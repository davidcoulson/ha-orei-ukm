"""The OREI serial protocol, kept free of Home Assistant so it can be unit tested alone.

OREI's small switches speak one line of ASCII per command at 9600 8N1. For the UKM-401
(OREI manual, page 6):

    PS11R .. PS14R   select HDMI input 1-4
                     reply "please insert HDMI" when that input has no live signal
    Status           reply "Status:\\r\\nBaud 9600\\r\\nPS12R OK", or "NA" when no input is live
    Reset            restart the switch
    Recover          factory reset (deliberately not exposed)
    Baud XX          change the baud rate (deliberately not exposed)

Models are described as data so another OREI switch with the same style of protocol can be
added by adding an entry to MODELS.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Model:
    """How one switch model is driven."""

    name: str
    inputs: int
    baudrate: int
    line_ending: str
    select_template: str  # formatted with n = 1-based input number
    status_command: str
    reset_command: str | None


MODELS: dict[str, Model] = {
    "UKM-401": Model(
        name="UKM-401",
        inputs=4,
        baudrate=9600,
        line_ending="\n",
        select_template="PS1{n}R",
        status_command="Status",
        reset_command="Reset",
    ),
}

DEFAULT_MODEL = "UKM-401"

_SELECTED = re.compile(r"PS1(\d)R OK")
_BAUD = re.compile(r"Baud\s+(\d+)")
_NO_SIGNAL = re.compile(r"insert\s+HDMI", re.IGNORECASE)


class OreiError(Exception):
    """The switch could not be reached or gave an unusable reply."""


class NoSignalError(OreiError):
    """The switch refused to select an input because nothing live is connected to it."""


@dataclass(frozen=True)
class Status:
    """Parsed reply to the status command."""

    input: int | None  # 1-based live input, or None when the switch reports NA
    baudrate: int | None
    raw: str


def parse_status(reply: str, model: Model = MODELS[DEFAULT_MODEL]) -> Status:
    """Parse a status reply.

    >>> parse_status("Status:\\r\\nBaud 9600\\r\\nPS12R OK\\r\\n").input
    2
    >>> parse_status("Status:\\r\\nBaud 9600\\r\\nNA\\r\\n").input is None
    True
    """
    text = reply.strip()
    if not text:
        raise OreiError("Empty reply to status")
    states: list[int | None] = []
    baudrate = None
    for line in text.splitlines():
        line = line.strip()
        selected = _SELECTED.fullmatch(line)
        baud = _BAUD.fullmatch(line)
        if selected and 1 <= int(selected.group(1)) <= model.inputs:
            states.append(int(selected.group(1)))
        elif line == "NA":
            states.append(None)
        elif baud:
            baudrate = int(baud.group(1))
        elif line not in ("", "Status:"):
            raise OreiError(f"Unrecognised status reply: {text!r}")
    if len(states) != 1:
        raise OreiError("Status reply must contain exactly one valid state")
    return Status(input=states[0], baudrate=baudrate, raw=text)


def select_command(model: Model, number: int) -> str:
    """Command that selects input `number` (1-based)."""
    if not 1 <= number <= model.inputs:
        raise ValueError(f"{model.name} has inputs 1-{model.inputs}, not {number}")
    return model.select_template.format(n=number)


def check_select_reply(reply: str, number: int, model: Model = MODELS[DEFAULT_MODEL]) -> bool:
    """Validate an acknowledgement; return False if silence needs confirmation."""
    if _NO_SIGNAL.search(reply):
        raise NoSignalError(f"Input {number} has no signal; turn on the device connected to it first")
    text = reply.strip()
    if not text:
        return False
    if text != f"{select_command(model, number)} OK":
        raise OreiError(f"Unexpected acknowledgement for input {number}: {text!r}")
    return True

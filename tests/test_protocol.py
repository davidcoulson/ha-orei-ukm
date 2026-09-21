"""Parsing the switch's replies, including the exact strings a real UKM-401 sent."""

import pytest

from custom_components.orei_ukm.protocol import (
    MODELS, NoSignalError, OreiError, check_select_reply, parse_status, select_command,
)


def test_status_with_live_input():
    s = parse_status("Status:\r\nBaud 9600\r\nPS12R OK\r\n")
    assert (s.input, s.baudrate) == (2, 9600)


def test_status_na_seen_on_real_switch():
    # Captured from the theater's UKM-401 with every source off.
    s = parse_status("Status:\r\nBaud 9600\r\nNA\r\n")
    assert s.input is None and s.baudrate == 9600


@pytest.mark.parametrize("reply", ["", "   ", "garbage"])
def test_status_rejects_nonsense(reply):
    with pytest.raises(OreiError):
        parse_status(reply)


def test_select_commands():
    m = MODELS["UKM-401"]
    assert [select_command(m, n) for n in (1, 2, 3, 4)] == ["PS11R", "PS12R", "PS13R", "PS14R"]
    with pytest.raises(ValueError):
        select_command(m, 5)


def test_no_signal_reply_seen_on_real_switch():
    with pytest.raises(NoSignalError):
        check_select_reply("please insert HDMI\r\n", 3)
    check_select_reply("PS13R OK\r\n", 3)  # no exception
    check_select_reply("", 3)              # silence is not a refusal

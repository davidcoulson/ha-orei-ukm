"""Talking to the switch over a TCP-to-serial adapter or a local serial port.

Each command opens the link, writes one line, reads until the switch goes quiet, and closes
again. Serial servers usually accept a single TCP client at a time, so holding a connection
open would lock out anything else (a terminal while debugging, another controller). A lock
keeps commands from this integration strictly one at a time.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .protocol import Model, OreiError, Status, check_select_reply, parse_status, select_command

COMMAND_TIMEOUT = 10.0  # entire transaction; cancellation cleanup has its own bound
CLOSE_TIMEOUT = 1.0
MAX_REPLY_BYTES = 4096
CONNECT_TIMEOUT = 5.0
REPLY_TIMEOUT = 2.0   # wait this long for the first byte
QUIET_TIME = 0.25     # then stop once the switch has been silent this long


class Transport:
    """Opens a (reader, writer) pair to the switch."""

    description: str

    @asynccontextmanager
    async def open(self) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        raise NotImplementedError
        yield  # pragma: no cover


class TcpTransport(Transport):
    """Ethernet-to-RS-232 adapter in TCP server (raw socket) mode."""

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.description = f"{host}:{port}"

    @asynccontextmanager
    async def open(self):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT)
        except (OSError, TimeoutError) as err:
            raise OreiError(f"Cannot connect to {self.description}: {err}") from err
        try:
            yield reader, writer
        finally:
            await _close_writer(writer)


class SerialTransport(Transport):
    """A serial port on the Home Assistant host (USB-serial adapter)."""

    def __init__(self, device: str, baudrate: int) -> None:
        self.device, self.baudrate = device, baudrate
        self.description = device

    @asynccontextmanager
    async def open(self):
        import serial_asyncio_fast  # imported late: only needed for local serial ports

        try:
            reader, writer = await asyncio.wait_for(
                serial_asyncio_fast.open_serial_connection(url=self.device, baudrate=self.baudrate, bytesize=8, parity="N", stopbits=1),
                CONNECT_TIMEOUT,
            )
        except (OSError, TimeoutError) as err:
            raise OreiError(f"Cannot open {self.device}: {err}") from err
        try:
            yield reader, writer
        finally:
            await _close_writer(writer)


class OreiClient:
    """High-level commands for one switch."""

    def __init__(self, transport: Transport, model: Model) -> None:
        self.transport = transport
        self.model = model
        self._lock = asyncio.Lock()

    async def command(self, command: str) -> str:
        """Send one command line and return the reply text (may be empty)."""
        async with self._lock:
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT), self.transport.open() as (reader, writer):
                    writer.write((command + self.model.line_ending).encode("ascii"))
                    await writer.drain()
                    return await _read_reply(reader)
            except TimeoutError as err:
                raise OreiError("Command transaction timed out") from err
            except OSError as err:
                raise OreiError(f"Communication failed with {self.transport.description}: {err}") from err

    async def status(self) -> Status:
        return parse_status(await self.command(self.model.status_command), self.model)

    async def select_input(self, number: int) -> None:
        """Switch to input `number` (1-based). Raises NoSignalError if nothing is live there."""
        reply = await self.command(select_command(self.model, number))
        if not check_select_reply(reply, number, self.model):
            if (await self.status()).input != number:
                raise OreiError(f"Switch did not confirm input {number}")

    async def reset(self) -> None:
        if not self.model.reset_command:
            raise OreiError(f"{self.model.name} has no reset command")
        await self.command(self.model.reset_command)


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
    except OSError:
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            return
        raise
    try:
        async with asyncio.timeout(CLOSE_TIMEOUT):
            await writer.wait_closed()
    except TimeoutError as err:
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            return  # preserve the cancellation that triggered teardown
        raise OreiError("Connection close timed out") from err
    except OSError:
        pass


async def _read_reply(reader: asyncio.StreamReader) -> str:
    chunks: list[bytes] = []
    size = 0
    timeout = REPLY_TIMEOUT
    while True:
        try:
            data = await asyncio.wait_for(reader.read(256), timeout)
        except TimeoutError:
            break
        if not data:
            break
        size += len(data)
        if size > MAX_REPLY_BYTES:
            raise OreiError("Reply exceeds size limit")
        chunks.append(data)
        timeout = QUIET_TIME
    return b"".join(chunks).decode("ascii", errors="replace")

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
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


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
            writer.close()


class OreiClient:
    """High-level commands for one switch."""

    def __init__(self, transport: Transport, model: Model) -> None:
        self.transport = transport
        self.model = model
        self._lock = asyncio.Lock()

    async def command(self, command: str) -> str:
        """Send one command line and return the reply text (may be empty)."""
        async with self._lock, self.transport.open() as (reader, writer):
            writer.write((command + self.model.line_ending).encode("ascii"))
            await writer.drain()
            return await _read_reply(reader)

    async def status(self) -> Status:
        return parse_status(await self.command(self.model.status_command))

    async def select_input(self, number: int) -> None:
        """Switch to input `number` (1-based). Raises NoSignalError if nothing is live there."""
        reply = await self.command(select_command(self.model, number))
        check_select_reply(reply, number)

    async def reset(self) -> None:
        if not self.model.reset_command:
            raise OreiError(f"{self.model.name} has no reset command")
        await self.command(self.model.reset_command)


async def _read_reply(reader: asyncio.StreamReader) -> str:
    chunks: list[bytes] = []
    timeout = REPLY_TIMEOUT
    while True:
        try:
            data = await asyncio.wait_for(reader.read(256), timeout)
        except TimeoutError:
            break
        if not data:
            break
        chunks.append(data)
        timeout = QUIET_TIME
    return b"".join(chunks).decode("ascii", errors="replace")

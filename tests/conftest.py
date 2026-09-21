"""Shared fixtures: a fake OREI UKM-401 on a local TCP port, and HA's custom-integration loader."""

from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST, CONF_PORT

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def allow_localhost_sockets(socket_enabled):
    """HA's test plugin blocks sockets; these tests talk to a fake switch on 127.0.0.1."""
    yield


class FakeUkm401:
    """Answers like the real switch: 9600 baud status, NA when nothing is live,
    and "please insert HDMI" when asked for an input with no signal."""

    def __init__(self) -> None:
        self.live: set[int] = set()
        self.current: int | None = None
        self.received: list[str] = []
        self.server: asyncio.base_events.Server | None = None
        self.port = 0

    def reply(self, line: str) -> str:
        self.received.append(line)
        if line == "Status":
            state = f"PS1{self.current}R OK" if self.current else "NA"
            return f"Status:\r\nBaud 9600\r\n{state}\r\n"
        if len(line) == 5 and line.startswith("PS1") and line.endswith("R") and line[3].isdigit():
            n = int(line[3])
            if n not in self.live:
                return "please insert HDMI\r\n"
            self.current = n
            return f"PS1{n}R OK\r\n"
        if line == "Reset":
            return ""
        return "error\r\n"

    async def _handle(self, reader, writer) -> None:
        try:
            while line := await reader.readline():
                writer.write(self.reply(line.decode().strip()).encode())
                await writer.drain()
        finally:
            writer.close()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()


@pytest.fixture
async def fake_switch():
    switch = FakeUkm401()
    await switch.start()
    yield switch
    await switch.stop()


@pytest.fixture
async def setup_switch(hass, fake_switch):
    entry = MockConfigEntry(
        domain="orei_ukm", title="OREI UKM-401 (127.0.0.1)", unique_id=f"127.0.0.1:{fake_switch.port}",
        data={"transport": "tcp", CONF_HOST: "127.0.0.1", CONF_PORT: fake_switch.port, "model": "UKM-401"},
        options={"input_names": ["Wii", "Xbox", "RetroPie", "Input 4"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry



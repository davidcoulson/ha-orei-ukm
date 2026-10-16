"""The client against the fake switch over real TCP."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.orei_ukm.client import OreiClient, TcpTransport
from custom_components.orei_ukm.protocol import MODELS, NoSignalError, OreiError


def client_for(switch):
    return OreiClient(TcpTransport("127.0.0.1", switch.port), MODELS["UKM-401"])


async def test_status_and_select(fake_switch):
    client = client_for(fake_switch)
    assert (await client.status()).input is None
    fake_switch.live = {1, 2}
    await client.select_input(2)
    assert (await client.status()).input == 2
    assert fake_switch.received == ["Status", "PS12R", "Status"]


async def test_select_without_signal_raises(fake_switch):
    with pytest.raises(NoSignalError):
        await client_for(fake_switch).select_input(3)


async def test_unreachable_adapter_raises():
    client = OreiClient(TcpTransport("127.0.0.1", 1), MODELS["UKM-401"])
    with pytest.raises(OreiError):
        await client.status()


async def test_commands_are_serialised(fake_switch):
    client = client_for(fake_switch)
    fake_switch.live = {1, 2, 3, 4}
    await asyncio.gather(*(client.select_input(n) for n in (1, 2, 3, 4)))
    assert sorted(fake_switch.received) == ["PS11R", "PS12R", "PS13R", "PS14R"]


@pytest.mark.parametrize("phase", ["stream", "drain", "close"])
async def test_transaction_deadline(monkeypatch, phase):
    from custom_components.orei_ukm import client as client_module

    async def blocked(*args):
        await asyncio.Event().wait()

    reader = Mock(read=AsyncMock(return_value=b""))
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    if phase == "stream":
        async def trickle(*args):
            await asyncio.sleep(0.001)
            return b"x"
        reader.read.side_effect = trickle
    elif phase == "drain":
        writer.drain.side_effect = blocked
    else:
        writer.wait_closed.side_effect = blocked
    monkeypatch.setattr(client_module, "COMMAND_TIMEOUT", 0.03, raising=False)
    monkeypatch.setattr(client_module, "CLOSE_TIMEOUT", 0.01, raising=False)
    monkeypatch.setattr(asyncio, "open_connection", AsyncMock(return_value=(reader, writer)))
    client = client_for(type("Switch", (), {"port": 1})())
    with pytest.raises(OreiError):
        await asyncio.wait_for(client.command("Status"), 0.3)
    assert writer.close.called
    assert not client._lock.locked()
    reader.read.side_effect = None
    writer.drain.side_effect = writer.wait_closed.side_effect = None
    assert await client.command("Reset") == ""


async def test_reply_size_limit(monkeypatch):
    from custom_components.orei_ukm import client as client_module

    async def oversized(*args):
        await asyncio.sleep(0)
        return b"x" * 256

    reader = Mock(read=AsyncMock(side_effect=oversized))
    monkeypatch.setattr(client_module, "MAX_REPLY_BYTES", 512, raising=False)
    with pytest.raises(OreiError, match="[Ss]ize|[Ll]arge|[Ll]imit"):
        await asyncio.wait_for(client_module._read_reply(reader), 0.3)
    assert reader.read.await_count == 3


@pytest.mark.parametrize("close_result", ["delayed", "blocked", "error"])
async def test_serial_close_is_awaited(monkeypatch, close_result):
    import serial_asyncio_fast
    from custom_components.orei_ukm import client as client_module

    entered = asyncio.Event()
    release = asyncio.Event()

    async def wait_closed():
        entered.set()
        if close_result == "error":
            raise OSError("disconnected")
        await release.wait()

    reader = Mock(read=AsyncMock(return_value=b""))
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock(side_effect=wait_closed))
    opener = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(serial_asyncio_fast, "open_serial_connection", opener)
    monkeypatch.setattr(client_module, "CLOSE_TIMEOUT", 0.03, raising=False)
    client = OreiClient(client_module.SerialTransport("fake", 9600), MODELS["UKM-401"])
    first = asyncio.create_task(client.command("Reset"))
    if close_result == "delayed":
        await asyncio.wait_for(entered.wait(), 0.3)
        second = asyncio.create_task(client.command("Reset"))
        await asyncio.sleep(0)
        assert opener.await_count == 1
        assert client._lock.locked()
        release.set()
        await asyncio.gather(first, second)
    elif close_result == "blocked":
        with pytest.raises(OreiError):
            await asyncio.wait_for(first, 0.3)
    else:
        await first
    assert writer.wait_closed.await_count >= 1
    assert not client._lock.locked()

"""The client against the fake switch over real TCP."""

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
    import asyncio
    client = client_for(fake_switch)
    fake_switch.live = {1, 2, 3, 4}
    await asyncio.gather(*(client.select_input(n) for n in (1, 2, 3, 4)))
    assert sorted(fake_switch.received) == ["PS11R", "PS12R", "PS13R", "PS14R"]

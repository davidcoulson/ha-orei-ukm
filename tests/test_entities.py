"""Entities and the raw-command action, running inside Home Assistant."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError

from custom_components.orei_ukm.const import CONF_INPUT_NAMES, DOMAIN

SELECT = "select.orei_ukm_401_127_0_0_1_input"
SIGNAL = "binary_sensor.orei_ukm_401_127_0_0_1_signal"
RESTART = "button.orei_ukm_401_127_0_0_1_restart"
LINK = "binary_sensor.orei_ukm_401_127_0_0_1_link"


async def test_entities_when_nothing_is_live(hass, setup_switch):
    select = hass.states.get(SELECT)
    assert select.state == "unknown"
    assert select.attributes["options"] == ["Wii", "Xbox", "RetroPie", "Input 4"]
    assert hass.states.get(SIGNAL).state == "off"
    assert hass.states.get(RESTART) is not None


async def test_select_input(hass, setup_switch, fake_switch):
    fake_switch.live = {2}
    await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Xbox"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "Xbox"
    assert hass.states.get(SIGNAL).state == "on"
    assert "PS12R" in fake_switch.received


async def test_select_input_without_signal_errors(hass, setup_switch):
    with pytest.raises(HomeAssistantError, match="RetroPie"):
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "RetroPie"}, blocking=True)


async def test_restart_button(hass, setup_switch, fake_switch):
    await hass.services.async_call("button", "press", {"entity_id": RESTART}, blocking=True)
    assert "Reset" in fake_switch.received


async def test_send_command_returns_reply(hass, setup_switch):
    response = await hass.services.async_call(
        DOMAIN, "send_command", {"config_entry_id": setup_switch.entry_id, "command": "Status"},
        blocking=True, return_response=True)
    assert response == {"reply": "Status:\r\nBaud 9600\r\nNA"}


async def test_link_sensor_follows_the_status_poll(hass, setup_switch, fake_switch):
    link = hass.states.get(LINK)
    assert link.state == "on"
    assert link.attributes["last_reply"] == "Status:\r\nBaud 9600\r\nNA"
    assert link.attributes["last_error"] is None
    assert link.attributes["failures"] == 0

    # The adapter goes away: the other entities drop out, the link sensor says why and stays.
    await fake_switch.stop()
    await setup_switch.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "unavailable"
    link = hass.states.get(LINK)
    assert link.state == "off"
    assert "Cannot connect" in link.attributes["last_error"]
    assert link.attributes["failures"] == 1
    await fake_switch.start()  # so the fixture's stop has a server to close


async def test_unload(hass, setup_switch):
    assert await hass.config_entries.async_unload(setup_switch.entry_id)

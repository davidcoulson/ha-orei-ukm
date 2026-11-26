"""orei_ukm.reload_code: unload, re-import the modules from disk, set up again."""

import sys

from homeassistant.config_entries import ConfigEntryState

from custom_components.orei_ukm.const import DOMAIN

PACKAGE = "custom_components.orei_ukm"


async def test_reload_code_replaces_the_modules(hass, setup_switch):
    entry = setup_switch
    assert entry.state is ConfigEntryState.LOADED
    old = {n: m for n, m in sys.modules.items() if n.startswith(PACKAGE)}

    await hass.services.async_call(DOMAIN, "reload_code", {}, blocking=True)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert sys.modules[PACKAGE] is not old[PACKAGE]
    assert hass.services.has_service(DOMAIN, "reload_code")
    # send_command was registered again by the new module and works on the new entry data
    response = await hass.services.async_call(
        DOMAIN, "send_command", {"config_entry_id": entry.entry_id, "command": "Status"},
        blocking=True, return_response=True)
    assert response == {"reply": "Status:\r\nBaud 9600\r\nNA"}

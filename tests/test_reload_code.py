"""orei_ukm.reload_code: unload, re-import the modules from disk, set up again."""

import sys

from homeassistant.config_entries import ConfigEntryState

from custom_components.orei_ukm import _clear_marketplace_restart
from custom_components.orei_ukm.const import DOMAIN
from homeassistant.helpers import issue_registry as ir

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


async def test_reload_clears_only_marketplaces_orei_ukm_restart_repairs(hass) -> None:
    for domain, issue_id, issue_domain in (
        ("marketplace", "restart_required_1_tags/2026.11.27.2", DOMAIN),
        ("marketplace", "restart_required_2_tags/2026.11.26.01", "ssh"),
        ("marketplace", "critical_x", DOMAIN),
        (DOMAIN, "restart_required_x", DOMAIN),
    ):
        ir.async_create_issue(
            hass, domain, issue_id, is_fixable=False, issue_domain=issue_domain,
            severity=ir.IssueSeverity.WARNING, translation_key="x",
        )
    _clear_marketplace_restart(hass)
    assert set(ir.async_get(hass).issues) == {
        ("marketplace", "restart_required_2_tags/2026.11.26.01"),
        ("marketplace", "critical_x"),
        (DOMAIN, "restart_required_x"),
    }

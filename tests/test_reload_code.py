"""orei_ukm.reload_code: unload, re-import the modules from disk, set up again."""

import json
import sys
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import issue_registry as ir

from custom_components.orei_ukm import _CODE_VERSION, _clear_marketplace_restart
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


async def test_reload_clears_only_the_running_versions_restart_repair(hass, monkeypatch) -> None:
    monkeypatch.setitem(_clear_marketplace_restart.__globals__, "_CODE_VERSION", "1.2.3")
    for domain, issue_id, issue_domain in (
        ("marketplace", "restart_required_1_tags/1.2.3", DOMAIN),
        ("marketplace", "restart_required_2_tags/v1.2.3", DOMAIN),
        ("marketplace", "restart_required_3_tags/1.2.4", DOMAIN),
        ("marketplace", "restart_required_4_tags/1.2.3", "ssh"),
        ("marketplace", "critical_x", DOMAIN),
        (DOMAIN, "restart_required_x", DOMAIN),
    ):
        ir.async_create_issue(
            hass, domain, issue_id, is_fixable=False, issue_domain=issue_domain,
            severity=ir.IssueSeverity.WARNING, translation_key="x",
        )
    _clear_marketplace_restart(hass)
    assert set(ir.async_get(hass).issues) == {
        ("marketplace", "restart_required_3_tags/1.2.4"),
        ("marketplace", "restart_required_4_tags/1.2.3"),
        ("marketplace", "critical_x"),
        (DOMAIN, "restart_required_x"),
    }


def test_code_version_is_the_manifest_version() -> None:
    manifest = Path(__file__).parents[1] / "custom_components" / "orei_ukm" / "manifest.json"
    assert _CODE_VERSION == json.loads(manifest.read_text())["version"]

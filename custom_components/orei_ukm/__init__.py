"""OREI HDMI switch (RS-232) integration.

Controls OREI switches such as the UKM-401 4x1 HDMI KVM over their RS-232 port, either
through an Ethernet-to-RS-232 adapter (raw TCP) or a serial port on the Home Assistant host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import importlib
import logging
import sys

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import OreiClient, SerialTransport, TcpTransport
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_DEVICE,
    CONF_TRANSPORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    UNREACHABLE_AFTER,
    SERVICE_SEND_COMMAND,
    TRANSPORT_SERIAL,
)
from .protocol import DEFAULT_MODEL, MODELS, OreiError, Status

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SELECT, Platform.BINARY_SENSOR, Platform.BUTTON]


@dataclass
class Link:
    """How the last status polls went: the Link sensor reads this, so it can say the serial
    path is dead while the other entities are simply unavailable."""

    last_success: datetime | None = None
    last_reply: str | None = None
    last_error: str | None = None
    failures: int = 0


@dataclass
class OreiData:
    client: OreiClient
    coordinator: DataUpdateCoordinator[Status]
    link: Link = field(default_factory=Link)


type OreiConfigEntry = ConfigEntry[OreiData]


def build_client(data: dict) -> OreiClient:
    model = MODELS[data.get(CONF_MODEL, DEFAULT_MODEL)]
    if data.get(CONF_TRANSPORT) == TRANSPORT_SERIAL:
        transport = SerialTransport(data[CONF_SERIAL_DEVICE], model.baudrate)
    else:
        transport = TcpTransport(data[CONF_HOST], data[CONF_PORT])
    return OreiClient(transport, model)


async def async_setup_entry(hass: HomeAssistant, entry: OreiConfigEntry) -> bool:
    client = build_client(dict(entry.data))
    link = Link()

    # Every poll is the switch's Status command over the whole path (network, adapter, RS-232,
    # switch): a reply proves the path end to end, which is what the Link sensor reports.
    async def _update() -> Status:
        try:
            status = await client.status()
        except OreiError as err:
            link.last_error = str(err)
            link.failures += 1
            if link.failures >= UNREACHABLE_AFTER:
                _set_unreachable(hass, entry, client, True)
            raise UpdateFailed(str(err)) from err
        _set_unreachable(hass, entry, client, False)
        link.last_success = dt_util.utcnow()
        link.last_reply = status.raw
        link.last_error = None
        link.failures = 0
        return status

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=f"{DOMAIN} {client.transport.description}",
        update_method=_update,
        update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        # Setup retries on its own schedule and rebuilds the poll state each time, so raise the
        # issue now rather than waiting for UNREACHABLE_AFTER polls that never accumulate.
        _set_unreachable(hass, entry, client, True)
        raise
    entry.runtime_data = OreiData(client, coordinator, link)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    _register_reload_code(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OreiConfigEntry) -> bool:
    _set_unreachable(hass, entry, entry.runtime_data.client, False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _set_unreachable(hass: HomeAssistant, entry: OreiConfigEntry, client: OreiClient, unreachable: bool) -> None:
    """Show (or clear) the Repairs issue; creating it again for the same id is a no-op update."""
    issue_id = f"unreachable_{entry.entry_id}"
    if unreachable:
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.ERROR,
            translation_key="unreachable", translation_placeholders={"host": client.transport.description},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


async def _reload_on_options(hass: HomeAssistant, entry: OreiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    async def send_command(call: ServiceCall) -> ServiceResponse:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise ServiceValidationError("That switch is not set up")
        try:
            reply = await entry.runtime_data.client.command(call.data[ATTR_COMMAND])
        except OreiError as err:
            raise HomeAssistantError(str(err)) from err
        await entry.runtime_data.coordinator.async_request_refresh()
        return {"reply": reply.strip()}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        send_command,
        schema=vol.Schema({vol.Required(ATTR_CONFIG_ENTRY): cv.string, vol.Required(ATTR_COMMAND): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )


def _import_code(package: str) -> None:
    """Import the new package and its platforms in the executor, so HA's own import is a cache hit."""
    for platform in importlib.import_module(package).PLATFORMS:
        importlib.import_module(f"{package}.{platform}")


def _forget_code(hass: HomeAssistant, package: str, domain: str) -> None:
    """Drop a package's modules so the next setup imports them from disk again.

    Home Assistant keeps its own copy of each imported integration module
    (hass.data["components"], keyed "<domain>" and "<domain>.<platform>") next to
    sys.modules; both have to go.
    """
    for cache, root in ((sys.modules, package), (hass.data.get("components", {}), domain),
                        (hass.data.get("missing_platforms", {}), domain)):
        for key in [n for n in cache if n == root or n.startswith(root + ".")]:
            del cache[key]
    importlib.invalidate_caches()  # or a file added since the last import may not be found


def _register_reload_code(hass: HomeAssistant) -> None:
    """Dev: orei_ukm.reload_code loads the Python files from disk without a restart."""

    async def _reload_code(call: ServiceCall) -> None:
        # Disabled and ignored entries are never set up, so they are not ours to reload.
        entries = hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=False
        )
        for entry in entries:
            if not await hass.config_entries.async_unload(entry.entry_id):
                raise HomeAssistantError(f"{DOMAIN} did not unload; restart Home Assistant instead")
        _forget_code(hass, __name__, DOMAIN)
        try:
            await hass.async_add_import_executor_job(_import_code, __name__)
        except Exception as err:
            # This handler stays registered, so the action works again once the code is fixed.
            raise HomeAssistantError(f"{DOMAIN} is unloaded: the new code did not load ({err}). "
                                     f"Fix it and call {DOMAIN}.reload_code again") from err
        failed = [e.title for e in entries if not await hass.config_entries.async_setup(e.entry_id)]
        if failed:
            raise HomeAssistantError(f"{DOMAIN} did not set up again for {failed}; see the log")

    async_register_admin_service(hass, DOMAIN, "reload_code", _reload_code)

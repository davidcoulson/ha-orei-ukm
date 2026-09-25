"""OREI HDMI switch (RS-232) integration.

Controls OREI switches such as the UKM-401 4x1 HDMI KVM over their RS-232 port, either
through an Ethernet-to-RS-232 adapter (raw TCP) or a serial port on the Home Assistant host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
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
            raise UpdateFailed(str(err)) from err
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
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = OreiData(client, coordinator, link)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OreiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload_on_options(hass: HomeAssistant, entry: OreiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

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

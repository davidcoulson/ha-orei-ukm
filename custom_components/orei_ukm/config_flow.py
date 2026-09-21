"""Config and options flows: where the switch is, and what is plugged into each input."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import build_client
from .const import (
    CONF_INPUT_NAMES,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_DEVICE,
    CONF_TRANSPORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRANSPORT_SERIAL,
    TRANSPORT_TCP,
)
from .protocol import DEFAULT_MODEL, MODELS, OreiError


class OreiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the model and how the switch is connected."""
        return self.async_show_menu(step_id="user", menu_options=[TRANSPORT_TCP, TRANSPORT_SERIAL])

    async def async_step_tcp(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TRANSPORT: TRANSPORT_TCP, **user_input}
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if (error := await _probe(data)) is None:
                return self.async_create_entry(title=f"OREI {data[CONF_MODEL]} ({user_input[CONF_HOST]})", data=data)
            errors["base"] = error
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): vol.All(vol.Coerce(int), vol.Range(1, 65535)),
            vol.Required(CONF_MODEL, default=DEFAULT_MODEL): _model_selector(),
        })
        return self.async_show_form(step_id="tcp", data_schema=schema, errors=errors)

    async def async_step_serial(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TRANSPORT: TRANSPORT_SERIAL, **user_input}
            await self.async_set_unique_id(user_input[CONF_SERIAL_DEVICE])
            self._abort_if_unique_id_configured()
            if (error := await _probe(data)) is None:
                return self.async_create_entry(title=f"OREI {data[CONF_MODEL]} ({user_input[CONF_SERIAL_DEVICE]})", data=data)
            errors["base"] = error
        schema = vol.Schema({
            vol.Required(CONF_SERIAL_DEVICE, default=(user_input or {}).get(CONF_SERIAL_DEVICE, "/dev/ttyUSB0")): str,
            vol.Required(CONF_MODEL, default=DEFAULT_MODEL): _model_selector(),
        })
        return self.async_show_form(step_id="serial", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OreiOptionsFlow()


class OreiOptionsFlow(OptionsFlow):
    """Name each input after what is plugged into it, and set the polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        count = MODELS[self.config_entry.data.get(CONF_MODEL, DEFAULT_MODEL)].inputs
        current = input_names(self.config_entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            names = [user_input[f"input_{i}"].strip() or f"Input {i}" for i in range(1, count + 1)]
            if len(set(names)) != len(names):
                errors["base"] = "duplicate_names"
            else:
                return self.async_create_entry(data={CONF_INPUT_NAMES: names, CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]})
        fields: dict[Any, Any] = {vol.Required(f"input_{i}", default=current[i - 1]): str for i in range(1, count + 1)}
        fields[vol.Required(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))] = vol.All(vol.Coerce(int), vol.Range(5, 3600))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)


def input_names(entry: ConfigEntry) -> list[str]:
    """The configured names for each input, defaulting to "Input 1".."Input N"."""
    count = MODELS[entry.data.get(CONF_MODEL, DEFAULT_MODEL)].inputs
    names = list(entry.options.get(CONF_INPUT_NAMES, []))[:count]
    return names + [f"Input {i}" for i in range(len(names) + 1, count + 1)]


def _model_selector() -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(options=list(MODELS), mode=selector.SelectSelectorMode.DROPDOWN))


async def _probe(data: dict[str, Any]) -> str | None:
    """Ask the switch for its status; returns an error key or None when it answered."""
    try:
        await build_client(data).status()
    except OreiError:
        return "cannot_connect"
    return None

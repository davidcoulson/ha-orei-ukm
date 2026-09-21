"""The input selector: one option per HDMI input, named in the integration's options."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_flow import input_names
from .entity import OreiEntity
from .protocol import NoSignalError, OreiError


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([OreiInputSelect(entry)])


class OreiInputSelect(OreiEntity, SelectEntity):
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, entry) -> None:
        super().__init__(entry, "input")
        self._attr_options = input_names(entry)

    @property
    def current_option(self) -> str | None:
        # None (unknown) when the switch reports NA: nothing live on any input.
        number = self.coordinator.data.input if self.coordinator.data else None
        return self._attr_options[number - 1] if number and number <= len(self._attr_options) else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"input_number": data.input if data else None, "raw_status": data.raw if data else None}

    async def async_select_option(self, option: str) -> None:
        number = self._attr_options.index(option) + 1
        try:
            await self._client.select_input(number)
        except NoSignalError as err:
            raise HomeAssistantError(f"{option}: {err}") from err
        except OreiError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

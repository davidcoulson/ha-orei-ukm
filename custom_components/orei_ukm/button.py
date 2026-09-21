"""Restart button (the switch's Reset command). Factory reset is deliberately not exposed."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import OreiEntity
from .protocol import OreiError


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.runtime_data.client.model.reset_command:
        async_add_entities([OreiRestartButton(entry)])


class OreiRestartButton(OreiEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry) -> None:
        super().__init__(entry, "restart")

    async def async_press(self) -> None:
        try:
            await self._client.reset()
        except OreiError as err:
            raise HomeAssistantError(str(err)) from err

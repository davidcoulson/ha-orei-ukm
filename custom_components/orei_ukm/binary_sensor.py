"""Signal sensor: on while any input has a live source (the switch does not report NA)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import OreiEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([OreiSignalSensor(entry)])


class OreiSignalSensor(OreiEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, entry) -> None:
        super().__init__(entry, "signal")

    @property
    def is_on(self) -> bool | None:
        return None if self.coordinator.data is None else self.coordinator.data.input is not None

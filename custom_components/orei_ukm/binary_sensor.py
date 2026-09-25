"""Signal sensor: on while any input has a live source (the switch does not report NA).
Link sensor: on while the switch answers the status poll, the one reading that stays available
when the serial path is down."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import OreiEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([OreiSignalSensor(entry), OreiLinkSensor(entry)])


class OreiSignalSensor(OreiEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, entry) -> None:
        super().__init__(entry, "signal")

    @property
    def is_on(self) -> bool | None:
        return None if self.coordinator.data is None else self.coordinator.data.input is not None


class OreiLinkSensor(OreiEntity, BinarySensorEntity):
    """The status poll (every scan interval, 30 s by default) is a Status command over the whole
    path: network, adapter, RS-232 cable, switch. On while the last one was answered."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry) -> None:
        super().__init__(entry, "link")
        self._link = entry.runtime_data.link

    @property
    def available(self) -> bool:
        # A dead link is exactly what this sensor exists to show.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "adapter": self._client.transport.description,
            "last_reply": self._link.last_reply,
            "last_success": self._link.last_success.isoformat() if self._link.last_success else None,
            "last_error": self._link.last_error,
            "failures": self._link.failures,
        }

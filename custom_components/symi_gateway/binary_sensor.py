"""Binary sensor platform for Symi Gateway - TCP based like Yeelight Pro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import async_add_setuper, SymiEntity
from .const import DOMAIN
from .device import SymiDevice, MotionDevice
from .converters.base import Converter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway binary sensor entities."""
    await async_add_setuper(hass, config_entry, 'binary_sensor', async_add_entities)

class SymiBinarySensor(SymiEntity, BinarySensorEntity):
    """Symi binary sensor entity."""

    def __init__(self, device: SymiDevice, conv: Converter) -> None:
        """Initialize the binary sensor."""
        super().__init__(device, conv)

        # Set device class based on converter attribute
        if conv.attr == 'motion':
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        elif conv.attr == 'door':
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        else:
            self._attr_device_class = None

    @property
    def is_on(self) -> bool | None:
        """Return true if binary sensor is on."""
        return bool(self._attr_extra_state_attributes.get(self._name, False))

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.device.online

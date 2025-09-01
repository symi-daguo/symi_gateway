"""Switch platform for Symi Gateway - TCP based like Yeelight Pro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import async_add_setuper, SymiEntity
from .const import DOMAIN
from .device import SymiDevice, SwitchDevice
from .converters.base import Converter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway switch entities."""
    await async_add_setuper(hass, config_entry, 'switch', async_add_entities)


def async_add_entities(device: SymiDevice, conv: Converter):
    """Add switch entity."""
    if conv.domain == 'switch':
        return SymiSwitch(device, conv)

class SymiSwitch(SymiEntity, SwitchEntity):
    """Symi switch entity."""

    def __init__(self, device: SymiDevice, conv: Converter) -> None:
        """Initialize the switch."""
        super().__init__(device, conv)

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self._attr_extra_state_attributes.get(self._name, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.device_send_props({self._name: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.device_send_props({self._name: False})

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.device.online

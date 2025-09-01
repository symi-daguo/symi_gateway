"""Light platform for Symi Gateway - TCP based like Yeelight Pro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import async_add_setuper, SymiEntity
from .const import DOMAIN
from .device import SymiDevice, LightDevice
from .converters.base import Converter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway light entities."""
    await async_add_setuper(hass, config_entry, 'light', async_add_entities)


class SymiLight(SymiEntity, LightEntity):
    """Symi light entity."""

    def __init__(self, device: SymiDevice, conv: Converter) -> None:
        """Initialize the light."""
        super().__init__(device, conv)

        # Determine supported color modes based on device type
        self._attr_supported_color_modes = {ColorMode.ONOFF}

        if hasattr(device, 'type'):
            if device.type == 4:  # LIGHT_DIMMER
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
            elif device.type == 24:  # LIGHT_CCT
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
                self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
                self._attr_min_mireds = 153  # 6500K
                self._attr_max_mireds = 500  # 2000K

        # Set color mode
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return bool(self._attr_extra_state_attributes.get('light', False))

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            return self._attr_extra_state_attributes.get('brightness')
        return None

    @property
    def color_temp(self) -> int | None:
        """Return the CT color value in mireds."""
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            return self._attr_extra_state_attributes.get('color_temp')
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        params = {"light": True}

        if ATTR_BRIGHTNESS in kwargs and ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            params["brightness"] = kwargs[ATTR_BRIGHTNESS]

        if ATTR_COLOR_TEMP_KELVIN in kwargs and ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            params["color_temp"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

        await self.device_send_props(params)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.device_send_props({"light": False})

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.device.online

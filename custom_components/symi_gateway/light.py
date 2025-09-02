"""Light platform for Symi Gateway."""
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MSG_TYPE_SWITCH_CONTROL, MSG_TYPE_BRIGHTNESS_CONTROL, MSG_TYPE_COLOR_TEMP_CONTROL
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway light entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Get light devices
    light_devices = coordinator.get_devices_by_capability("brightness")

    entities = []
    for device in light_devices:
        entities.append(SymiLight(coordinator, device))

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d light entities", len(entities))


class SymiLight(CoordinatorEntity, LightEntity):
    """Symi light entity."""

    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{DOMAIN}_{device.unique_id}_light"
        self._attr_name = f"{device.name}"

        # Determine supported color modes based on device type
        self._attr_supported_color_modes = {ColorMode.ONOFF}

        if device.device_type == 4:  # SMART_LIGHT
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
        elif device.device_type == 24:  # FIVE_COLOR_LIGHT
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
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device.unique_id)},
            "name": self._device.name,
            "manufacturer": "Symi",
            "model": f"Smart Light Type {self._device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._device.get_state("switch") or False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            # Convert from device range (0-100) to HA range (0-255)
            device_brightness = self._device.get_state("brightness")
            if device_brightness is not None:
                return int(device_brightness * 255 / 100)
        return None

    @property
    def color_temp(self) -> int | None:
        """Return the CT color value in mireds."""
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            # Convert from device range (0-100) to mireds
            device_temp = self._device.get_state("color_temp")
            if device_temp is not None:
                # 0% = warm (500 mireds), 100% = cool (153 mireds)
                mireds = 500 - (device_temp * (500 - 153) / 100)
                return int(mireds)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        # Turn on the light using switch control
        success = await self.coordinator.async_control_device(
            self._device.network_address,
            MSG_TYPE_SWITCH_CONTROL,
            bytes([0x02])  # Turn on: bit1-2 = 10
        )

        if not success:
            _LOGGER.error("Failed to turn on light: %s", self._device.name)
            return

        # Set brightness if specified
        if ATTR_BRIGHTNESS in kwargs and ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_pct = int(brightness_255 * 100 / 255)
            brightness_pct = max(1, min(100, brightness_pct))  # Clamp to 1-100

            await self.coordinator.async_control_device(
                self._device.network_address,
                MSG_TYPE_BRIGHTNESS_CONTROL,
                bytes([brightness_pct])
            )

        # Set color temperature if specified (use mireds, not kelvin)
        if ATTR_COLOR_TEMP_KELVIN in kwargs and ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            # Convert kelvin to 0-100 percentage (2000K-6500K)
            color_temp_pct = int((kelvin - 2000) * 100 / (6500 - 2000))
            color_temp_pct = max(0, min(100, color_temp_pct))  # Clamp to 0-100

            await self.coordinator.async_control_device(
                self._device.network_address,
                MSG_TYPE_COLOR_TEMP_CONTROL,
                bytes([color_temp_pct])
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        success = await self.coordinator.async_control_device(
            self._device.network_address,
            MSG_TYPE_SWITCH_CONTROL,
            bytes([0x01])  # Turn off: bit1-2 = 01
        )

        if not success:
            _LOGGER.error("Failed to turn off light: %s", self._device.name)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._device.online and self.coordinator.available

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

from .const import DOMAIN
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway light entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Add light entities from discovered devices
    for device in coordinator.discovered_devices.values():
        if "light" in device.capabilities:
            _LOGGER.warning("💡 Creating light entity for device: %s (Type: %d)", device.name, device.device_type)
            entities.append(SymiLight(coordinator, device))
            _LOGGER.warning("✅ Created light entity: %s", device.name)

    _LOGGER.info("🔄 Setting up %d light entities", len(entities))
    async_add_entities(entities)


class SymiLight(CoordinatorEntity, LightEntity):
    """Light entity for Symi smart lights."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo):
        """Initialize light entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.device = device
        
        # Set entity attributes
        self._attr_name = device.name
        self._attr_unique_id = f"{device.device_id}_light"
        
        # Set supported color modes
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        if "color_temp" in device.capabilities:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            # Set color temp range (2700K to 6500K in mireds)
            self._attr_min_mireds = 154  # 6500K
            self._attr_max_mireds = 370  # 2700K
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.device.unique_id)},
            "name": self.device.name,
            "manufacturer": "Symi",
            "model": f"Smart Light Type {self.device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }
    
    @property
    def is_on(self) -> bool:
        """Return if light is on."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return False
        return current_device.get_state("switch") or False
    
    @property
    def brightness(self) -> int | None:
        """Return brightness of light (0-255)."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return None
        
        # Convert from 0-100 to 0-255
        brightness_pct = current_device.get_state("brightness")
        if brightness_pct is not None:
            return int(brightness_pct * 255 / 100)
        return None
    
    @property
    def color_temp(self) -> int | None:
        """Return color temperature in mireds."""
        if ColorMode.COLOR_TEMP not in self._attr_supported_color_modes:
            return None
        
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return None
        
        # Convert from 0-100 to mireds (154-370)
        color_temp_pct = current_device.get_state("color_temp")
        if color_temp_pct is not None:
            # 0% = warm (370 mireds), 100% = cool (154 mireds)
            mireds = 370 - (color_temp_pct * (370 - 154) / 100)
            return int(mireds)
        return None
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            _LOGGER.error("❌ Device not found: %s", self.device.unique_id)
            return
        
        # Turn on the light
        success = await self.coordinator.async_control_device(
            current_device.unique_id, MSG_TYPE_SWITCH_CONTROL, SWITCH_ALL_ON
        )
        
        if not success:
            _LOGGER.error("❌ Failed to turn on light: %s", self._attr_name)
            return
        
        # Set brightness if specified
        if ATTR_BRIGHTNESS in kwargs:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_pct = int(brightness_255 * 100 / 255)
            brightness_pct = max(1, min(100, brightness_pct))  # Clamp to 1-100
            
            success = await self.coordinator.async_control_device(
                current_device.unique_id, MSG_TYPE_BRIGHTNESS_CONTROL, brightness_pct
            )
            
            if not success:
                _LOGGER.error("❌ Failed to set brightness: %s", self._attr_name)
        
        # Set color temperature if specified
        if ATTR_COLOR_TEMP in kwargs and ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            mireds = kwargs[ATTR_COLOR_TEMP]
            # Convert mireds to 0-100 percentage
            color_temp_pct = int((370 - mireds) * 100 / (370 - 154))
            color_temp_pct = max(0, min(100, color_temp_pct))  # Clamp to 0-100
            
            success = await self.coordinator.async_control_device(
                current_device.unique_id, MSG_TYPE_COLOR_TEMP_CONTROL, color_temp_pct
            )
            
            if not success:
                _LOGGER.error("❌ Failed to set color temperature: %s", self._attr_name)
        
        _LOGGER.info("📡 Light ON command sent: %s", self._attr_name)
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            _LOGGER.error("❌ Device not found: %s", self.device.unique_id)
            return
        
        # Turn off the light
        success = await self.coordinator.async_control_device(
            current_device.unique_id, MSG_TYPE_SWITCH_CONTROL, SWITCH_ALL_OFF
        )
        
        if success:
            _LOGGER.info("📡 Light OFF command sent: %s", self._attr_name)
        else:
            _LOGGER.error("❌ Failed to turn off light: %s", self._attr_name)

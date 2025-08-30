"""Binary sensor platform for Symi Gateway."""
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEVICE_TYPE_DOOR_SENSOR, DEVICE_TYPE_MOTION_SENSOR
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway binary sensor entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Add binary sensor entities from discovered devices
    for device in coordinator.discovered_devices.values():
        if "motion" in device.capabilities or "door" in device.capabilities:
            _LOGGER.warning("🔍 Creating binary sensor entity for device: %s (Type: %d)", device.name, device.device_type)
            if device.device_type == DEVICE_TYPE_DOOR_SENSOR:
                entities.append(SymiDoorSensor(coordinator, device))
            elif device.device_type == DEVICE_TYPE_MOTION_SENSOR:
                entities.append(SymiMotionSensor(coordinator, device))
            else:
                # Generic binary sensor
                entities.append(SymiBinarySensor(coordinator, device))
            _LOGGER.warning("✅ Created binary sensor entity: %s", device.name)

    _LOGGER.info("🔄 Setting up %d binary sensor entities", len(entities))
    async_add_entities(entities)


class SymiBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base binary sensor for Symi devices."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo):
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.device = device
        
        # Set entity attributes
        self._attr_name = device.name
        self._attr_unique_id = f"{device.device_id}_binary_sensor"
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.device.unique_id)},
            "name": self.device.name,
            "manufacturer": "Symi",
            "model": f"Binary Sensor Type {self.device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }
    
    @property
    def is_on(self) -> bool | None:
        """Return true if binary sensor is on."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return None
        
        return current_device.get_state("binary_sensor")


class SymiDoorSensor(SymiBinarySensor):
    """Door sensor for Symi devices."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo):
        """Initialize door sensor."""
        super().__init__(coordinator, device)
        
        self._attr_device_class = BinarySensorDeviceClass.DOOR
        self._attr_icon = "mdi:door"
    
    @property
    def is_on(self) -> bool | None:
        """Return true if door is open."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return None
        
        # Door sensor: True = open, False = closed
        return current_device.get_state("door_open")


class SymiMotionSensor(SymiBinarySensor):
    """Motion sensor for Symi devices."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo):
        """Initialize motion sensor."""
        super().__init__(coordinator, device)
        
        self._attr_device_class = BinarySensorDeviceClass.MOTION
        self._attr_icon = "mdi:motion-sensor"
    
    @property
    def is_on(self) -> bool | None:
        """Return true if motion is detected."""
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return None
        
        # Motion sensor: True = motion detected, False = no motion
        return current_device.get_state("motion_detected")

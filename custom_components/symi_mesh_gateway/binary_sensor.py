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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway binary sensor entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Register platform callback for dynamic entity creation
    coordinator.add_platform_callback("binary_sensor", async_add_entities)

    # Get binary sensor devices that are already discovered
    motion_devices = coordinator.get_devices_by_capability("motion")
    door_devices = coordinator.get_devices_by_capability("door")

    entities = []
    for device in motion_devices:
        entities.append(SymiBinarySensor(coordinator, device, "motion"))

    for device in door_devices:
        entities.append(SymiBinarySensor(coordinator, device, "door"))

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d binary sensor entities", len(entities))


class SymiBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Symi binary sensor entity."""

    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo, sensor_type: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device = device
        self._sensor_type = sensor_type

        self._attr_name = f"{device.name}"
        self._attr_unique_id = f"{DOMAIN}_{device.unique_id}_{sensor_type}"

        # Set device class based on sensor type
        if sensor_type == 'motion':
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        elif sensor_type == 'door':
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        else:
            self._attr_device_class = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device.unique_id)},
            "name": self._device.name,
            "manufacturer": "Symi",
            "model": f"Binary Sensor Type {self._device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if binary sensor is on."""
        return self._device.get_state(self._sensor_type) or False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._device.online and self.coordinator.available

"""Switch platform for Symi Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway switch entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Store the add_entities callback for dynamic entity creation
    coordinator._switch_add_entities = async_add_entities
    coordinator._created_switch_entities = getattr(coordinator, '_created_switch_entities', set())

    entities = []

    # Add device switches from discovered devices
    for device in coordinator.discovered_devices.values():
        if "switch" in device.capabilities:
            _LOGGER.info("🔌 Creating switch entities for device: %s (%d channels)", device.name, device.channels)
            if device.channels == 1:
                # Single channel switch
                entity_id = device.unique_id
                if entity_id not in coordinator._created_switch_entities:
                    entities.append(SymiDeviceSwitch(coordinator, device))
                    coordinator._created_switch_entities.add(entity_id)
                    _LOGGER.info("✅ Created single channel switch: %s", device.name)
            else:
                # Multi-channel switch - create individual switches for each channel
                for channel in range(1, device.channels + 1):
                    entity_id = f"{device.unique_id}_{channel}"
                    if entity_id not in coordinator._created_switch_entities:
                        entities.append(SymiDeviceSwitch(coordinator, device, channel))
                        coordinator._created_switch_entities.add(entity_id)
                        _LOGGER.info("✅ Created channel %d switch: %s", channel, device.name)

    _LOGGER.info("🔄 Setting up %d switch entities", len(entities))
    async_add_entities(entities)
    
    # Register callback for future device discoveries
    def device_discovered_callback():
        """Handle new device discovery."""
        hass.async_create_task(_async_handle_new_switch_devices(coordinator))
    
    coordinator.async_add_listener(device_discovered_callback)


async def _async_handle_new_switch_devices(coordinator: SymiGatewayCoordinator) -> None:
    """Handle newly discovered devices and create switch entities for them."""
    if not hasattr(coordinator, '_switch_add_entities'):
        return
        
    new_entities = []
    
    # Check for new switch devices
    for device in coordinator.discovered_devices.values():
        if "switch" in device.capabilities:
            if device.channels == 1:
                entity_id = device.unique_id
                if entity_id not in coordinator._created_switch_entities:
                    new_entities.append(SymiDeviceSwitch(coordinator, device))
                    coordinator._created_switch_entities.add(entity_id)
                    _LOGGER.info("🆕 Created new single channel switch: %s", device.name)
            else:
                for channel in range(1, device.channels + 1):
                    entity_id = f"{device.unique_id}_{channel}"
                    if entity_id not in coordinator._created_switch_entities:
                        new_entities.append(SymiDeviceSwitch(coordinator, device, channel))
                        coordinator._created_switch_entities.add(entity_id)
                        _LOGGER.info("🆕 Created new channel %d switch: %s", channel, device.name)
    
    if new_entities:
        _LOGGER.info("🔄 Adding %d new switch entities", len(new_entities))
        coordinator._switch_add_entities(new_entities)


class SymiDeviceSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for Symi devices."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo, channel: int = 1):
        """Initialize device switch."""
        super().__init__(coordinator)
        self.device = device
        self.channel = channel
        
        # Set entity attributes
        if device.channels == 1:
            self._attr_name = device.name
            self._attr_unique_id = device.unique_id
        else:
            self._attr_name = f"{device.name} 通道{channel}"
            self._attr_unique_id = f"{device.unique_id}_{channel}"
        
        self._attr_icon = "mdi:light-switch"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return get_device_info(self.device)

    @property
    def is_on(self) -> bool:
        """Return if switch is on."""
        if self.device.channels == 1:
            return self.device.state.get("switch", False)
        else:
            return self.device.state.get(f"switch_{self.channel}", False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.device.online

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.async_control_device(
            self.device.network_address,
            "switch",
            True,
            self.channel if self.device.channels > 1 else None
        )
        
        if success:
            # Update local state
            if self.device.channels == 1:
                self.device.state["switch"] = True
            else:
                self.device.state[f"switch_{self.channel}"] = True
            self.async_write_ha_state()
            _LOGGER.info("✅ Switch turned ON: %s", self._attr_name)
        else:
            _LOGGER.error("❌ Failed to turn ON switch: %s", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.async_control_device(
            self.device.network_address,
            "switch",
            False,
            self.channel if self.device.channels > 1 else None
        )
        
        if success:
            # Update local state
            if self.device.channels == 1:
                self.device.state["switch"] = False
            else:
                self.device.state[f"switch_{self.channel}"] = False
            self.async_write_ha_state()
            _LOGGER.info("✅ Switch turned OFF: %s", self._attr_name)
        else:
            _LOGGER.error("❌ Failed to turn OFF switch: %s", self._attr_name)

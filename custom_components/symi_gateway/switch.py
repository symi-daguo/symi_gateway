"""Switch platform for Symi Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    get_gateway_device_info,
    MSG_TYPE_ON_OFF,
    SWITCH_ON,
    SWITCH_OFF,
    MSG_TYPE_SWITCH_CONTROL,
    SWITCH_ALL_ON,
    SWITCH_ALL_OFF,
    SWITCH_1_ON,
    SWITCH_1_OFF,
    SWITCH_2_ON,
    SWITCH_2_OFF,
    SWITCH_3_ON,
    SWITCH_3_OFF,
    SWITCH_4_ON,
    SWITCH_4_OFF,
    SWITCH_5_ON,
    SWITCH_5_OFF,
    SWITCH_6_ON,
    SWITCH_6_OFF,
)
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

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
    coordinator._created_switch_entities = set()

    entities = []

    # Always add gateway management switches
    entities.append(SymiDiscoverySwitch(coordinator))
    entities.append(SymiDebugLogSwitch(coordinator))
    _LOGGER.info("🔄 Added gateway management switches")

    # Add device switches from gateway device manager
    if coordinator.gateway and coordinator.gateway.device_manager:
        for device in coordinator.gateway.device_manager.get_all_devices():
            if "switch" in device.capabilities:
                _LOGGER.warning("🔌 Creating switch entities for device: %s (%d channels)", device.name, device.channels)
                device_entities = _create_switch_entities_for_device(coordinator, device)
                entities.extend(device_entities)

    _LOGGER.info("🔄 Setting up %d switch entities", len(entities))
    async_add_entities(entities)

    # Register device discovery callback for dynamic entity creation
    def device_discovered_callback():
        """Handle device discovery for switch entities."""
        coordinator.hass.async_create_task(_async_device_discovered_callback(coordinator))

    coordinator.async_add_listener(device_discovered_callback)


def _create_switch_entities_for_device(coordinator: SymiGatewayCoordinator, device) -> list:
    """Create switch entities for a device."""
    entities = []

    if device.channels == 1:
        # Single channel switch
        entity = SymiDeviceSwitch(coordinator, device)
        entities.append(entity)
        entity_id = f"{device.unique_id}"
        coordinator._created_switch_entities.add(entity_id)
        _LOGGER.warning("✅ Created single channel switch: %s", device.name)
    else:
        # Multi-channel switch - create individual switches for each channel
        for channel in range(1, device.channels + 1):
            entity = SymiDeviceSwitch(coordinator, device, channel)
            entities.append(entity)
            entity_id = f"{device.unique_id}_{channel}"
            coordinator._created_switch_entities.add(entity_id)
            _LOGGER.warning("✅ Created channel %d switch: %s", channel, device.name)

    return entities


async def _async_device_discovered_callback(coordinator: SymiGatewayCoordinator) -> None:
    """Handle new device discovery for dynamic entity creation."""
    if not hasattr(coordinator, '_switch_add_entities'):
        return

    new_entities = []

    # Check for new switch devices
    if coordinator.gateway and coordinator.gateway.device_manager:
        for device in coordinator.gateway.device_manager.get_all_devices():
            if "switch" in device.capabilities:
                # Check if we already created entities for this device
                device_id = device.unique_id
                if device.channels == 1:
                    if device_id not in coordinator._created_switch_entities:
                        entity = SymiDeviceSwitch(coordinator, device)
                        new_entities.append(entity)
                        coordinator._created_switch_entities.add(device_id)
                        _LOGGER.warning("🆕 Created new single channel switch: %s", device.name)
                else:
                    for channel in range(1, device.channels + 1):
                        entity_id = f"{device_id}_{channel}"
                        if entity_id not in coordinator._created_switch_entities:
                            entity = SymiDeviceSwitch(coordinator, device, channel)
                            new_entities.append(entity)
                            coordinator._created_switch_entities.add(entity_id)
                            _LOGGER.warning("🆕 Created new channel %d switch: %s", channel, device.name)

    if new_entities:
        _LOGGER.info("🔄 Adding %d new switch entities", len(new_entities))
        coordinator._switch_add_entities(new_entities)


class SymiDiscoverySwitch(CoordinatorEntity, SwitchEntity):
    """Discovery mode switch for Symi Gateway."""

    def __init__(self, coordinator: SymiGatewayCoordinator):
        """Initialize discovery switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "亖米读取设备列表"
        self._attr_unique_id = f"{DOMAIN}_read_device_list_{coordinator.entry.entry_id}"
        self._attr_icon = "mdi:format-list-bulleted"
        self._attr_entity_category = None  # Make it a primary entity

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return get_gateway_device_info(self.coordinator.entry.entry_id)
    
    @property
    def is_on(self) -> bool:
        """Return if reading device list."""
        return False  # This is a momentary switch
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_count": len(self.coordinator.discovered_devices),
            "description": "点击读取网关中已配对的设备列表",
        }
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Read device list from gateway."""
        _LOGGER.info("📋 Reading device list from gateway...")
        success = await self.coordinator.async_read_device_list()
        if success:
            _LOGGER.info("✅ Device list request sent")
        else:
            _LOGGER.error("❌ Failed to send device list request")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (no action for momentary switch)."""
        pass  # Momentary switch, no off action needed


class SymiDeviceSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for Symi devices."""
    
    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo, channel: int = 1):
        """Initialize device switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.device = device
        self.channel = channel
        
        # Set entity attributes
        if device.channels == 1:
            self._attr_name = device.name
            self._attr_unique_id = f"{device.device_id}_switch"
        else:
            self._attr_name = f"{device.name} 第{channel}路"
            self._attr_unique_id = f"{device.device_id}_switch_{channel}"
        
        self._attr_icon = "mdi:light-switch"
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.device.unique_id)},
            "name": self.device.name,
            "manufacturer": "Symi",
            "model": f"Type {self.device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }
    
    @property
    def is_on(self) -> bool:
        """Return if switch is on."""
        # Get current device from coordinator
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            return False
        
        if current_device.channels == 1:
            return current_device.get_state("switch") or False
        else:
            return current_device.get_state(f"switch_{self.channel}") or False
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        # Get current device
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            _LOGGER.error("❌ Device not found: %s", self.device.unique_id)
            return
        
        # Determine control parameter
        if current_device.channels == 1:
            param = SWITCH_ALL_ON
        else:
            param_map = {
                1: SWITCH_1_ON,
                2: SWITCH_2_ON,
                3: SWITCH_3_ON,
                4: SWITCH_4_ON,
                5: SWITCH_5_ON,
                6: SWITCH_6_ON,
            }
            param = param_map.get(self.channel, SWITCH_1_ON)
        
        # Send control command using new protocol
        param_bytes = bytes([SWITCH_ON])
        success = await self.coordinator.async_control_device_by_id(
            current_device.unique_id, MSG_TYPE_ON_OFF, param_bytes
        )

        if success:
            _LOGGER.warning("✅ Switch ON command sent: %s", self._attr_name)
            # Update local state
            if current_device.channels == 1:
                current_device.state["switch"] = True
            else:
                current_device.state[f"switch_{self.channel}"] = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("❌ Failed to send switch ON command: %s", self._attr_name)
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        # Get current device
        current_device = self.coordinator.get_device(self.device.unique_id)
        if not current_device:
            _LOGGER.error("❌ Device not found: %s", self.device.unique_id)
            return
        
        # Determine control parameter
        if current_device.channels == 1:
            param = SWITCH_ALL_OFF
        else:
            param_map = {
                1: SWITCH_1_OFF,
                2: SWITCH_2_OFF,
                3: SWITCH_3_OFF,
                4: SWITCH_4_OFF,
                5: SWITCH_5_OFF,
                6: SWITCH_6_OFF,
            }
            param = param_map.get(self.channel, SWITCH_1_OFF)
        
        # Send control command using new protocol
        param_bytes = bytes([SWITCH_OFF])
        success = await self.coordinator.async_control_device_by_id(
            current_device.unique_id, MSG_TYPE_ON_OFF, param_bytes
        )

        if success:
            _LOGGER.warning("✅ Switch OFF command sent: %s", self._attr_name)
            # Update local state
            if current_device.channels == 1:
                current_device.state["switch"] = False
            else:
                current_device.state[f"switch_{self.channel}"] = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("❌ Failed to send switch OFF command: %s", self._attr_name)



class SymiDebugLogSwitch(CoordinatorEntity, SwitchEntity):
    """Debug log switch for Symi Gateway."""

    def __init__(self, coordinator: SymiGatewayCoordinator):
        """Initialize debug log switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "亖米网关调试日志"
        self._attr_unique_id = f"{DOMAIN}_debug_log_{coordinator.entry.entry_id}"
        self._attr_icon = "mdi:bug"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._is_on = False

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return get_gateway_device_info(self.coordinator.entry.entry_id)

    @property
    def is_on(self) -> bool:
        """Return if debug logging is on."""
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        status = {}
        if self.coordinator.comm:
            status = self.coordinator.comm.get_status()

        return {
            "connection_status": status,
            "description": "开启后可在日志中查看详细的通信数据",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on debug logging."""
        self._is_on = True
        self.async_write_ha_state()

        # Set logger level to DEBUG for all symi_gateway modules
        symi_logger = logging.getLogger("custom_components.symi_gateway")
        symi_logger.setLevel(logging.DEBUG)

        # Also set for specific modules
        for module in ["tcp_comm", "serial_comm", "gateway", "coordinator", "protocol"]:
            module_logger = logging.getLogger(f"custom_components.symi_gateway.{module}")
            module_logger.setLevel(logging.DEBUG)

        _LOGGER.warning("🔍 Debug logging ENABLED for Symi Gateway - All TCP/Serial data will be logged")

        # Log current connection status
        if self.coordinator.comm:
            status = self.coordinator.comm.get_status()
            _LOGGER.warning("📊 Connection Status: %s", status)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off debug logging."""
        self._is_on = False
        self.async_write_ha_state()

        # Set logger level back to INFO
        symi_logger = logging.getLogger("custom_components.symi_gateway")
        symi_logger.setLevel(logging.INFO)

        # Also set for specific modules
        for module in ["tcp_comm", "serial_comm", "gateway", "coordinator", "protocol"]:
            module_logger = logging.getLogger(f"custom_components.symi_gateway.{module}")
            module_logger.setLevel(logging.INFO)

        _LOGGER.warning("🔍 Debug logging DISABLED for Symi Gateway")

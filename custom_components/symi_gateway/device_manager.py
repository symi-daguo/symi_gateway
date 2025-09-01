"""Device management for Symi Gateway."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .const import (
    DEVICE_TYPE_NAMES,
    DEVICE_TYPE_ZERO_FIRE_SWITCH,
    DEVICE_TYPE_SINGLE_FIRE_SWITCH,
    DEVICE_TYPE_SMART_SOCKET,
    DEVICE_TYPE_SMART_LIGHT,
    DEVICE_TYPE_SMART_CURTAIN,
    DEVICE_TYPE_SCENE_PANEL,
    DEVICE_TYPE_DOOR_SENSOR,
    DEVICE_TYPE_MOTION_SENSOR,
    DEVICE_TYPE_CARD_POWER,
    DEVICE_TYPE_THERMOSTAT,
    DEVICE_TYPE_TEMP_HUMIDITY,
    DEVICE_TYPE_TRANSPARENT_MODULE,
    DEVICE_TYPE_FIVE_COLOR_LIGHT,
    MSG_TYPE_SWITCH_CONTROL,
    MSG_TYPE_BRIGHTNESS_CONTROL,
    MSG_TYPE_COLOR_TEMP_CONTROL,
    MSG_TYPE_CURTAIN_CONTROL,
    MSG_TYPE_CURTAIN_POSITION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Device information."""

    mac_address: str
    network_address: int
    device_type: int
    device_sub_type: int
    rssi: int
    vendor_id: int
    device_id: str = ""  # Unique device identifier
    name: str = ""
    channels: int = 1
    capabilities: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    last_seen: Optional[float] = None
    online: bool = True  # Device online status
    
    def __post_init__(self):
        """Post-initialization setup."""
        if not self.device_id:
            self.device_id = self.mac_address.replace(":", "").lower()

        if not self.name:
            self.name = self._generate_name()

        if not self.capabilities:
            self.capabilities = self._determine_capabilities()
    
    def _generate_name(self) -> str:
        """Generate device name based on type and address."""
        type_name = DEVICE_TYPE_NAMES.get(self.device_type, "未知设备")
        
        # Determine channel count for switches
        # 根据协议文档：dev_sub_type = 具体支持几路 1-8路
        # 子类型直接等于键数/路数
        if self.device_type == DEVICE_TYPE_ZERO_FIRE_SWITCH:
            if self.device_sub_type == 0:
                channels = 1  # 0表示1路
            else:
                channels = self.device_sub_type  # 子类型直接等于路数
        elif self.device_type == DEVICE_TYPE_SINGLE_FIRE_SWITCH:
            if self.device_sub_type == 0:
                channels = 1  # 0表示1路
            else:
                channels = self.device_sub_type  # 子类型直接等于路数
            
            self.channels = channels
            if channels > 1:
                type_name = f"{channels}路{type_name}"
        
        # Use last 4 characters of MAC for unique identification
        mac_suffix = self.mac_address.replace(":", "")[-4:].upper()
        return f"{type_name} {mac_suffix}"
    
    def _determine_capabilities(self) -> list[str]:
        """Determine device capabilities based on type."""
        capabilities = []
        
        if self.device_type in [DEVICE_TYPE_ZERO_FIRE_SWITCH, DEVICE_TYPE_SINGLE_FIRE_SWITCH]:
            capabilities.extend(["switch"])
            if self.channels > 1:
                capabilities.extend([f"switch_{i}" for i in range(1, self.channels + 1)])
        
        elif self.device_type == DEVICE_TYPE_SMART_SOCKET:
            capabilities.extend(["switch", "power_monitoring"])
        
        elif self.device_type == DEVICE_TYPE_SMART_LIGHT:
            capabilities.extend(["light", "brightness", "color_temp"])
        
        elif self.device_type == DEVICE_TYPE_SMART_CURTAIN:
            capabilities.extend(["cover", "position"])
        
        elif self.device_type == DEVICE_TYPE_SCENE_PANEL:
            capabilities.extend(["scene_control"])
        
        elif self.device_type == DEVICE_TYPE_DOOR_SENSOR:
            capabilities.extend(["door"])

        elif self.device_type == DEVICE_TYPE_MOTION_SENSOR:
            capabilities.extend(["motion"])
        
        elif self.device_type == DEVICE_TYPE_CARD_POWER:
            capabilities.extend(["switch", "card_detection"])
        
        elif self.device_type == DEVICE_TYPE_THERMOSTAT:
            capabilities.extend(["climate", "temperature", "humidity"])
        
        elif self.device_type == DEVICE_TYPE_TEMP_HUMIDITY:
            capabilities.extend(["temperature", "humidity"])

        elif self.device_type == DEVICE_TYPE_FIVE_COLOR_LIGHT:
            capabilities.extend(["light", "brightness", "color_temp", "rgb"])

        elif self.device_type == DEVICE_TYPE_TRANSPARENT_MODULE:
            # 透传模块没有控制能力，只用于信号放大
            capabilities.extend(["transparent"])

        return capabilities
    
    @property
    def unique_id(self) -> str:
        """Get unique device ID."""
        return self.mac_address.replace(":", "").lower()
    
    @property
    def device_id(self) -> str:
        """Get device ID for Home Assistant."""
        return f"symi_{self.unique_id}"
    
    @property
    def is_switch(self) -> bool:
        """Check if device is a switch."""
        return "switch" in self.capabilities
    
    @property
    def is_light(self) -> bool:
        """Check if device is a light."""
        return "brightness" in self.capabilities
    
    @property
    def is_cover(self) -> bool:
        """Check if device is a cover."""
        return "cover" in self.capabilities
    
    @property
    def is_sensor(self) -> bool:
        """Check if device is a sensor."""
        return any(cap in self.capabilities for cap in ["temperature", "humidity", "illuminance"])
    
    @property
    def is_binary_sensor(self) -> bool:
        """Check if device is a binary sensor."""
        return "binary_sensor" in self.capabilities
    
    @property
    def is_climate(self) -> bool:
        """Check if device is a climate device."""
        return "climate" in self.capabilities
    
    def update_state(self, msg_type: int, value: Any) -> None:
        """Update device state."""
        if msg_type == MSG_TYPE_SWITCH_CONTROL:
            if self.channels == 1:
                self.state["switch"] = bool(value & 0x02)
            else:
                # Multi-channel switch
                for i in range(self.channels):
                    bit_pos = i + 1
                    self.state[f"switch_{i+1}"] = bool(value & (1 << bit_pos))
        
        elif msg_type == MSG_TYPE_BRIGHTNESS_CONTROL:
            self.state["brightness"] = min(100, max(0, value))
        
        elif msg_type == MSG_TYPE_COLOR_TEMP_CONTROL:
            self.state["color_temp"] = min(100, max(0, value))
        
        elif msg_type == MSG_TYPE_CURTAIN_CONTROL:
            if value == 1:
                self.state["cover_state"] = "opening"
            elif value == 2:
                self.state["cover_state"] = "closing"
            elif value == 3:
                self.state["cover_state"] = "stopped"
        
        elif msg_type == MSG_TYPE_CURTAIN_POSITION:
            self.state["position"] = min(100, max(0, value))
    
    def get_state(self, attribute: str) -> Any:
        """Get device state attribute."""
        return self.state.get(attribute)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "mac_address": self.mac_address,
            "network_address": self.network_address,
            "device_type": self.device_type,
            "device_sub_type": self.device_sub_type,
            "rssi": self.rssi,
            "vendor_id": self.vendor_id,
            "name": self.name,
            "channels": self.channels,
            "capabilities": self.capabilities,
            "state": self.state,
            "last_seen": self.last_seen,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceInfo:
        """Create from dictionary."""
        return cls(
            mac_address=data["mac_address"],
            network_address=data["network_address"],
            device_type=data["device_type"],
            device_sub_type=data["device_sub_type"],
            rssi=data["rssi"],
            vendor_id=data["vendor_id"],
            name=data.get("name", ""),
            channels=data.get("channels", 1),
            capabilities=data.get("capabilities", []),
            state=data.get("state", {}),
            last_seen=data.get("last_seen"),
        )


class DeviceManager:
    """Manages Symi devices."""
    
    def __init__(self):
        """Initialize device manager."""
        self.devices: dict[str, DeviceInfo] = {}
    
    def add_device(self, device: DeviceInfo) -> bool:
        """Add a device."""
        device_id = device.unique_id
        _LOGGER.warning("🔍 Trying to add device: ID=%s, MAC=%s, Type=%d", device_id, device.mac_address, device.device_type)

        if device_id in self.devices:
            # Update existing device
            existing = self.devices[device_id]
            existing.rssi = device.rssi
            existing.last_seen = device.last_seen
            _LOGGER.warning("📱 Updated existing device: %s", device.name)
            return False
        else:
            # Add new device
            self.devices[device_id] = device
            _LOGGER.warning("🆕 Added new device: %s (%s) - Total devices: %d", device.name, device.mac_address, len(self.devices))
            return True
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device by ID."""
        return self.devices.get(device_id)
    
    def get_device_by_mac(self, mac_address: str) -> Optional[DeviceInfo]:
        """Get device by MAC address."""
        mac_id = mac_address.replace(":", "").lower()
        return self.devices.get(mac_id)
    
    def get_device_by_address(self, network_address: int) -> Optional[DeviceInfo]:
        """Get device by network address."""
        for device in self.devices.values():
            if device.network_address == network_address:
                return device
        return None

    def has_device(self, device_id: str) -> bool:
        """Check if device exists."""
        return device_id in self.devices

    def update_device_status(self, device_id: str, online: bool) -> bool:
        """Update device online status."""
        if device_id in self.devices:
            self.devices[device_id].online = online
            return True
        return False
    
    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all devices."""
        return list(self.devices.values())
    
    def remove_device(self, device_id: str) -> bool:
        """Remove a device."""
        if device_id in self.devices:
            device = self.devices.pop(device_id)
            _LOGGER.info("🗑️ Removed device: %s", device.name)
            return True
        return False
    
    def clear_all_devices(self) -> None:
        """Clear all devices."""
        count = len(self.devices)
        self.devices.clear()
        _LOGGER.info("🗑️ Cleared %d devices", count)
    
    def update_device_state(self, network_address: int, msg_type: int, value: Any) -> Optional[DeviceInfo]:
        """Update device state by network address."""
        device = self.get_device_by_address(network_address)
        if device:
            device.update_state(msg_type, value)
            _LOGGER.debug("📊 Updated device state: %s, msg_type=0x%02X, value=%s", 
                         device.name, msg_type, value)
            return device
        return None
    
    def get_devices_by_type(self, device_type: int) -> list[DeviceInfo]:
        """Get devices by type."""
        return [device for device in self.devices.values() if device.device_type == device_type]
    
    def get_devices_by_capability(self, capability: str) -> list[DeviceInfo]:
        """Get devices by capability."""
        return [device for device in self.devices.values() if capability in device.capabilities]

    def to_dict(self) -> dict[str, Any]:
        """Convert all devices to dictionary for storage."""
        return {device_id: device.to_dict() for device_id, device in self.devices.items()}

    def from_dict(self, data: dict[str, Any]) -> None:
        """Load devices from dictionary."""
        self.devices.clear()
        for device_id, device_data in data.items():
            try:
                device = DeviceInfo.from_dict(device_data)
                self.devices[device_id] = device
            except Exception as err:
                _LOGGER.error("❌ Failed to load device %s: %s", device_id, err)

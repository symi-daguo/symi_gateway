"""Coordinator for Symi Gateway."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    DEFAULT_TIMEOUT,
    OP_READ_DEVICE_LIST,
    OP_RESP_READ_DEVICE_LIST,
    OP_DEVICE_CONTROL,
    OP_RESP_DEVICE_CONTROL,
    OP_EVENT_NODE_NOTIFICATION,
    STATUS_SUCCESS,
    STATUS_NODE_STATUS_EVENT,
    DEVICE_TYPE_NAMES,
)
from .tcp_comm import TCPCommunication
from .protocol import ProtocolFrame, ProtocolHandler, build_read_device_list_frame, build_device_control_frame
from .device_manager import DeviceManager, DeviceInfo

_LOGGER = logging.getLogger(__name__)

# Storage version for device data
STORAGE_VERSION = 1
STORAGE_KEY = "symi_gateway_devices"


class SymiGatewayCoordinator(DataUpdateCoordinator):
    """Coordinator for Symi Gateway."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, host: str, port: int):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # We don't use polling, only event-driven updates
        )
        
        self.entry = entry
        self.host = host
        self.port = port
        
        # Communication
        self.tcp_comm = TCPCommunication(host, port)
        self.protocol_handler = ProtocolHandler()
        
        # Device management
        self.device_manager = DeviceManager()
        self.discovered_devices: dict[str, DeviceInfo] = {}
        
        # State
        self.is_connected = False
        self.last_update_success = True
        
        # Callbacks for entity creation
        self._entity_callbacks: list[Callable] = []

        # Platform callbacks for dynamic entity creation
        self._platform_callbacks: dict[str, Callable] = {}
        
        # Response handling
        self._pending_responses: dict[int, asyncio.Future] = {}
        self._response_timeout = DEFAULT_TIMEOUT
        
        # Storage for device persistence
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Load previously saved devices
            await self._load_device_data()
            
            # Connect to gateway
            if not await self.tcp_comm.async_connect():
                _LOGGER.error("❌ Failed to connect to gateway")
                return False

            self.is_connected = True

            # Register frame callback
            self.tcp_comm.add_frame_callback(self._handle_frame)

            # Read current devices from gateway
            await self.async_read_device_list()

            _LOGGER.info("✅ Coordinator setup completed")
            return True

        except Exception as err:
            _LOGGER.error("❌ Coordinator setup failed: %s", err)
            return False

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Save device data before shutdown
        await self._save_device_data()
        
        self.is_connected = False
        await self.tcp_comm.async_disconnect()
        _LOGGER.info("🛑 Coordinator shutdown completed")

    def _handle_frame(self, frame: ProtocolFrame) -> None:
        """Handle received protocol frame."""
        _LOGGER.debug("📦 Handling frame: opcode=0x%02X, status=%s", frame.opcode, frame.status)
        
        if frame.opcode == OP_RESP_READ_DEVICE_LIST:
            self._handle_device_list_response(frame)
        elif frame.opcode == OP_RESP_DEVICE_CONTROL:
            self._handle_device_control_response(frame)
        elif frame.opcode == OP_EVENT_NODE_NOTIFICATION:
            self._handle_node_event(frame)
        else:
            _LOGGER.debug("🤷 Unhandled frame: opcode=0x%02X", frame.opcode)

    def _handle_device_list_response(self, frame: ProtocolFrame) -> None:
        """Handle device list response."""
        if frame.status != STATUS_SUCCESS:
            _LOGGER.error("❌ Device list request failed: status=0x%02X", frame.status)
            return
        
        if not frame.payload:
            _LOGGER.info("📋 No devices found in gateway")
            return
        
        _LOGGER.info("📋 Parsing device list: %d bytes", len(frame.payload))
        devices = self._parse_device_list(frame.payload)
        
        # Check for new devices (not in storage)
        new_devices = []
        updated_devices = []
        
        for device in devices:
            existing_device = self.discovered_devices.get(device.unique_id)
            
            if existing_device is None:
                # Completely new device
                self.discovered_devices[device.unique_id] = device
                self.device_manager.add_device(device)
                new_devices.append(device)
                _LOGGER.warning("🆕 NEW device discovered: %s (%s)", device.name, device.mac_address)
            else:
                # Update existing device info (network address, online status, etc.)
                existing_device.network_address = device.network_address
                existing_device.online = device.online
                existing_device.last_seen = device.last_seen
                updated_devices.append(existing_device)
                _LOGGER.debug("🔄 Updated existing device: %s", device.name)

        # Save updated device data
        if new_devices or updated_devices:
            self.hass.async_create_task(self._save_device_data())

        # Only trigger entity creation for genuinely new devices
        if new_devices:
            _LOGGER.warning("🔄 Triggering entity creation for %d NEW devices", len(new_devices))
            self.hass.async_create_task(self._create_entities_for_devices(new_devices))
        else:
            _LOGGER.info("👍 All devices are already known, no new entities to create")

        # Notify entity callbacks for status updates
        self._notify_entity_callbacks()

    def _parse_device_list(self, payload: bytes) -> list[DeviceInfo]:
        """Parse device list from payload.
        
        Based on protocol document dev_list_node_rsp_t structure:
        u8 max;          // 节点总数  最大5个
        u8 index;        // 0 - max-1   辅助批量返回列表
        u8 mac[6];       // MAC地址
        u16 naddr;       // 网络短地址 未分配时为0
        u16 vendor_id;   // 支持客户Vendor编码 隔离厂商 0未知
        u8 dev_type;     // 设备类型  0未知
        u8 dev_sub_type; // 具体支持几路 1-8路  0未知
        u8 online:1;     // bit0  0: 离线 1:在线  
        u8 only_tmall:1; // bit1  0: 厂商私有协议  1：只支持天猫精灵协议
        u8 status:6;     // 保留状态 bits
        u8 resv;         // 保留
        """
        devices = []
        offset = 0

        _LOGGER.warning("🔍 Parsing device list payload: %s", payload.hex().upper())

        while offset < len(payload):
            if offset + 16 > len(payload):  # Each device entry is 16 bytes
                _LOGGER.warning("⚠️ Incomplete device entry at offset %d, remaining bytes: %d", 
                              offset, len(payload) - offset)
                break

            try:
                # Parse device entry (16 bytes)
                device_data = payload[offset:offset+16]
                _LOGGER.warning("📱 Parsing device entry: %s", device_data.hex().upper())

                # Parse according to dev_list_node_rsp_t structure
                max_devices = device_data[0]   # u8 max
                device_index = device_data[1]  # u8 index
                
                # Extract MAC address (6 bytes)
                mac_bytes = device_data[2:8]   # u8 mac[6]
                mac_address = ":".join(f"{b:02X}" for b in mac_bytes)

                # Extract network address (2 bytes, little endian)
                network_address = int.from_bytes(device_data[8:10], 'little')  # u16 naddr

                # Extract vendor ID (2 bytes, little endian)
                vendor_id = int.from_bytes(device_data[10:12], 'little')  # u16 vendor_id

                # Extract device type and subtype
                device_type = device_data[12]    # u8 dev_type
                device_sub_type = device_data[13]  # u8 dev_sub_type
                
                # Extract online status and flags
                status_byte = device_data[14]  # Contains online:1, only_tmall:1, status:6
                online = bool(status_byte & 0x01)  # bit 0
                only_tmall = bool(status_byte & 0x02)  # bit 1
                
                # Reserved byte
                reserved = device_data[15]  # u8 resv

                # Calculate RSSI (not in protocol, use a default value)
                rssi = -50  # Default RSSI value

                # Create device info
                device = DeviceInfo(
                    mac_address=mac_address,
                    network_address=network_address,
                    device_type=device_type,
                    device_sub_type=device_sub_type,
                    rssi=rssi,
                    vendor_id=vendor_id,
                    last_seen=time.time(),
                    online=online,
                )

                devices.append(device)
                _LOGGER.warning("✅ Parsed device: %s, MAC=%s, type=%d, sub_type=%d, addr=0x%04X, online=%s",
                            device.name, mac_address, device_type, device_sub_type, network_address, online)

                # Log device parsing details
                _LOGGER.info("📊 Device Details:")
                _LOGGER.info("  - Index: %d/%d", device_index, max_devices - 1)
                _LOGGER.info("  - MAC: %s", mac_address)
                _LOGGER.info("  - Network Address: 0x%04X", network_address)
                _LOGGER.info("  - Vendor ID: 0x%04X", vendor_id)
                _LOGGER.info("  - Device Type: %d (%s)", device_type, DEVICE_TYPE_NAMES.get(device_type, f"未知设备({device_type})"))
                _LOGGER.info("  - Sub Type: %d", device_sub_type)
                _LOGGER.info("  - Online: %s", online)
                _LOGGER.info("  - Only Tmall: %s", only_tmall)
                _LOGGER.info("  - Reserved: 0x%02X", reserved)

                offset += 16

            except Exception as err:
                _LOGGER.error("❌ Failed to parse device at offset %d: %s", offset, err)
                # Get the actual device data if available
                if offset + 16 <= len(payload):
                    error_data = payload[offset:offset+16]
                    _LOGGER.error("  Device data: %s", error_data.hex().upper())
                break

        _LOGGER.warning("📋 Total parsed devices: %d", len(devices))
        return devices

    def _handle_device_control_response(self, frame: ProtocolFrame) -> None:
        """Handle device control response."""
        if frame.status == STATUS_SUCCESS:
            _LOGGER.debug("✅ Device control successful")
        else:
            _LOGGER.warning("⚠️ Device control failed: status=0x%02X", frame.status)

    def _handle_node_event(self, frame: ProtocolFrame) -> None:
        """Handle node event notification."""
        if frame.status != STATUS_NODE_STATUS_EVENT:
            return
        
        if len(frame.payload) < 5:
            _LOGGER.warning("⚠️ Invalid node event payload length: %d", len(frame.payload))
            return
        
        try:
            network_address = int.from_bytes(frame.payload[0:2], 'little')
            msg_type = frame.payload[2]
            value_bytes = frame.payload[3:]
            
            # Parse value based on message type
            if len(value_bytes) >= 1:
                value = value_bytes[0]
            else:
                value = 0
            
            _LOGGER.debug("📡 Node event: addr=0x%04X, msg_type=0x%02X, value=0x%02X", 
                         network_address, msg_type, value)
            
            # Update device state
            device = self.device_manager.update_device_state(network_address, msg_type, value)
            if device:
                # Trigger state update for entities
                self.async_set_updated_data({})
                
        except Exception as err:
            _LOGGER.error("❌ Failed to handle node event: %s", err)

    async def async_read_device_list(self) -> bool:
        """Read device list from gateway."""
        try:
            _LOGGER.info("📋 Reading device list from gateway...")
            frame_data = build_read_device_list_frame()
            success = await self.tcp_comm.async_send_frame(frame_data)
            
            if success:
                _LOGGER.info("✅ Device list request sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send device list request")
                return False
                
        except Exception as err:
            _LOGGER.error("❌ Failed to read device list: %s", err)
            return False

    async def async_control_device(self, network_address: int, msg_type: int, param: bytes = b'') -> bool:
        """Control a device."""
        try:
            _LOGGER.debug("🎮 Controlling device: addr=0x%04X, msg_type=0x%02X, param=%s", 
                         network_address, msg_type, param.hex() if param else "")
            
            frame_data = build_device_control_frame(network_address, msg_type, param)
            success = await self.tcp_comm.async_send_frame(frame_data)
            
            if success:
                _LOGGER.debug("✅ Device control command sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send device control command")
                return False
                
        except Exception as err:
            _LOGGER.error("❌ Failed to control device: %s", err)
            return False

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device by ID."""
        return self.device_manager.get_device(device_id)

    def get_devices_by_capability(self, capability: str) -> list[DeviceInfo]:
        """Get devices by capability."""
        return self.device_manager.get_devices_by_capability(capability)

    def add_entity_callback(self, callback: Callable) -> None:
        """Add entity creation callback."""
        self._entity_callbacks.append(callback)

    def add_platform_callback(self, platform: str, callback: Callable) -> None:
        """Add platform callback for dynamic entity creation."""
        self._platform_callbacks[platform] = callback
        _LOGGER.info("📋 Registered platform callback for %s", platform)

    def _notify_entity_callbacks(self) -> None:
        """Notify all entity callbacks."""
        for callback in self._entity_callbacks:
            try:
                callback()
            except Exception as err:
                _LOGGER.error("❌ Error in entity callback: %s", err)

    @property
    def available(self) -> bool:
        """Return if coordinator is available."""
        return self.is_connected and self.last_update_success

    async def _create_entities_for_devices(self, new_devices: list[DeviceInfo] | None = None) -> None:
        """Create entities for discovered devices."""
        try:
            if new_devices:
                _LOGGER.warning("🏭 Creating entities for %d new devices...", len(new_devices))
            else:
                _LOGGER.warning("🏭 Creating entities for all discovered devices...")
                new_devices = list(self.device_manager.devices.values())

            # Create entities for each platform
            await self._create_switch_entities(new_devices)
            await self._create_light_entities(new_devices)
            await self._create_binary_sensor_entities(new_devices)

            # Set updated data to trigger entity updates
            self.async_set_updated_data({
                "devices": list(self.device_manager.devices.values()),
                "timestamp": time.time()
            })

        except Exception as err:
            _LOGGER.error("❌ Failed to create entities: %s", err)

    async def _create_switch_entities(self, devices: list[DeviceInfo]) -> None:
        """Create switch entities for discovered devices."""
        if "switch" not in self._platform_callbacks:
            _LOGGER.debug("Switch platform not ready yet")
            return

        # Filter devices that have switch capability
        switch_devices = [d for d in devices if "switch" in d.capabilities]
        if not switch_devices:
            return

        entities = []
        for device in switch_devices:
            if device.channels == 1:
                # Single channel switch
                from .switch import SymiSwitch
                entities.append(SymiSwitch(self, device))
            else:
                # Multi-channel switch - create individual switches for each channel
                for channel in range(1, device.channels + 1):
                    from .switch import SymiSwitch
                    entities.append(SymiSwitch(self, device, channel))

        if entities:
            self._platform_callbacks["switch"](entities)
            _LOGGER.warning("🔌 Created %d switch entities", len(entities))

    async def _create_light_entities(self, devices: list[DeviceInfo]) -> None:
        """Create light entities for discovered devices."""
        if "light" not in self._platform_callbacks:
            _LOGGER.debug("Light platform not ready yet")
            return

        # Filter devices that have brightness capability
        light_devices = [d for d in devices if "brightness" in d.capabilities]
        if not light_devices:
            return

        entities = []
        for device in light_devices:
            from .light import SymiLight
            entities.append(SymiLight(self, device))

        if entities:
            self._platform_callbacks["light"](entities)
            _LOGGER.warning("💡 Created %d light entities", len(entities))

    async def _create_binary_sensor_entities(self, devices: list[DeviceInfo]) -> None:
        """Create binary sensor entities for discovered devices."""
        if "binary_sensor" not in self._platform_callbacks:
            _LOGGER.debug("Binary sensor platform not ready yet")
            return

        # Filter devices that have motion or door capabilities
        motion_devices = [d for d in devices if "motion" in d.capabilities]
        door_devices = [d for d in devices if "door" in d.capabilities]

        entities = []
        for device in motion_devices:
            from .binary_sensor import SymiBinarySensor
            entities.append(SymiBinarySensor(self, device, "motion"))

        for device in door_devices:
            from .binary_sensor import SymiBinarySensor
            entities.append(SymiBinarySensor(self, device, "door"))

        if entities:
            self._platform_callbacks["binary_sensor"](entities)
            _LOGGER.warning("🔍 Created %d binary sensor entities", len(entities))

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data."""
        # This coordinator is event-driven, so we don't need to poll
        return {}

    async def _load_device_data(self) -> None:
        """Load device data from storage."""
        try:
            data = await self._store.async_load()
            if data and "devices" in data:
                _LOGGER.info("💾 Loading %d saved devices from storage", len(data["devices"]))
                self.device_manager.from_dict(data["devices"])
                
                # Update discovered devices cache
                for device in self.device_manager.get_all_devices():
                    self.discovered_devices[device.unique_id] = device
                    
                _LOGGER.info("✅ Successfully loaded device data from storage")
            else:
                _LOGGER.info("🆕 No saved device data found, starting fresh")
        except Exception as err:
            _LOGGER.warning("⚠️ Failed to load device data: %s", err)

    async def _save_device_data(self) -> None:
        """Save device data to storage."""
        try:
            data = {
                "devices": self.device_manager.to_dict(),
                "timestamp": time.time(),
            }
            await self._store.async_save(data)
            _LOGGER.debug("💾 Saved device data to storage")
        except Exception as err:
            _LOGGER.warning("⚠️ Failed to save device data: %s", err)

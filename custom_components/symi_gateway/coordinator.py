"""Coordinator for Symi Gateway."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

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
        
        # Response handling
        self._pending_responses: dict[int, asyncio.Future] = {}
        self._response_timeout = DEFAULT_TIMEOUT

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Connect to gateway
            if not await self.tcp_comm.async_connect():
                _LOGGER.error("❌ Failed to connect to gateway")
                return False
            
            self.is_connected = True
            
            # Register frame callback
            self.tcp_comm.add_frame_callback(self._handle_frame)
            
            # Read existing devices
            await self.async_read_device_list()
            
            _LOGGER.info("✅ Coordinator setup completed")
            return True
            
        except Exception as err:
            _LOGGER.error("❌ Coordinator setup failed: %s", err)
            return False

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
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
        
        for device in devices:
            self.discovered_devices[device.unique_id] = device
            is_new = self.device_manager.add_device(device)
            _LOGGER.warning("📱 Discovered device: %s (%s), new=%s", device.name, device.mac_address, is_new)

        # Trigger entity creation for all platforms
        _LOGGER.warning("🔄 Triggering entity creation for %d devices", len(devices))
        self.hass.async_create_task(self._create_entities_for_devices())

        # Notify entity callbacks
        self._notify_entity_callbacks()

    def _parse_device_list(self, payload: bytes) -> list[DeviceInfo]:
        """Parse device list from payload."""
        devices = []
        offset = 0

        _LOGGER.warning("🔍 Parsing device list payload: %s", payload.hex().upper())

        while offset < len(payload):
            if offset + 16 > len(payload):  # Each device entry is 16 bytes
                break

            try:
                # Parse device entry (16 bytes based on the received data)
                device_data = payload[offset:offset+16]
                _LOGGER.warning("📱 Parsing device entry: %s", device_data.hex().upper())

                # Extract MAC address (6 bytes)
                mac_bytes = device_data[0:6]
                mac_address = ":".join(f"{b:02X}" for b in mac_bytes)

                # Extract network address (2 bytes, little endian)
                network_address = int.from_bytes(device_data[6:8], 'little')

                # Extract device type and other info
                device_type = device_data[8]
                device_sub_type = device_data[9]
                rssi = device_data[10] if device_data[10] < 128 else device_data[10] - 256
                vendor_id = device_data[11]

                # Additional data in bytes 12-15
                extra_data = device_data[12:16]

                device = DeviceInfo(
                    mac_address=mac_address,
                    network_address=network_address,
                    device_type=device_type,
                    device_sub_type=device_sub_type,
                    rssi=rssi,
                    vendor_id=vendor_id,
                    last_seen=time.time(),
                )

                devices.append(device)
                _LOGGER.warning("✅ Parsed device: %s, MAC=%s, type=%d, addr=0x%04X",
                            device.name, mac_address, device_type, network_address)

                offset += 16

            except Exception as err:
                _LOGGER.error("❌ Failed to parse device at offset %d: %s", offset, err)
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

    async def _create_entities_for_devices(self) -> None:
        """Create entities for discovered devices."""
        try:
            _LOGGER.warning("🏭 Creating entities for discovered devices...")

            # Force reload of platforms to create entities
            await self.hass.config_entries.async_reload(self.entry.entry_id)

        except Exception as err:
            _LOGGER.error("❌ Failed to create entities: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data."""
        # This coordinator is event-driven, so we don't need to poll
        return {}

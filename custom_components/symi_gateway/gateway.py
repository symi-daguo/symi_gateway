"""Symi Gateway management."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from .const import (
    OP_START_SCAN,
    OP_STOP_SCAN,
    OP_READ_DEVICE_LIST,
    OP_ADD_DEVICE,
    OP_DELETE_DEVICE,
    OP_CLEAR_ALL_DEVICES,
    OP_READ_DEVICE_COUNT,
    OP_READ_SOFTWARE_VERSION,
    OP_READ_MAC_ADDRESS,
    OP_FACTORY_RESET,
    OP_REBOOT,
    OP_DEVICE_CONTROL,
    OP_SCENE_CONTROL,
    OP_RESP_SCAN,
    OP_RESP_STOP_SCAN,
    OP_RESP_READ_DEVICE_LIST,
    OP_RESP_DEVICE_LIST,
    OP_RESP_ADD_DEVICE,
    OP_RESP_DELETE_DEVICE,
    OP_RESP_CLEAR_ALL_DEVICES,
    OP_RESP_READ_DEVICE_COUNT,
    OP_RESP_READ_SOFTWARE_VERSION,
    OP_RESP_READ_MAC_ADDRESS,
    OP_RESP_FACTORY_RESET,
    OP_RESP_REBOOT,
    OP_RESP_DEVICE_CONTROL,
    OP_RESP_SCENE_CONTROL,
    OP_RESP_DEVICE_STATUS_QUERY,
    OP_EVENT_NODE_NOTIFICATION,
    STATUS_SUCCESS,
    STATUS_SCAN_DISCOVERY_EVENT,
    STATUS_PAIRING_SUCCESS_EVENT,
    STATUS_NODE_STATUS_EVENT,
    DISCOVERY_TIMEOUT,
    SCAN_RESPONSE_TIMEOUT,
    SYMI_VENDOR_ID,
)
from .device_manager import DeviceInfo, DeviceManager
from .protocol import (
    ProtocolFrame,
    build_scan_discovery_frame,
    build_stop_scan_frame,
    build_device_control_frame,
    build_add_device_frame,
    build_read_device_list_frame,
    build_factory_reset_frame,
    build_device_status_query_frame,
    build_scene_control_frame
)

_LOGGER = logging.getLogger(__name__)


class SymiGateway:
    """Symi Gateway manager."""

    def __init__(self, comm):
        """Initialize gateway."""
        self.comm = comm
        self.device_manager = DeviceManager()
        
        # Gateway state
        self.is_scanning = False
        self.scan_start_time: Optional[float] = None
        self.gateway_info: dict[str, Any] = {}

        # 智能状态同步
        self._last_activity_time: Optional[float] = None
        self._sync_timer_handle: Optional[Any] = None
        
        # Callbacks
        self.device_discovered_callbacks: list[Callable[[DeviceInfo], None]] = []
        self.device_state_callbacks: list[Callable[[DeviceInfo], None]] = []
        self.scan_state_callbacks: list[Callable[[bool], None]] = []

        
        # Setup frame callback
        self.comm.add_frame_callback(self._handle_frame)
    
    def add_device_discovered_callback(self, callback: Callable[[DeviceInfo], None]) -> None:
        """Add device discovered callback."""
        self.device_discovered_callbacks.append(callback)
    
    def add_device_state_callback(self, callback: Callable[[DeviceInfo], None]) -> None:
        """Add device state callback."""
        self.device_state_callbacks.append(callback)
    
    def add_scan_state_callback(self, callback: Callable[[bool], None]) -> None:
        """Add scan state callback."""
        self.scan_state_callbacks.append(callback)


    
    def _handle_frame(self, frame: ProtocolFrame) -> None:
        """Handle received protocol frame."""
        _LOGGER.info("🎯 Gateway handling frame: opcode=0x%02X, status=%s", frame.opcode, frame.status)

        # 只有设备控制相关的数据才需要状态同步，查询响应不需要
        if self._is_device_control_frame(frame):
            _LOGGER.debug("📡 Device control frame detected, scheduling status sync")
            self._last_activity_time = time.time()
            self._schedule_status_sync()

        try:
            if frame.opcode == OP_RESP_SCAN:
                self._handle_scan_response(frame)
            elif frame.opcode == OP_RESP_STOP_SCAN:
                self._handle_stop_scan_response(frame)
            elif frame.opcode == OP_RESP_ADD_DEVICE:
                self._handle_add_device_response(frame)
            elif frame.opcode == OP_RESP_READ_DEVICE_LIST or frame.opcode == OP_RESP_DEVICE_LIST:
                self._handle_device_list_response(frame)
            elif frame.opcode == OP_RESP_DEVICE_STATUS_QUERY:
                self._handle_device_status_response(frame)
            elif frame.opcode == OP_RESP_READ_SOFTWARE_VERSION:
                self._handle_software_version_response(frame)
            elif frame.opcode == OP_RESP_READ_MAC_ADDRESS:
                self._handle_mac_address_response(frame)
            elif frame.opcode == OP_RESP_READ_DEVICE_COUNT:
                self._handle_device_count_response(frame)
            elif frame.opcode == OP_EVENT_NODE_NOTIFICATION:
                self._handle_node_event(frame)
            else:
                _LOGGER.warning("🔍 Unhandled frame: opcode=0x%02X, status=%s", frame.opcode, frame.status)
        except Exception as err:
            _LOGGER.error("❌ Error handling frame: %s", err)
    
    def _handle_scan_response(self, frame: ProtocolFrame) -> None:
        """Handle scan response."""
        if frame.status == STATUS_SUCCESS:
            _LOGGER.info("✅ Scan mode started successfully")
            self.is_scanning = True
            self.scan_start_time = time.time()
            self._notify_scan_state_callbacks(True)
            
        elif frame.status == STATUS_SCAN_DISCOVERY_EVENT:
            # Device discovery event
            self._handle_device_discovery(frame)
    
    def _handle_stop_scan_response(self, frame: ProtocolFrame) -> None:
        """Handle stop scan response."""
        if frame.status == STATUS_SUCCESS:
            _LOGGER.info("✅ Scan mode stopped successfully")
            self.is_scanning = False
            self.scan_start_time = None
            self._notify_scan_state_callbacks(False)
    
    def _handle_add_device_response(self, frame: ProtocolFrame) -> None:
        """Handle add device response."""
        if frame.status == STATUS_SUCCESS:
            _LOGGER.info("✅ Device added to whitelist successfully")
        elif frame.status == STATUS_PAIRING_SUCCESS_EVENT:
            # Auto pairing success event
            if len(frame.payload) >= 8:
                mac_bytes = frame.payload[:6]
                network_addr = int.from_bytes(frame.payload[6:8], 'little')
                mac_address = ':'.join([f"{b:02X}" for b in mac_bytes])
                _LOGGER.info("🎉 Device auto-paired: MAC=%s, Address=0x%04X", mac_address, network_addr)

    def _handle_device_list_response(self, frame: ProtocolFrame) -> None:
        """Handle device list response."""
        _LOGGER.warning("🎯 Handling device list response: status=%s, payload_len=%d", frame.status, len(frame.payload))

        if frame.status == STATUS_SUCCESS:
            if len(frame.payload) == 16:
                # Parse device info according to protocol document
                # 16 bytes: max(1) + index(1) + mac(6) + naddr(2) + vendor_id(2) + dev_type(1) + dev_sub_type(1) + status(1) + resv(1)
                max_devices = frame.payload[0]
                index = frame.payload[1]
                mac_bytes = frame.payload[2:8]
                network_addr = int.from_bytes(frame.payload[8:10], 'little')
                vendor_id = int.from_bytes(frame.payload[10:12], 'little')
                dev_type = frame.payload[12]
                dev_sub_type = frame.payload[13]
                status_byte = frame.payload[14]

                online = bool(status_byte & 0x01)
                only_tmall = bool(status_byte & 0x02)

                mac_address = ':'.join([f"{b:02X}" for b in mac_bytes])

                _LOGGER.warning("📋 DEVICE %d/%d: MAC=%s, Addr=0x%04X, VendorID=0x%04X, Type=%d, SubType=%d, Online=%s",
                           index + 1, max_devices, mac_address, network_addr, vendor_id, dev_type, dev_sub_type, online)

                # Create device info
                device = DeviceInfo(
                    mac_address=mac_address,
                    network_address=network_addr,
                    vendor_id=vendor_id,
                    device_type=dev_type,
                    device_sub_type=dev_sub_type,
                    rssi=0,  # Not available in device list
                    online=online
                )

                # Generate unique device ID
                device_id = device.unique_id

                # Only add if not already exists (prevent duplicates)
                if not self.device_manager.has_device(device_id):
                    self.device_manager.add_device(device)
                    self._notify_device_discovered_callbacks(device)
                    _LOGGER.warning("✅ ADDED NEW DEVICE: %s (Type: %d, ID: %s)", device.name, dev_type, device_id)
                    _LOGGER.warning("📋 Device capabilities: %s", device.capabilities)
                    _LOGGER.warning("🔧 Device channels: %d", device.channels)
                else:
                    # Update existing device status
                    self.device_manager.update_device_status(device_id, online)
                    _LOGGER.warning("🔄 UPDATED EXISTING DEVICE: %s (Online: %s)", device_id, online)

            elif len(frame.payload) == 0:
                _LOGGER.warning("📋 DEVICE LIST COMPLETE")
            else:
                _LOGGER.warning("⚠️ Invalid device list payload length: %d, expected 16 or 0", len(frame.payload))
        else:
            _LOGGER.error("❌ Device list response failed with status: %s", frame.status)

    def _handle_device_status_response(self, frame: ProtocolFrame) -> None:
        """Handle device status query response."""
        _LOGGER.warning("📊 Handling device status response: status=%s, payload_len=%d", frame.status, len(frame.payload))

        if frame.status == STATUS_SUCCESS and len(frame.payload) >= 4:
            # Parse device status response
            # This might be a different type of response, log it for analysis
            _LOGGER.warning("📊 Device status payload: %s", frame.payload.hex().upper())
        else:
            _LOGGER.warning("❌ Device status query failed with status: %s", frame.status)

    def _handle_device_discovery(self, frame: ProtocolFrame) -> None:
        """Handle device discovery event."""
        if len(frame.payload) < 16:
            _LOGGER.warning("⚠️ Invalid device discovery payload length: %d", len(frame.payload))
            return
        
        try:
            # Parse discovery data
            rssi_raw = frame.payload[0]
            rssi = rssi_raw if rssi_raw < 128 else rssi_raw - 256
            
            mac_bytes = frame.payload[1:7]
            mac_address = ':'.join([f"{b:02X}" for b in mac_bytes])
            
            vendor_id = int.from_bytes(frame.payload[7:9], 'little')
            device_type = frame.payload[9]
            device_sub_type = frame.payload[10]
            
            _LOGGER.info("🔍 Device discovered:")
            _LOGGER.info("   MAC: %s", mac_address)
            _LOGGER.info("   RSSI: %d dBm", rssi)
            _LOGGER.info("   Vendor ID: 0x%04X", vendor_id)
            _LOGGER.info("   Device Type: %d", device_type)
            _LOGGER.info("   Sub Type: %d", device_sub_type)
            
            # Check if it's a Symi device
            if vendor_id == SYMI_VENDOR_ID:
                # Create device info
                device = DeviceInfo(
                    mac_address=mac_address,
                    network_address=0,  # Will be assigned when added
                    device_type=device_type,
                    device_sub_type=device_sub_type,
                    rssi=rssi,
                    vendor_id=vendor_id,
                    last_seen=time.time(),
                )
                
                # Add device to manager
                is_new = self.device_manager.add_device(device)
                
                if is_new:
                    # Automatically add device to whitelist
                    asyncio.create_task(self._auto_add_device(device))

                    # Notify callbacks
                    self._notify_device_discovered_callbacks(device)
                
            else:
                _LOGGER.debug("🔍 Non-Symi device discovered (vendor_id=0x%04X), ignoring", vendor_id)
                
        except Exception as err:
            _LOGGER.error("❌ Error parsing device discovery: %s", err)
    
    async def _auto_add_device(self, device: DeviceInfo) -> None:
        """Automatically add discovered device to whitelist."""
        try:
            mac_bytes = bytes.fromhex(device.mac_address.replace(":", ""))
            frame_data = build_add_device_frame(mac_bytes, 0)  # 0 = auto-assign address
            
            success = await self.comm.async_send_frame(frame_data)
            if success:
                _LOGGER.info("📡 Auto-adding device to whitelist: %s", device.name)
            else:
                _LOGGER.error("❌ Failed to send add device command for: %s", device.name)
                
        except Exception as err:
            _LOGGER.error("❌ Error auto-adding device: %s", err)
    
    def _handle_node_event(self, frame: ProtocolFrame) -> None:
        """Handle node event."""
        if frame.status == STATUS_NODE_STATUS_EVENT and len(frame.payload) >= 4:
            # Device status event
            network_addr = int.from_bytes(frame.payload[:2], 'little')
            msg_type = frame.payload[2]
            
            if len(frame.payload) > 3:
                value = frame.payload[3]
                
                # Update device state
                device = self.device_manager.update_device_state(network_addr, msg_type, value)
                if device:
                    _LOGGER.info("📊 Device state updated: %s", device.name)
                    self._notify_device_state_callbacks(device)
                else:
                    _LOGGER.warning("⚠️ Received state for unknown device: 0x%04X", network_addr)
    
    def _handle_software_version_response(self, frame: ProtocolFrame) -> None:
        """Handle software version response."""
        if frame.status == STATUS_SUCCESS and len(frame.payload) >= 4:
            version = f"{frame.payload[0]}.{frame.payload[1]}.{frame.payload[2]}.{frame.payload[3]}"
            self.gateway_info["software_version"] = version
            _LOGGER.info("📋 Gateway software version: %s", version)
    
    def _handle_mac_address_response(self, frame: ProtocolFrame) -> None:
        """Handle MAC address response."""
        if frame.status == STATUS_SUCCESS and len(frame.payload) >= 6:
            mac_address = ':'.join([f"{b:02X}" for b in frame.payload[:6]])
            self.gateway_info["mac_address"] = mac_address
            _LOGGER.info("📋 Gateway MAC address: %s", mac_address)
    
    def _handle_device_count_response(self, frame: ProtocolFrame) -> None:
        """Handle device count response."""
        if frame.status == STATUS_SUCCESS and len(frame.payload) >= 1:
            device_count = frame.payload[0]
            self.gateway_info["device_count"] = device_count
            _LOGGER.info("📋 Gateway device count: %d", device_count)
    
    def _notify_device_discovered_callbacks(self, device: DeviceInfo) -> None:
        """Notify device discovered callbacks."""
        for callback in self.device_discovered_callbacks:
            try:
                callback(device)
            except Exception as err:
                _LOGGER.error("❌ Error in device discovered callback: %s", err)
    
    def _notify_device_state_callbacks(self, device: DeviceInfo) -> None:
        """Notify device state callbacks."""
        for callback in self.device_state_callbacks:
            try:
                callback(device)
            except Exception as err:
                _LOGGER.error("❌ Error in device state callback: %s", err)
    
    def _notify_scan_state_callbacks(self, is_scanning: bool) -> None:
        """Notify scan state callbacks."""
        for callback in self.scan_state_callbacks:
            try:
                callback(is_scanning)
            except Exception as err:
                _LOGGER.error("❌ Error in scan state callback: %s", err)
    
    async def start_scan(self) -> bool:
        """Start device scanning."""
        if self.is_scanning:
            _LOGGER.warning("⚠️ Scan already in progress")
            return True
        
        try:
            frame_data = build_scan_discovery_frame()
            success = await self.comm.async_send_frame(frame_data)
            
            if success:
                _LOGGER.info("📡 Scan discovery command sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send scan discovery command")
                return False
                
        except Exception as err:
            _LOGGER.error("❌ Error starting scan: %s", err)
            return False
    
    async def stop_scan(self) -> bool:
        """Stop device scanning."""
        if not self.is_scanning:
            _LOGGER.warning("⚠️ No scan in progress")
            return True
        
        try:
            frame_data = build_stop_scan_frame()
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.info("📡 Stop scan command sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send stop scan command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error stopping scan: %s", err)
            return False

    async def async_read_device_list(self) -> bool:
        """Read device list from gateway."""
        try:
            frame_data = build_read_device_list_frame()
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("📋 Device list request sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send device list request")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error reading device list: %s", err)
            return False

    async def async_factory_reset(self) -> bool:
        """Perform factory reset."""
        try:
            frame_data = build_factory_reset_frame()
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("🏭 Factory reset command sent")
                # Reset internal state
                self.is_scanning = False
                self.scan_remaining_time = 0
                return True
            else:
                _LOGGER.error("❌ Failed to send factory reset command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error performing factory reset: %s", err)
            return False

    async def async_control_device(self, network_addr: int, msg_type: int, param: bytes = b'') -> bool:
        """Control a device."""
        try:
            frame_data = build_device_control_frame(network_addr, msg_type, param)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("🎮 Device control sent: addr=0x%04X, msg_type=0x%02X, param=%s",
                              network_addr, msg_type, param.hex().upper() if param else "None")
                return True
            else:
                _LOGGER.error("❌ Failed to send device control command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error controlling device: %s", err)
            return False

    async def async_query_device_status(self, network_addr: int, msg_type: int = 0) -> bool:
        """Query device status."""
        try:
            frame_data = build_device_status_query_frame(network_addr, msg_type)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("❓ Device status query sent: addr=0x%04X, msg_type=0x%02X",
                              network_addr, msg_type)
                return True
            else:
                _LOGGER.error("❌ Failed to send device status query")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error querying device status: %s", err)
            return False

    async def async_control_scene(self, scene_id: int) -> bool:
        """Control scene."""
        try:
            frame_data = build_scene_control_frame(scene_id)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("🎬 Scene control sent: scene_id=%d", scene_id)
                return True
            else:
                _LOGGER.error("❌ Failed to send scene control command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error controlling scene: %s", err)
            return False

    def _schedule_status_sync(self) -> None:
        """Schedule status sync 1 second after last activity."""
        # 取消之前的定时器
        if self._sync_timer_handle:
            try:
                self._sync_timer_handle.cancel()
            except:
                pass

        # 创建新的定时器，1秒后执行状态同步
        import asyncio
        loop = asyncio.get_event_loop()
        self._sync_timer_handle = loop.call_later(1.0, self._perform_status_sync)
        _LOGGER.debug("⏰ Scheduled status sync in 1 second")

    def _perform_status_sync(self) -> None:
        """Perform status sync by reading device list."""
        _LOGGER.warning("🔄 Auto status sync triggered - reading device list")

        # 异步执行设备列表读取
        import asyncio
        loop = asyncio.get_event_loop()
        asyncio.create_task(self.async_read_device_list())

    def _is_device_control_frame(self, frame: ProtocolFrame) -> bool:
        """Check if frame is device control related (not query response)."""
        # 查询响应帧不需要状态同步
        if frame.opcode in [OP_RESP_DEVICE_LIST, OP_RESP_SCAN, OP_RESP_READ_SOFTWARE_VERSION,
                           OP_RESP_READ_MAC_ADDRESS, OP_RESP_READ_DEVICE_COUNT]:
            return False

        # 设备控制、状态变化等需要状态同步
        if frame.opcode in [OP_RESP_DEVICE_CONTROL, OP_RESP_SCENE_CONTROL]:
            return True

        # 其他设备相关的数据帧
        return True

    async def control_device(self, device: DeviceInfo, msg_type: int, param: int) -> bool:
        """Control a device."""
        try:
            frame_data = build_device_control_frame(device.network_address, msg_type, param)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.info("📡 Device control command sent: %s, msg_type=0x%02X, param=0x%02X",
                           device.name, msg_type, param)
                return True
            else:
                _LOGGER.error("❌ Failed to send device control command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error controlling device: %s", err)
            return False

    async def read_gateway_info(self) -> None:
        """Read gateway information."""
        try:
            # Read software version
            version_frame = self.comm.protocol_handler.build_frame(OP_READ_SOFTWARE_VERSION)
            await self.comm.async_send_frame(version_frame)

            await asyncio.sleep(0.5)

            # Read MAC address
            mac_frame = self.comm.protocol_handler.build_frame(OP_READ_MAC_ADDRESS)
            await self.comm.async_send_frame(mac_frame)

            await asyncio.sleep(0.5)

            # Read device count
            count_frame = self.comm.protocol_handler.build_frame(OP_READ_DEVICE_COUNT)
            await self.comm.async_send_frame(count_frame)

        except Exception as err:
            _LOGGER.error("❌ Error reading gateway info: %s", err)

    async def factory_reset(self) -> bool:
        """Factory reset gateway."""
        try:
            frame_data = self.comm.protocol_handler.build_frame(OP_FACTORY_RESET)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.warning("⚠️ Factory reset command sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send factory reset command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error sending factory reset: %s", err)
            return False

    async def reboot_gateway(self) -> bool:
        """Reboot gateway."""
        try:
            frame_data = self.comm.protocol_handler.build_frame(OP_REBOOT)
            success = await self.comm.async_send_frame(frame_data)

            if success:
                _LOGGER.info("🔄 Reboot command sent")
                return True
            else:
                _LOGGER.error("❌ Failed to send reboot command")
                return False

        except Exception as err:
            _LOGGER.error("❌ Error sending reboot: %s", err)
            return False

    @property
    def scan_remaining_time(self) -> int:
        """Get remaining scan time in seconds."""
        if not self.is_scanning or not self.scan_start_time:
            return 0

        elapsed = time.time() - self.scan_start_time
        remaining = max(0, DISCOVERY_TIMEOUT - int(elapsed))
        return remaining

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all managed devices."""
        return self.device_manager.get_all_devices()

    def get_device_by_id(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device by ID."""
        return self.device_manager.get_device(device_id)

    def get_devices_by_capability(self, capability: str) -> list[DeviceInfo]:
        """Get devices by capability."""
        return self.device_manager.get_devices_by_capability(capability)

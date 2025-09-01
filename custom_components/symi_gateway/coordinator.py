"""Coordinator for Symi Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SERIAL_PORT,
    CONF_BAUDRATE,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_TCP,
    DOMAIN,
    PLATFORMS
)
from .device_manager import DeviceInfo
from .gateway import SymiGateway
from .serial_comm import SerialCommunication
from .tcp_comm import TCPCommunication
from .storage import SymiStorage

_LOGGER = logging.getLogger(__name__)


class SymiGatewayCoordinator(DataUpdateCoordinator):
    """Symi Gateway coordinator."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        
        self.entry = entry
        self.hass = hass
        
        # Core components
        self.comm: SerialCommunication | TCPCommunication | None = None
        self.gateway: SymiGateway | None = None
        self.storage: SymiStorage | None = None
        
        # State
        self.is_scanning = False
        self.discovered_devices: dict[str, DeviceInfo] = {}
        
        # Setup lock
        self._setup_lock = asyncio.Lock()
        self._setup_complete = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data."""
        if not self._setup_complete:
            return {}

        return {
            "devices": {device_id: device.to_dict() for device_id, device in self.discovered_devices.items()},
            "gateway_info": self.gateway.gateway_info if self.gateway else {},
            "is_scanning": self.is_scanning,
            "scan_remaining": self.gateway.scan_remaining_time if self.gateway else 0,
        }
    

    
    async def async_setup(self) -> None:
        """Set up the coordinator."""
        async with self._setup_lock:
            if self._setup_complete:
                return
            
            try:
                await self._async_setup_storage()
                await self._async_setup_communication()
                await self._async_setup_gateway()
                await self._async_load_devices()
                
                self._setup_complete = True
                _LOGGER.info("✅ Symi Gateway coordinator setup complete")

                # Read existing device list from gateway
                _LOGGER.info("📋 Reading existing device list...")
                await self.async_read_device_list()

                # Trigger initial data update
                try:
                    await self.async_config_entry_first_refresh()
                except AttributeError:
                    # Fallback for older HA versions
                    await self.async_refresh()
                
            except Exception as err:
                _LOGGER.error("❌ Failed to setup coordinator: %s", err)
                raise UpdateFailed(f"Setup failed: {err}") from err
    
    async def _async_setup_storage(self) -> None:
        """Setup storage."""
        self.storage = SymiStorage(self.hass, self.entry.entry_id)
        _LOGGER.debug("📂 Storage initialized")
    
    async def _async_setup_communication(self) -> None:
        """Setup communication (serial or TCP)."""
        connection_type = self.entry.data[CONF_CONNECTION_TYPE]

        if connection_type == CONNECTION_TYPE_SERIAL:
            port = self.entry.data[CONF_SERIAL_PORT]
            baudrate = self.entry.data[CONF_BAUDRATE]

            _LOGGER.info("🔧 Setting up serial communication:")
            _LOGGER.info("   Port: %s", port)
            _LOGGER.info("   Baudrate: %d", baudrate)

            self.comm = SerialCommunication(port, baudrate)

            if not await self.comm.async_connect():
                raise UpdateFailed(f"Failed to connect to serial port {port}")

            _LOGGER.info("✅ Serial communication setup completed")

        elif connection_type == CONNECTION_TYPE_TCP:
            host = self.entry.data[CONF_TCP_HOST]
            port = self.entry.data[CONF_TCP_PORT]

            _LOGGER.info("🔧 Setting up TCP communication:")
            _LOGGER.info("   Host: %s", host)
            _LOGGER.info("   Port: %d", port)

            self.comm = TCPCommunication(host, port)

            if not await self.comm.async_connect():
                raise UpdateFailed(f"Failed to connect to TCP server {host}:{port}")

            _LOGGER.info("✅ TCP communication setup completed")

        else:
            raise UpdateFailed(f"Unsupported connection type: {connection_type}")
    
    async def _async_setup_gateway(self) -> None:
        """Setup gateway."""
        if not self.comm:
            raise UpdateFailed("Communication not initialized")

        self.gateway = SymiGateway(self.comm)
        
        # Setup callbacks
        self.gateway.add_device_discovered_callback(self._on_device_discovered)
        self.gateway.add_device_state_callback(self._on_device_state_changed)
        self.gateway.add_scan_state_callback(self._on_scan_state_changed)
        
        # Read gateway information
        await self.gateway.read_gateway_info()

        # Read device list from gateway to get all current devices
        _LOGGER.info("📋 Reading device list from gateway...")
        await self.gateway.async_read_device_list()

        # Wait a moment for device list response to be processed
        await asyncio.sleep(2)

        # Update discovered devices cache from device manager
        if self.gateway.device_manager:
            for device in self.gateway.device_manager.get_all_devices():
                if device.unique_id not in self.discovered_devices:
                    self.discovered_devices[device.unique_id] = device
                    _LOGGER.info("📱 New device discovered: %s (Type: %d, Capabilities: %s)",
                               device.name, device.device_type, device.capabilities)
                else:
                    # Update existing device info but keep the same unique_id
                    self.discovered_devices[device.unique_id] = device
                    _LOGGER.info("📱 Updated existing device: %s", device.name)

        # Trigger initial data update to create entities for loaded devices
        await self.async_refresh()

        _LOGGER.info("✅ Gateway setup completed with %d devices", len(self.discovered_devices))

    async def async_refresh_devices(self) -> None:
        """Refresh device list and create new entities for newly discovered devices."""
        if not self.gateway:
            _LOGGER.warning("⚠️ Gateway not initialized, cannot refresh devices")
            return

        _LOGGER.info("🔄 Refreshing device list...")

        # Store current device count
        old_device_count = len(self.discovered_devices)

        # Read device list from gateway
        await self.gateway.async_read_device_list()

        # Wait for response processing
        await asyncio.sleep(2)

        # Update discovered devices cache from device manager
        new_devices = []
        if self.gateway.device_manager:
            for device in self.gateway.device_manager.get_all_devices():
                if device.unique_id not in self.discovered_devices:
                    self.discovered_devices[device.unique_id] = device
                    new_devices.append(device)
                    _LOGGER.info("🆕 Found new device: %s (Type: %d, Capabilities: %s)",
                               device.name, device.device_type, device.capabilities)
                else:
                    # Update existing device info
                    self.discovered_devices[device.unique_id] = device

        # Trigger data update to notify entity platforms
        await self.async_refresh()

        new_device_count = len(self.discovered_devices)
        _LOGGER.info("✅ Device refresh completed: %d total devices (%d new)",
                   new_device_count, new_device_count - old_device_count)

        return new_devices
    
    async def _async_load_devices(self) -> None:
        """Load devices from storage."""
        if not self.storage or not self.gateway:
            return
        
        try:
            stored_devices = await self.storage.async_load_devices()
            
            # Load devices into device manager
            self.gateway.device_manager.from_dict(stored_devices)
            
            # Update local cache
            self.discovered_devices = {
                device.unique_id: device 
                for device in self.gateway.device_manager.get_all_devices()
            }
            
            _LOGGER.info("📂 Loaded %d devices from storage", len(self.discovered_devices))
            
        except Exception as err:
            _LOGGER.error("❌ Failed to load devices: %s", err)
    
    async def _async_save_devices(self) -> None:
        """Save devices to storage."""
        if not self.storage or not self.gateway:
            return
        
        try:
            device_data = self.gateway.device_manager.to_dict()
            await self.storage.async_save_devices(device_data)
            _LOGGER.debug("💾 Devices saved to storage")
        except Exception as err:
            _LOGGER.error("❌ Failed to save devices: %s", err)
    
    def _on_device_discovered(self, device: DeviceInfo) -> None:
        """Handle device discovered."""
        _LOGGER.warning("🆕 Device discovered: %s (Type: %d, Capabilities: %s)",
                       device.name, device.device_type, device.capabilities)
        
        # Update local cache
        self.discovered_devices[device.unique_id] = device
        
        # Save to storage
        self.hass.async_create_task(self._async_save_devices())
        
        # Trigger update
        self.async_update_listeners()

        _LOGGER.warning("🔄 Triggered coordinator update for new device: %s", device.name)
    
    def _on_device_state_changed(self, device: DeviceInfo) -> None:
        """Handle device state changed."""
        _LOGGER.debug("📊 Device state changed: %s", device.name)
        
        # Update local cache
        self.discovered_devices[device.unique_id] = device
        
        # Save to storage
        self.hass.async_create_task(self._async_save_devices())
        
        # Trigger update
        self.async_update_listeners()
    
    def _on_scan_state_changed(self, is_scanning: bool) -> None:
        """Handle scan state changed."""
        _LOGGER.info("🔍 Scan state changed: %s", "scanning" if is_scanning else "stopped")
        self.is_scanning = is_scanning

        # Trigger update
        self.async_update_listeners()


    
    async def _async_forward_device_setup(self, device: DeviceInfo) -> None:
        """Forward device setup to appropriate platforms."""
        try:
            # Determine which platforms this device needs
            platforms_needed = []
            
            if device.is_switch:
                platforms_needed.append("switch")
            if device.is_light:
                platforms_needed.append("light")
            if device.is_cover:
                platforms_needed.append("cover")
            if device.is_sensor:
                platforms_needed.append("sensor")
            if device.is_binary_sensor:
                platforms_needed.append("binary_sensor")
            if device.is_climate:
                platforms_needed.append("climate")
            
            # Forward to platforms
            for platform in platforms_needed:
                if platform in PLATFORMS:
                    _LOGGER.debug("🔄 Forwarding device %s to platform %s", device.name, platform)
                    # The platform will pick up the new device on next update
            
        except Exception as err:
            _LOGGER.error("❌ Error forwarding device setup: %s", err)
    
    async def async_start_scan(self) -> bool:
        """Start device scanning."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False
        
        return await self.gateway.start_scan()
    
    async def async_stop_scan(self) -> bool:
        """Stop device scanning."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        return await self.gateway.stop_scan()

    async def async_factory_reset(self) -> bool:
        """Perform factory reset."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        _LOGGER.warning("⚠️ Performing factory reset - all device configurations will be lost!")
        success = await self.gateway.async_factory_reset()

        if success:
            # Clear local device storage
            self.discovered_devices.clear()
            await self.storage.async_save_devices({})
            await self.async_update_listeners()
            _LOGGER.warning("✅ Factory reset completed - all devices cleared")

        return success

    async def async_read_device_list(self) -> bool:
        """Read device list from gateway."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        return await self.gateway.async_read_device_list()

    async def async_control_device(self, network_addr: int, msg_type: int, param: bytes = b'') -> bool:
        """Control a device by network address."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        return await self.gateway.async_control_device(network_addr, msg_type, param)

    async def async_query_device_status(self, network_addr: int, msg_type: int = 0) -> bool:
        """Query device status by network address."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        return await self.gateway.async_query_device_status(network_addr, msg_type)

    async def async_control_scene(self, scene_id: int) -> bool:
        """Control scene."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        return await self.gateway.async_control_scene(scene_id)

    async def async_control_device_by_id(self, device_id: str, msg_type: int, param: bytes = b'') -> bool:
        """Control a device by device ID."""
        if not self.gateway:
            _LOGGER.error("❌ Gateway not initialized")
            return False

        # Find device by ID in device manager
        device = self.gateway.device_manager.get_device(device_id)
        if not device:
            _LOGGER.error("❌ Device not found: %s", device_id)
            return False

        # Control device using network address
        _LOGGER.warning("🎮 Controlling device: %s (addr=0x%04X, msg_type=0x%02X)",
                       device.name, device.network_address, msg_type)
        return await self.gateway.async_control_device(device.network_address, msg_type, param)
    
    async def async_factory_reset(self) -> bool:
        """Factory reset gateway."""
        if not self.gateway:
            return False
        
        success = await self.gateway.factory_reset()
        if success and self.storage:
            # Clear stored data
            await self.storage.async_clear_all_data()
            self.discovered_devices.clear()
        
        return success
    
    async def async_reboot_gateway(self) -> bool:
        """Reboot gateway."""
        if not self.gateway:
            return False
        
        return await self.gateway.reboot_gateway()
    
    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Get device by ID."""
        return self.discovered_devices.get(device_id)
    
    def get_devices_by_capability(self, capability: str) -> list[DeviceInfo]:
        """Get devices by capability."""
        return [
            device for device in self.discovered_devices.values()
            if capability in device.capabilities
        ]
    
    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        _LOGGER.info("🛑 Shutting down Symi Gateway coordinator")
        
        # Stop scanning
        if self.gateway and self.is_scanning:
            await self.gateway.stop_scan()
        
        # Save devices
        await self._async_save_devices()
        
        # Disconnect communication
        if self.comm:
            await self.comm.async_disconnect()
        
        _LOGGER.info("✅ Coordinator shutdown complete")

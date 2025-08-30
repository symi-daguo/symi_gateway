"""The Symi Gateway integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SymiGatewayCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Symi Gateway from a config entry."""
    _LOGGER.info("🚀 Setting up Symi Gateway integration")
    
    # Create coordinator
    coordinator = SymiGatewayCoordinator(hass, entry)
    
    # Setup coordinator
    await coordinator.async_setup()
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Register services
    await _async_register_services(hass, coordinator)
    
    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("✅ Symi Gateway integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("🛑 Unloading Symi Gateway integration")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Shutdown coordinator
        coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()
        
        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)
    
    _LOGGER.info("✅ Symi Gateway integration unloaded")
    return unload_ok


async def _async_register_services(hass: HomeAssistant, coordinator: SymiGatewayCoordinator) -> None:
    """Register integration services."""
    
    async def start_scan_service(call):
        """Start device scanning service."""
        success = await coordinator.async_start_scan()
        if success:
            _LOGGER.info("📡 Device scanning started via service")
        else:
            _LOGGER.error("❌ Failed to start device scanning via service")
    
    async def stop_scan_service(call):
        """Stop device scanning service."""
        success = await coordinator.async_stop_scan()
        if success:
            _LOGGER.info("🛑 Device scanning stopped via service")
        else:
            _LOGGER.error("❌ Failed to stop device scanning via service")
    
    async def factory_reset_service(call):
        """Factory reset gateway service."""
        success = await coordinator.async_factory_reset()
        if success:
            _LOGGER.warning("⚠️ Gateway factory reset completed via service")
        else:
            _LOGGER.error("❌ Failed to factory reset gateway via service")
    
    async def reboot_gateway_service(call):
        """Reboot gateway service."""
        success = await coordinator.async_reboot_gateway()
        if success:
            _LOGGER.info("🔄 Gateway reboot initiated via service")
        else:
            _LOGGER.error("❌ Failed to reboot gateway via service")
    
    # Register services
    hass.services.async_register(DOMAIN, "start_scan", start_scan_service)
    hass.services.async_register(DOMAIN, "stop_scan", stop_scan_service)
    hass.services.async_register(DOMAIN, "factory_reset", factory_reset_service)
    hass.services.async_register(DOMAIN, "reboot_gateway", reboot_gateway_service)
    
    _LOGGER.info("📋 Services registered")


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister integration services."""
    hass.services.async_remove(DOMAIN, "start_scan")
    hass.services.async_remove(DOMAIN, "stop_scan")
    hass.services.async_remove(DOMAIN, "factory_reset")
    hass.services.async_remove(DOMAIN, "reboot_gateway")
    
    _LOGGER.info("📋 Services unregistered")

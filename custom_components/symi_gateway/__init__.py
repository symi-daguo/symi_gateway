"""The Symi Gateway integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
import homeassistant.helpers.device_registry as dr

from .const import DOMAIN, SUPPORTED_DOMAINS, DEFAULT_TCP_PORT
from .coordinator import SymiGatewayCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Symi Gateway from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_TCP_PORT)

    # Create coordinator
    coordinator = SymiGatewayCoordinator(hass, entry, host, port)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up coordinator
    try:
        if not await coordinator.async_setup():
            _LOGGER.error("❌ Failed to setup coordinator")
            return False
        _LOGGER.info("✅ Connected to Symi Gateway at %s:%d", host, port)
    except Exception as err:
        _LOGGER.error("❌ Failed to connect to gateway: %s", err)
        return False

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_DOMAINS)

    # Register stop handler
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.async_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_DOMAINS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.async_shutdown()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Remove a config entry device."""
    return True

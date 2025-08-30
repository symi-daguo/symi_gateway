"""Data storage for Symi Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_devices"


class SymiStorage:
    """Handles persistent storage for Symi Gateway."""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        """Initialize storage."""
        self.hass = hass
        self.entry_id = entry_id
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
    
    async def async_load_devices(self) -> dict[str, Any]:
        """Load devices from storage."""
        try:
            data = await self.store.async_load()
            if data and isinstance(data, dict):
                devices = data.get("devices", {})
                _LOGGER.info("📂 Loaded %d devices from storage", len(devices))
                return devices
            else:
                _LOGGER.info("📂 No device data found in storage")
                return {}
        except Exception as err:
            _LOGGER.error("❌ Failed to load devices from storage: %s", err)
            return {}
    
    async def async_save_devices(self, devices: dict[str, Any]) -> None:
        """Save devices to storage."""
        try:
            data = {
                "devices": devices,
                "version": STORAGE_VERSION,
                "entry_id": self.entry_id,
            }
            await self.store.async_save(data)
            _LOGGER.debug("💾 Saved %d devices to storage", len(devices))
        except Exception as err:
            _LOGGER.error("❌ Failed to save devices to storage: %s", err)
    
    async def async_load_gateway_config(self) -> dict[str, Any]:
        """Load gateway configuration."""
        try:
            data = await self.store.async_load()
            if data and isinstance(data, dict):
                config = data.get("gateway_config", {})
                _LOGGER.debug("📂 Loaded gateway config from storage")
                return config
            else:
                return {}
        except Exception as err:
            _LOGGER.error("❌ Failed to load gateway config: %s", err)
            return {}
    
    async def async_save_gateway_config(self, config: dict[str, Any]) -> None:
        """Save gateway configuration."""
        try:
            data = await self.store.async_load() or {}
            data["gateway_config"] = config
            await self.store.async_save(data)
            _LOGGER.debug("💾 Saved gateway config to storage")
        except Exception as err:
            _LOGGER.error("❌ Failed to save gateway config: %s", err)
    
    async def async_clear_all_data(self) -> None:
        """Clear all stored data."""
        try:
            await self.store.async_remove()
            _LOGGER.info("🗑️ Cleared all stored data")
        except Exception as err:
            _LOGGER.error("❌ Failed to clear stored data: %s", err)

"""The Symi Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity
import homeassistant.helpers.device_registry as dr

from .const import DOMAIN, SUPPORTED_DOMAINS, DEFAULT_TCP_PORT
from .gateway import SymiGateway

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Symi Gateway from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_TCP_PORT)

    # Create gateway instance
    gateway = SymiGateway(host, port=port, hass=hass, entry=entry)

    # Store gateway instance
    hass.data[DOMAIN][entry.entry_id] = gateway

    # Start gateway and discover devices
    try:
        await gateway.start()
        _LOGGER.info("✅ Connected to Symi Gateway at %s:%d", host, port)
    except Exception as err:
        _LOGGER.error("❌ Failed to connect to gateway: %s", err)
        return False

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_DOMAINS)

    # Register stop handler
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, gateway.stop)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_DOMAINS)
    if unload_ok:
        gateway = hass.data[DOMAIN].pop(entry.entry_id, None)
        if gateway:
            await gateway.stop()
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Remove a config entry device."""
    return True


async def async_add_setuper(hass: HomeAssistant, config_entry: ConfigEntry, domain: str, async_add_entities):
    """Add entity setuper for a domain."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]
    gateway.add_setup(domain, async_add_entities)


class SymiEntity(Entity):
    """Base Symi entity."""

    def __init__(self, device, conv):
        """Initialize entity."""
        self.device = device
        self._name = conv.attr if hasattr(conv, 'attr') else 'unknown'
        self._attr_name = f"{device.name} {self._name}".strip()
        self._attr_unique_id = f"{device.id}-{self._name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=device.name,
            manufacturer="Symi",
            model=f"Type {getattr(device, 'type', 'Unknown')}",
        )
        self._attr_extra_state_attributes = {}
        self.subscribed_attrs = device.subscribe_attrs(conv)
        self.added = False

        # Store entity in device
        device.entities[conv.attr] = self

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self.added = True
        await super().async_added_to_hass()

    def async_set_state(self, data: dict):
        """Handle state update from gateway."""
        if self._name in data:
            self._attr_state = data[self._name]
        for k in self.subscribed_attrs:
            if k not in data:
                continue
            self._attr_extra_state_attributes[k] = data[k]

    async def device_send_props(self, props: dict):
        """Send properties to device."""
        return await self.device.set_prop(**props)

"""Switch platform for Symi Gateway - TCP based like Yeelight Pro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MSG_TYPE_SWITCH_CONTROL
from .coordinator import SymiGatewayCoordinator
from .device_manager import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Symi Gateway switch entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Get switch devices
    switch_devices = coordinator.get_devices_by_capability("switch")

    entities = []
    for device in switch_devices:
        if device.channels == 1:
            # Single channel switch
            entities.append(SymiSwitch(coordinator, device))
        else:
            # Multi-channel switch - create individual switches for each channel
            for channel in range(1, device.channels + 1):
                entities.append(SymiSwitch(coordinator, device, channel))

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d switch entities", len(entities))


class SymiSwitch(CoordinatorEntity, SwitchEntity):
    """Symi switch entity."""

    def __init__(self, coordinator: SymiGatewayCoordinator, device: DeviceInfo, channel: int = 1) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device = device
        self._channel = channel

        if device.channels == 1:
            self._attr_name = f"{device.name}"
            self._attr_unique_id = f"{DOMAIN}_{device.unique_id}_switch"
        else:
            self._attr_name = f"{device.name} 通道{channel}"
            self._attr_unique_id = f"{DOMAIN}_{device.unique_id}_switch_{channel}"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device.unique_id)},
            "name": self._device.name,
            "manufacturer": "Symi",
            "model": f"Smart Switch Type {self._device.device_type}",
            "sw_version": "1.0",
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        if self._device.channels == 1:
            return self._device.get_state("switch") or False
        else:
            return self._device.get_state(f"switch_{self._channel}") or False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._device.channels == 1:
            # Single channel switch
            param = bytes([0x02])  # Turn on
        else:
            # Multi-channel switch
            channel_mask = 1 << (self._channel - 1)
            param = bytes([channel_mask, 0x02])  # Channel mask + turn on

        success = await self.coordinator.async_control_device(
            self._device.network_address,
            MSG_TYPE_SWITCH_CONTROL,
            param
        )

        if not success:
            _LOGGER.error("Failed to turn on switch: %s", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._device.channels == 1:
            # Single channel switch
            param = bytes([0x01])  # Turn off
        else:
            # Multi-channel switch
            channel_mask = 1 << (self._channel - 1)
            param = bytes([channel_mask, 0x01])  # Channel mask + turn off

        success = await self.coordinator.async_control_device(
            self._device.network_address,
            MSG_TYPE_SWITCH_CONTROL,
            param
        )

        if not success:
            _LOGGER.error("Failed to turn off switch: %s", self._attr_name)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._device.online and self.coordinator.available

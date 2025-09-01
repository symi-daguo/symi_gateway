"""The Symi Gateway integration - TCP based like Yeelight Pro."""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.reload import (
    async_integration_yaml_config,
    async_reload_integration_platforms,
)
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, SUPPORTED_DOMAINS, DEFAULT_NAME
from .gateway import SymiGateway
from .device import SymiDevice, GatewayDevice
from .converters.base import Converter

_LOGGER = logging.getLogger(__name__)


def init_integration_data(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault('gateways', {})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    init_integration_data(hass)
    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_DOMAINS)

    if gtw := await get_gateway_from_config(hass, entry):
        await gtw.start()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, gtw.stop)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_DOMAINS)
    if unload_ok:
        gtw = hass.data[DOMAIN]['gateways'].pop(entry.entry_id, None)
        if gtw:
            await gtw.stop()
    return unload_ok


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry):
    """Supported from Hass v2022.3"""
    dr.async_get(hass).async_remove_device(device.id)


async def async_add_setuper(hass: HomeAssistant, config, domain, setuper):
    gtw = await get_gateway_from_config(hass, config)
    if isinstance(gtw, SymiGateway):
        gtw.add_setup(domain, setuper)


async def get_gateway_from_config(hass, config, renew=False):
    if isinstance(config, ConfigEntry):
        cfg = {
            **config.data,
            **config.options,
            'hass': hass,
            'entry_id': config.entry_id,
            'config_entry': config,
        }
    else:
        cfg = {
            **config,
            'hass': hass,
            'entry_id': config.get(CONF_HOST),
        }
    if not (eid := cfg.get('entry_id')):
        _LOGGER.warning('Config invalid: %s', cfg)
        return None
    host = cfg.pop(CONF_HOST, None)
    if renew:
        return SymiGateway(host, **cfg)
    gtw = hass.data[DOMAIN]['gateways'].get(eid)
    if not gtw:
        gtw = SymiGateway(host, **cfg)
        hass.data[DOMAIN]['gateways'][eid] = gtw
    return gtw


class SymiEntity(Entity):
    added = False
    _attr_should_poll = False

    def __init__(self, device: SymiDevice, conv: Converter, option=None):
        self.device = device
        self.hass = device.hass
        self._name = conv.attr
        self._option = option or {}
        self._attr_name = f'{device.name} {conv.attr}'.strip()
        self._attr_unique_id = f'{device.id}-{conv.attr}'
        self.entity_id = device.entity_id(conv)
        self._attr_icon = self._option.get('icon')
        self._attr_entity_picture = self._option.get('picture')
        self._attr_device_class = self._option.get('class') or conv.device_class
        self._attr_native_unit_of_measurement = conv.unit_of_measurement
        self._attr_entity_category = self._option.get('category')
        self._attr_translation_key = self._option.get('translation_key', conv.attr)

        via_device = None
        if not isinstance(device, GatewayDevice):
            via_device = (DOMAIN, device.gateway.device.id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=device.name,
            model=f'Type {device.type}' or '',
            via_device=via_device,
            manufacturer=DEFAULT_NAME,
        )
        self._attr_extra_state_attributes = {}
        self._vars = {}
        self.subscribed_attrs = device.subscribe_attrs(conv)
        device.entities[conv.attr] = self

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self.added = True
        await super().async_added_to_hass()

    @callback
    def async_set_state(self, data: dict):
        """Handle state update from gateway."""
        if self._name in data:
            self._attr_state = data[self._name]
        for k in self.subscribed_attrs:
            if k not in data:
                continue
            self._attr_extra_state_attributes[k] = data[k]
        _LOGGER.debug('%s: State changed: %s', self.entity_id, data)

    async def device_send_props(self, value: dict):
        payload = self.device.encode(value)
        if not payload:
            return False
        return await self.device.set_prop(**payload)

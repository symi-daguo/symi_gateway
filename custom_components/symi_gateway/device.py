"""Symi Device classes - based on Yeelight Pro architecture."""
from __future__ import annotations

import asyncio
import logging
from enum import IntEnum
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from . import SymiEntity
    from .gateway import SymiGateway
    from homeassistant.core import HomeAssistant

from .converters.base import *

_LOGGER = logging.getLogger(__name__)


class NodeType(IntEnum):
    GATEWAY = -1
    DEVICE = 1
    GROUP = 2
    SCENE = 3


class DeviceType(IntEnum):
    SWITCH_1CH = 1      # 单路开关
    SWITCH_2CH = 2      # 双路开关  
    SWITCH_3CH = 3      # 三路开关
    LIGHT_DIMMER = 4    # 调光灯
    MOTION_SENSOR = 8   # 人体感应
    LIGHT_CCT = 24      # 双色温调光灯


DEVICE_TYPE_LIGHTS = [
    DeviceType.LIGHT_DIMMER,
    DeviceType.LIGHT_CCT,
]

DEVICE_TYPE_SWITCHES = [
    DeviceType.SWITCH_1CH,
    DeviceType.SWITCH_2CH,
    DeviceType.SWITCH_3CH,
]


class SymiDevice:
    hass: "HomeAssistant" = None
    converters: Dict[str, Converter] = None

    def __init__(self, node: dict):
        self.id = str(node.get('id', ''))
        self.nt = node.get('nt', NodeType.DEVICE)
        self.type = node.get('type', 0)
        self.name = node.get('name', f'Symi Device {self.id}')
        self.mac_address = node.get('mac_address', '')
        self.network_address = node.get('network_address', 0)
        self.vendor_id = node.get('vendor_id', 0)
        self.device_sub_type = node.get('device_sub_type', 0)
        self.prop = {}
        self.entities: Dict[str, "SymiEntity"] = {}
        self.gateways: List["SymiGateway"] = []
        self.converters = {}
        self.setup_converters()

    def setup_converters(self):
        pass

    def add_converter(self, conv: Converter):
        self.converters[conv.attr] = conv

    def add_converters(self, *args: Converter):
        for conv in args:
            self.add_converter(conv)

    @staticmethod
    async def from_node(gateway: "SymiGateway", node: dict):
        if not (nid := str(node.get('id', ''))):
            return None
        
        if dvc := gateway.devices.get(nid):
            if name := node.get('name'):
                dvc.name = name
        else:
            device_type = node.get('type', 0)
            if device_type in DEVICE_TYPE_LIGHTS:
                dvc = LightDevice(node)
            elif device_type in DEVICE_TYPE_SWITCHES:
                dvc = SwitchDevice(node)
            elif device_type == DeviceType.MOTION_SENSOR:
                dvc = MotionDevice(node)
            else:
                dvc = SymiDevice(node)
            
            await gateway.add_device(dvc)
        return dvc

    async def prop_changed(self, data: dict):
        has_new = False
        for k in data.keys():
            if k not in self.prop:
                has_new = True
                break
        self.prop.update(data)
        if has_new:
            self.setup_converters()
            await self.setup_entities()
        self.update(self.decode(data))

    async def event_fired(self, data: dict):
        decoded = self.decode_event(data)
        self.update(decoded)
        _LOGGER.debug('Event fired: %s', [data, decoded])

    @property
    def gateway(self):
        if self.gateways:
            return self.gateways[0]
        return None

    @property
    def online(self):
        return self.prop.get('online', True)

    @property
    def unique_id(self):
        return f'symi_{self.type}_{self.id}'

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.symi_{self.unique_id}_{conv.attr}'

    async def setup_entities(self):
        if not (gateway := self.gateway):
            return
        if not self.converters:
            _LOGGER.warning('Device has none converters: %s', [type(self), self.id])
        for conv in self.converters.values():
            domain = conv.domain
            if domain is None:
                continue
            if conv.attr in self.entities:
                continue
            await asyncio.sleep(0.1)  # wait for setup
            await gateway.setup_entity(domain, self, conv)

    def subscribe_attrs(self, conv: Converter):
        attrs = {conv.attr}
        if conv.childs:
            attrs |= set(conv.childs)
        attrs.update(c.attr for c in self.converters.values() if c.parent == conv.attr)
        return attrs

    def decode(self, value: dict) -> dict:
        """Decode device props for HA."""
        payload = {}
        for conv in self.converters.values():
            prop = conv.prop or conv.attr
            if prop not in value:
                continue
            conv.decode(self, payload, value[prop])
        return payload

    def decode_event(self, data: dict) -> dict:
        """Decode device event for HA."""
        payload = {}
        event = data.get('event') or data.get('type')
        if conv := self.converters.get(event):
            value = data.get('value', {})
            conv.decode(self, payload, value)
        return payload

    def encode(self, value: dict) -> dict:
        """Encode payload for device."""
        payload = {}
        for conv in self.converters.values():
            if conv.attr not in value:
                continue
            conv.encode(self, payload, value[conv.attr])
        return payload

    def update(self, value: dict):
        """Push new state to Hass entities."""
        if not value:
            return
        attrs = value.keys()

        for entity in self.entities.values():
            if not (entity.subscribed_attrs & attrs):
                continue
            entity.async_set_state(value)
            if entity.added:
                entity.async_write_ha_state()

    async def set_prop(self, **kwargs):
        if not self.gateway:
            return None
        
        # Convert HA commands to Symi protocol
        payload = self.encode(kwargs)
        if not payload:
            return False
            
        # Send control command via gateway
        return await self.gateway.send('device_control', 
                                     device_id=self.id, 
                                     **payload)


class GatewayDevice(SymiDevice):
    def __init__(self, gateway: "SymiGateway"):
        super().__init__({
            'id': 'gateway',
            'nt': NodeType.GATEWAY,
            'type': 'gateway',
            'name': 'Symi Gateway'
        })
        self.id = gateway.host

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.symi_gateway_{conv.attr}'


class LightDevice(SymiDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(BoolConv('light', 'light'))
        if self.type == DeviceType.LIGHT_DIMMER:
            self.add_converter(BrightnessConv('brightness', parent='light'))
        elif self.type == DeviceType.LIGHT_CCT:
            self.add_converter(BrightnessConv('brightness', parent='light'))
            self.add_converter(ColorTempConv('color_temp', parent='light'))


class SwitchDevice(SymiDevice):
    def setup_converters(self):
        super().setup_converters()
        channels = self.device_sub_type or 1
        if channels == 1:
            self.add_converter(BoolConv('switch', 'switch'))
        else:
            for i in range(1, channels + 1):
                self.add_converter(BoolConv(f'switch_{i}', 'switch'))


class MotionDevice(SymiDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(BoolConv('motion', 'binary_sensor'))

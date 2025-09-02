"""Symi Gateway management - TCP based like Yeelight Pro."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Callable, Dict, List, Optional, Union

from .const import DOMAIN, SYMI_VENDOR_ID
from .device import SymiDevice, GatewayDevice
from .converters.base import Converter

_LOGGER = logging.getLogger(__name__)
MSG_SPLIT = b'\r\n'

_LOGGER = logging.getLogger(__name__)


class SymiGateway:
    """Symi Gateway manager - TCP based like Yeelight Pro."""

    host: str = None
    port: int = 4196  # Symi gateway TCP port
    device: "SymiDevice" = None

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    main_task: Optional[asyncio.Task] = None

    def __init__(self, host: str, port: int = 4196, **options):
        """Initialize gateway."""
        self.host = host
        self.port = port
        self.hass = options.get('hass')
        self.entry = options.get('entry')
        self.timeout = options.get('timeout', 5)
        self.keepalive = options.get('keepalive', 60)
        self.entry_id = options.get('entry_id')
        self.devices: Dict[str, "SymiDevice"] = {}
        self.setups: Dict[str, Callable] = {}
        self.log = options.get('logger', _LOGGER)
        self._msgs: Dict[Union[int, str], asyncio.Future] = {}

        self.log.debug('Gateway: %s, port: %s', host, self.port)

    def add_setup(self, domain: str, handler):
        """Add hass entity setup function."""
        if '.' in domain:
            _, domain = domain.rsplit('.', 1)
        self.setups[domain] = handler
        self.log.debug('Setup %s added for %s', domain, self.host)

    async def setup_entity(self, domain: str, device: "SymiDevice", conv: "Converter"):
        handler = self.setups.get(domain)
        if handler:
            # Create entity based on domain
            entity = None
            if domain == 'light':
                from .light import SymiLight
                entity = SymiLight(device, conv)
            elif domain == 'switch':
                from .switch import SymiSwitch
                entity = SymiSwitch(device, conv)
            elif domain == 'binary_sensor':
                from .binary_sensor import SymiBinarySensor
                entity = SymiBinarySensor(device, conv)

            if entity:
                handler([entity])
                self.log.info('Created %s entity: %s', domain, entity.entity_id)
        else:
            self.log.warning('Setup %s not ready for %s', domain, [device, conv])

    async def add_device(self, device: "SymiDevice"):
        if not device.hass:
            device.hass = self.hass
        if device.id not in self.devices:
            self.devices[device.id] = device
        if self not in device.gateways:
            device.gateways.append(self)

        self.log.info('Setup device: %s', [device.unique_id, device.name, device])

        # don't setup device from second gateway
        if len(device.gateways) > 1:
            return
        await device.setup_entities()

    async def start(self):
        self._msgs['ready'] = asyncio.get_event_loop().create_future()
        self.main_task = asyncio.create_task(self.run_forever())
        await self.ready()

    async def ready(self):
        if not self.writer:
            if not (fut := self._msgs.get('ready')):
                return None
            try:
                await asyncio.wait_for(fut, self.timeout)
            except asyncio.TimeoutError:
                return None

        await self.topology()

    async def stop(self, *args):
        if self.main_task and not self.main_task.cancelled():
            self.main_task.cancel()

        for device in self.devices.values():
            if self in device.gateways:
                device.gateways.remove(self)

    async def run_forever(self):
        """Main thread loop."""
        while True:
            try:
                if not await self.connect():
                    await asyncio.sleep(30)
                    continue
                await self.readline()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log.error('Main loop error: %s', [type(exc), exc], exc_info=exc)
        self.log.debug('Stop main loop')

    async def connect(self):
        try:
            res = await asyncio.wait_for(self._connect(), self.timeout)
        except (ConnectionError, Exception) as exc:
            res = False
            self.log.error('Gateway connect error: %s', [self.host, type(exc), exc])
        return res

    async def _connect(self):
        if not self.writer:
            self.log.debug('Connect gateway: %s', self.host)
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            if not self.writer:
                return False
            if fut := self._msgs.get('ready'):
                fut.set_result(True)
                del self._msgs['ready']
        return True

    async def readline(self):
        msg = b''
        while True:
            try:
                buf = await self.reader.readline()
            except (ConnectionError, BrokenPipeError, Exception) as exc:
                buf = None
                if isinstance(exc, (ConnectionError, BrokenPipeError)):
                    try:
                        self.writer.close()
                        await self.writer.wait_closed()
                    except (BrokenPipeError, Exception) as ce:
                        self.log.error('Connection close error: %s', [type(ce), ce])
                    self.writer = None
                self.log.error('Readline error: %s', [type(exc), exc])
                await asyncio.sleep(self.timeout - 0.1)
            if not buf:
                break
            msg += buf
            if buf[-2:] == MSG_SPLIT:
                await self.on_message(msg)
                break
        return msg

    async def on_message(self, msg):
        dat = json.loads(msg.decode()) or {}
        cmd = dat.get('method')
        cid = cmd if cmd == 'gateway_post.topology' else dat.get('id')
        nodes = dat.get('nodes') or []
        if ack := self._msgs.get(cid):
            ack.set_result(dat)
        else:
            self.log.info('Gateway message: %s', [cid, dat])

        if is_topology := cmd in ['gateway_post.topology']:
            if not self.device:
                self.device = GatewayDevice(self)
                await self.add_device(self.device)

        if not nodes and 'params' in dat:
            nodes = [dat['params']]

        for node in nodes:
            if not (nid := node.get('id')):
                continue
            if is_topology:
                # node list
                await SymiDevice.from_node(self, node)
            if not (dvc := self.devices.get(nid)):
                self.log.warning('Device not found: %s', node)
                continue
            if cmd in ['gateway_post.prop', 'device_post.prop']:
                # node prop
                await dvc.prop_changed(node)
            if cmd in ['gateway_post.event', 'device_post.event']:
                # node event
                await dvc.event_fired(node)

    async def send(self, method, wait_result=True, **kwargs):
        if not self.writer:
            await self.connect()
        if method == 'gateway_get.topology':
            cid = 'gateway_post.topology'
        else:
            cid = random.randint(1_000_000_000, 2_147_483_647)
        fut = None
        if wait_result:
            fut = asyncio.get_event_loop().create_future()
            self._msgs[cid] = fut

        dat = {
            'id': cid,
            'method': method,
            **kwargs,
        }
        self.log.info('Send command: %s', dat)
        self.writer.write(json.dumps(dat).encode() + MSG_SPLIT)
        await self.writer.drain()

        if not fut:
            return None
        try:
            await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            del self._msgs[cid]
        res = fut.result()
        return res

    async def topology(self, wait_result=False):
        cmd = 'gateway_get.topology'
        await self.send(cmd, wait_result=wait_result)

    async def get_node(self, nid=0, wait_result=True):
        cmd = 'gateway_get.node'
        return await self.send(cmd, params={'id': nid}, wait_result=wait_result)

    async def discover_devices(self):
        """Discover devices from gateway."""
        self.log.info("🔍 Starting device discovery...")
        await self.topology(wait_result=True)
        self.log.info("✅ Device discovery completed. Found %d devices", len(self.devices))

    async def control_device(self, device_id: str, **kwargs):
        """Control a device."""
        device = self.devices.get(device_id)
        if not device:
            self.log.error('Device not found: %s', device_id)
            return False

        return await device.set_prop(**kwargs)

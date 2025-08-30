"""Network discovery for Symi Gateway."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DISCOVERY_PORT, DISCOVERY_TIMEOUT, DEFAULT_TCP_PORT

_LOGGER = logging.getLogger(__name__)


class SymiGatewayDiscovery:
    """Discover Symi Gateways on the local network."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize discovery."""
        self.hass = hass
        
    async def async_discover_gateways(self) -> list[dict[str, Any]]:
        """Discover Symi Gateways on the local network."""
        _LOGGER.info("🔍 Starting fast Symi Gateway discovery on port %d", DISCOVERY_PORT)

        discovered_gateways = []

        # Get HA's local IP directly
        try:
            ha_ip = self.hass.config.api.local_ip
            if ha_ip:
                _LOGGER.info("📡 HA IP: %s", ha_ip)
                # Create network for HA's subnet
                network_obj = ipaddress.IPv4Network(f"{ha_ip}/24", strict=False)
                _LOGGER.info("🔍 Fast scanning HA network: %s", network_obj)

                # Fast scan only HA's network
                gateways = await self._fast_scan_network(network_obj)
                discovered_gateways.extend(gateways)
            else:
                raise ValueError("HA IP not available")

        except Exception as err:
            _LOGGER.warning("⚠️ Failed to get HA IP, using socket method: %s", err)
            # Fallback: get local IP via socket
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]

                _LOGGER.info("📡 Local IP: %s", local_ip)
                network_obj = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
                _LOGGER.info("🔍 Fast scanning local network: %s", network_obj)

                gateways = await self._fast_scan_network(network_obj)
                discovered_gateways.extend(gateways)

            except Exception as fallback_err:
                _LOGGER.error("❌ All discovery methods failed: %s", fallback_err)

        _LOGGER.info("✅ Fast discovery completed, found %d gateways", len(discovered_gateways))
        return discovered_gateways

    async def _fast_scan_network(self, network: ipaddress.IPv4Network) -> list[dict[str, Any]]:
        """Fast scan network for Symi Gateways - only check port 4196."""
        discovered = []

        # Create tasks for parallel scanning - only check 4196 port
        tasks = []
        for ip in network.hosts():
            # Skip broadcast and network addresses
            ip_str = str(ip)
            if ip_str.endswith('.0') or ip_str.endswith('.255'):
                continue

            task = asyncio.create_task(self._fast_check_gateway(ip_str))
            tasks.append(task)

        # Wait for all tasks with short timeout for speed
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=3.0  # 3秒快速扫描
            )

            for result in results:
                if isinstance(result, dict):
                    discovered.append(result)
                    _LOGGER.info("🎯 Found gateway: %s", result['host'])

        except asyncio.TimeoutError:
            _LOGGER.info("⏰ Fast scan completed (timeout)")

        return discovered

    async def _scan_network(self, network: ipaddress.IPv4Network) -> list[dict[str, Any]]:
        """Scan a network for Symi Gateways."""
        discovered = []
        
        # Create tasks for parallel scanning
        tasks = []
        for ip in network.hosts():
            if network.num_addresses > 256:
                # For large networks, only scan common gateway IPs
                ip_str = str(ip)
                if not (ip_str.endswith('.1') or ip_str.endswith('.254') or 
                       ip_str.endswith('.100') or ip_str.endswith('.200')):
                    continue
            
            task = asyncio.create_task(self._check_gateway(str(ip)))
            tasks.append(task)
        
        # Wait for all tasks with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=DISCOVERY_TIMEOUT * 2
            )
            
            for result in results:
                if isinstance(result, dict):
                    discovered.append(result)
                    
        except asyncio.TimeoutError:
            _LOGGER.warning("⏰ Network scan timeout for %s", network)
        
        return discovered

    async def _fast_check_gateway(self, ip: str) -> dict[str, Any] | None:
        """Fast check if IP has a Symi Gateway on port 4196."""
        try:
            # Only check port 4196 with very short timeout
            if await self._check_port_fast(ip, DISCOVERY_PORT):
                _LOGGER.info("🎯 Found Symi Gateway at %s:4196", ip)

                return {
                    "host": ip,
                    "port": DISCOVERY_PORT,
                    "discovery_port": DISCOVERY_PORT,
                    "name": f"亖米网关 ({ip})",
                    "info": {"connected": True, "fast_discovery": True}
                }

        except Exception as err:
            _LOGGER.debug("❌ Fast check failed for %s: %s", ip, err)

        return None

    async def _check_port_fast(self, ip: str, port: int) -> bool:
        """Fast port check with very short timeout."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=0.5  # 500ms超时
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return False

    async def _check_gateway(self, ip: str) -> dict[str, Any] | None:
        """Check if IP has a Symi Gateway."""
        try:
            # First check discovery port
            if await self._check_port(ip, DISCOVERY_PORT):
                _LOGGER.info("🎯 Found Symi Gateway at %s (discovery port)", ip)
                
                # Get gateway info
                gateway_info = await self._get_gateway_info(ip)
                return {
                    "host": ip,
                    "port": DEFAULT_TCP_PORT,
                    "discovery_port": DISCOVERY_PORT,
                    "name": f"亖米网关 ({ip})",
                    "info": gateway_info
                }
            
            # Fallback: check default TCP port
            elif await self._check_port(ip, DEFAULT_TCP_PORT):
                _LOGGER.info("🎯 Found potential Symi Gateway at %s (TCP port)", ip)
                
                gateway_info = await self._get_gateway_info(ip)
                return {
                    "host": ip,
                    "port": DEFAULT_TCP_PORT,
                    "discovery_port": None,
                    "name": f"亖米网关 ({ip})",
                    "info": gateway_info
                }
                
        except Exception as err:
            _LOGGER.debug("❌ Error checking %s: %s", ip, err)
        
        return None
    
    async def _check_port(self, ip: str, port: int) -> bool:
        """Check if port is open on IP."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=DISCOVERY_TIMEOUT
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return False
    
    async def _get_gateway_info(self, ip: str) -> dict[str, Any]:
        """Get gateway information."""
        try:
            # Try to connect and get basic info
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, DEFAULT_TCP_PORT),
                timeout=DISCOVERY_TIMEOUT
            )
            
            # Send a simple query (read software version)
            query_frame = bytes([0x53, 0x02, 0x00, 0x55])  # Read software version
            writer.write(query_frame)
            await writer.drain()
            
            # Try to read response
            try:
                response = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=2.0
                )
                
                if response and len(response) >= 4:
                    return {
                        "connected": True,
                        "response_length": len(response),
                        "first_bytes": response[:8].hex()
                    }
            except asyncio.TimeoutError:
                pass
            
            writer.close()
            await writer.wait_closed()
            
            return {"connected": True, "response": "no_data"}
            
        except Exception as err:
            _LOGGER.debug("❌ Failed to get gateway info from %s: %s", ip, err)
            return {"connected": False, "error": str(err)}


async def async_discover_symi_gateways(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Discover Symi Gateways on the local network."""
    discovery = SymiGatewayDiscovery(hass)
    return await discovery.async_discover_gateways()

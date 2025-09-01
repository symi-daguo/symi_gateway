"""Discovery for Symi Gateway."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEFAULT_TCP_PORT

_LOGGER = logging.getLogger(__name__)


async def async_discover_symi_gateways(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Discover Symi gateways on the local network."""
    _LOGGER.info("🔍 Starting Symi gateway discovery on port %d", DEFAULT_TCP_PORT)
    
    discovered_gateways = []
    
    try:
        # Get local network range
        local_ip = await hass.async_add_executor_job(_get_local_ip)
        if not local_ip:
            _LOGGER.error("❌ Could not determine local IP address")
            return discovered_gateways
            
        network_base = ".".join(local_ip.split(".")[:-1])
        _LOGGER.info("🌐 Scanning network: %s.x", network_base)
        
        # Create tasks for scanning IP range
        tasks = []
        for i in range(1, 255):
            ip = f"{network_base}.{i}"
            task = hass.async_create_task(_check_gateway(ip, DEFAULT_TCP_PORT))
            tasks.append(task)
        
        # Wait for all tasks with timeout
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful discoveries
        for i, result in enumerate(results):
            if isinstance(result, dict) and result.get("success"):
                ip = f"{network_base}.{i + 1}"
                gateway_info = {
                    "host": ip,
                    "port": DEFAULT_TCP_PORT,
                    "name": f"Symi Gateway ({ip})",
                    "unique_id": f"symi_gateway_{ip.replace('.', '_')}"
                }
                discovered_gateways.append(gateway_info)
                _LOGGER.info("✅ Found Symi gateway at %s:%d", ip, DEFAULT_TCP_PORT)
        
        _LOGGER.info("🔍 Discovery completed. Found %d gateways", len(discovered_gateways))
        
    except Exception as err:
        _LOGGER.error("❌ Discovery failed: %s", err)
    
    return discovered_gateways


def _get_local_ip() -> str | None:
    """Get the local IP address."""
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


async def _check_gateway(ip: str, port: int) -> dict[str, Any]:
    """Check if a Symi gateway is available at the given IP and port."""
    try:
        # Try to connect to the gateway
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=2.0
        )
        
        # Send a simple test message
        test_message = '{"method":"gateway_get.info","params":{},"id":1}\r\n'
        writer.write(test_message.encode())
        await writer.drain()
        
        # Try to read response
        response = await asyncio.wait_for(reader.read(1024), timeout=2.0)
        
        writer.close()
        await writer.wait_closed()
        
        # If we got any response, consider it a gateway
        if response:
            return {"success": True, "ip": ip, "port": port}
            
    except Exception:
        # Silently ignore connection failures during discovery
        pass
    
    return {"success": False}

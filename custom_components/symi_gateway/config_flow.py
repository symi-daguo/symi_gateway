"""Config flow for Symi Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_TCP_PORT
from .gateway import SymiGateway
from .discovery import async_discover_symi_gateways

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_TCP_PORT)

    try:
        # Test TCP connection to gateway
        gateway = SymiGateway(host, port=port, timeout=5)
        if await gateway.connect():
            await gateway.stop()
            title = f"Symi Gateway ({host}:{port})"
            return {"title": title}
        else:
            raise CannotConnect
    except Exception as err:
        _LOGGER.error("Failed to connect to gateway: %s", err)
        raise CannotConnect from err



class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Symi Gateway."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - show discovery or manual setup."""
        if user_input is not None:
            if user_input.get("setup_type") == "discovery":
                return await self.async_step_discovery()
            else:
                return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("setup_type", default="discovery"): vol.In({
                    "discovery": "🔍 自动发现网关",
                    "manual": "⚙️ 手动配置"
                })
            })
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle automatic discovery of Symi Gateways."""
        if user_input is not None:
            # User selected a discovered gateway
            selected_gateway = user_input["gateway"]
            host, port = selected_gateway.split(":")

            data = {CONF_HOST: host, CONF_PORT: int(port)}
            try:
                info = await validate_input(self.hass, data)
                return self.async_create_entry(title=info["title"], data=data)
            except CannotConnect:
                return self.async_show_form(
                    step_id="discovery",
                    errors={"base": "cannot_connect"}
                )

        # Start discovery
        _LOGGER.info("🔍 Starting gateway discovery...")
        try:
            discovered_gateways = await async_discover_symi_gateways(self.hass)

            if not discovered_gateways:
                return self.async_show_form(
                    step_id="discovery",
                    errors={"base": "no_gateways_found"},
                    data_schema=vol.Schema({
                        vol.Optional("manual_setup", default=False): bool,
                    })
                )

            # Create options for discovered gateways
            gateway_options = {}
            for gateway in discovered_gateways:
                key = f"{gateway['host']}:{gateway['port']}"
                gateway_options[key] = f"{gateway['name']}"

            return self.async_show_form(
                step_id="discovery",
                data_schema=vol.Schema({
                    vol.Required("gateway"): vol.In(gateway_options)
                }),
                description_placeholders={
                    "count": str(len(discovered_gateways))
                }
            )

        except Exception as err:
            _LOGGER.error("❌ Discovery failed: %s", err)
            return self.async_show_form(
                step_id="discovery",
                errors={"base": "discovery_failed"}
            )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual configuration."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_TCP_PORT): int,
            }),
            errors=errors,
        )



class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

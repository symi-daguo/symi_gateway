"""Config flow for Symi Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_TCP_PORT

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_TCP_PORT)

    try:
        # Test TCP connection to gateway
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0
        )
        
        # Close the connection
        writer.close()
        await writer.wait_closed()
        
        title = f"Symi Gateway ({host}:{port})"
        return {"title": title}
        
    except Exception as err:
        _LOGGER.error("Failed to connect to gateway: %s", err)
        raise CannotConnect from err



class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Symi Gateway."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if this gateway is already configured
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_TCP_PORT)
            
            # Check for existing entries
            for entry in self._async_current_entries():
                if (
                    entry.data.get(CONF_HOST) == host
                    and entry.data.get(CONF_PORT, DEFAULT_TCP_PORT) == port
                ):
                    return self.async_abort(reason="already_configured")
            
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
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_TCP_PORT): int,
            }),
            errors=errors,
        )



class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Symi Gateway."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_HOST,
                    default=self.config_entry.data.get(CONF_HOST, "")
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=self.config_entry.data.get(CONF_PORT, DEFAULT_TCP_PORT)
                ): int,
            }),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

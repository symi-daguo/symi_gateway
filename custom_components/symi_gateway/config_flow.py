"""Config flow for Symi Gateway integration."""
from __future__ import annotations

import logging
from typing import Any
import asyncio

import serial
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_BAUDRATE,
    CONF_SERIAL_PORT,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_TCP_PORT,
    DOMAIN
)
from .serial_comm import SerialCommunication
from .tcp_comm import TCPCommunication
from .discovery import async_discover_symi_gateways

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    connection_type = data[CONF_CONNECTION_TYPE]

    if connection_type == CONNECTION_TYPE_SERIAL:
        try:
            # Test serial port connection
            ser = serial.Serial(
                port=data[CONF_SERIAL_PORT],
                baudrate=data[CONF_BAUDRATE],
                timeout=1
            )
            ser.close()
            title = f"亖米Mesh网关 (串口: {data[CONF_SERIAL_PORT]})"
        except serial.SerialException as err:
            raise CannotConnect from err

    elif connection_type == CONNECTION_TYPE_TCP:
        try:
            # Test TCP connection
            tcp_comm = TCPCommunication(data[CONF_TCP_HOST], data[CONF_TCP_PORT])
            if not await tcp_comm.async_connect():
                raise CannotConnect("TCP连接失败")
            await tcp_comm.async_disconnect()
            title = f"亖米Mesh网关 (TCP: {data[CONF_TCP_HOST]}:{data[CONF_TCP_PORT]})"
        except Exception as err:
            raise CannotConnect from err

    else:
        raise CannotConnect("不支持的连接类型")

    return {"title": title}


def get_serial_ports() -> list[str]:
    """Get available serial ports."""
    return SerialCommunication.get_available_ports()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Symi Gateway."""

    VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration of the integration."""
        _LOGGER.info("🔄 Starting reconfiguration flow")

        if user_input is not None:
            # Validate the new configuration
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._get_reconfigure_schema(user_input),
                    errors={"base": "cannot_connect"}
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reconfiguration")
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._get_reconfigure_schema(user_input),
                    errors={"base": "unknown"}
                )

            # Update the config entry with new data
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data=user_input,
                title=info["title"]
            )

        # Show reconfiguration form with current values
        current_data = self._get_reconfigure_entry().data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_reconfigure_schema(current_data),
            description_placeholders={"current_config": self._format_current_config(current_data)}
        )

    def _get_reconfigure_schema(self, current_data: dict[str, Any]) -> vol.Schema:
        """Get schema for reconfiguration with current values as defaults."""
        connection_type = current_data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_TCP)

        if connection_type == CONNECTION_TYPE_SERIAL:
            return vol.Schema({
                vol.Required(CONF_CONNECTION_TYPE, default=connection_type): vol.In({
                    CONNECTION_TYPE_SERIAL: "串口连接",
                    CONNECTION_TYPE_TCP: "TCP连接"
                }),
                vol.Required(CONF_SERIAL_PORT, default=current_data.get(CONF_SERIAL_PORT, "")): vol.In(get_serial_ports()),
                vol.Required(CONF_BAUDRATE, default=current_data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)): vol.In([9600, 19200, 38400, 57600, 115200])
            })
        else:
            return vol.Schema({
                vol.Required(CONF_CONNECTION_TYPE, default=connection_type): vol.In({
                    CONNECTION_TYPE_SERIAL: "串口连接",
                    CONNECTION_TYPE_TCP: "TCP连接"
                }),
                vol.Required(CONF_TCP_HOST, default=current_data.get(CONF_TCP_HOST, "")): str,
                vol.Required(CONF_TCP_PORT, default=current_data.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)): vol.Coerce(int)
            })

    def _format_current_config(self, data: dict[str, Any]) -> str:
        """Format current configuration for display."""
        if data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_SERIAL:
            return f"串口: {data.get(CONF_SERIAL_PORT)} ({data.get(CONF_BAUDRATE)})"
        else:
            return f"TCP: {data.get(CONF_TCP_HOST)}:{data.get(CONF_TCP_PORT)}"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - show discovery or manual setup."""
        _LOGGER.info("🔧 Config flow user step called")

        if user_input is not None:
            if user_input.get("setup_type") == "discovery":
                return await self.async_step_discovery()
            else:
                return await self.async_step_connection_type()

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

            # Extract host and port from selection
            host, port = selected_gateway.split(":")

            # Create entry with discovered gateway
            return self.async_create_entry(
                title=f"亖米网关 ({host})",
                data={
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_TCP,
                    CONF_TCP_HOST: host,
                    CONF_TCP_PORT: int(port),
                }
            )

        # Start fast discovery
        _LOGGER.info("🔍 Starting fast gateway discovery...")
        errors = {}

        try:
            # Show progress to user
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "message": "正在扫描局域网中的亖米网关...",
                        "title": "网关发现",
                        "notification_id": "symi_discovery"
                    }
                )
            )

            discovered_gateways = await async_discover_symi_gateways(self.hass)

            # Clear progress notification
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "persistent_notification", "dismiss",
                    {"notification_id": "symi_discovery"}
                )
            )

            if not discovered_gateways:
                errors["base"] = "no_gateways_found"
            else:
                # Create options for discovered gateways
                gateway_options = {}
                for gateway in discovered_gateways:
                    key = f"{gateway['host']}:{gateway['port']}"
                    gateway_options[key] = f"{gateway['name']} - {gateway['host']}:4196"

                _LOGGER.info("✅ Found %d gateways", len(discovered_gateways))

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
            errors["base"] = "discovery_failed"

            # Clear progress notification on error
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "persistent_notification", "dismiss",
                    {"notification_id": "symi_discovery"}
                )
            )

        # Show error or fallback to manual setup
        if errors:
            return self.async_show_form(
                step_id="discovery",
                errors=errors,
                data_schema=vol.Schema({
                    vol.Optional("retry", default=False): bool,
                    vol.Optional("manual_setup", default=False): bool,
                })
            )

    async def async_step_connection_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection type selection."""
        _LOGGER.info("🔧 Config flow connection_type step called with input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            connection_type = user_input[CONF_CONNECTION_TYPE]
            _LOGGER.info("🔧 Selected connection type: %s", connection_type)
            if connection_type == CONNECTION_TYPE_SERIAL:
                return await self.async_step_serial()
            elif connection_type == CONNECTION_TYPE_TCP:
                return await self.async_step_tcp()

        _LOGGER.info("🔧 Showing connection type selection form")
        data_schema = vol.Schema({
            vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_SERIAL): vol.In({
                CONNECTION_TYPE_SERIAL: "串口连接",
                CONNECTION_TYPE_TCP: "TCP网络连接"
            }),
        })

        return self.async_show_form(
            step_id="connection_type",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle serial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Add connection type to user input
            user_input[CONF_CONNECTION_TYPE] = CONNECTION_TYPE_SERIAL

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Generate unique ID for serial connection
                port_clean = user_input[CONF_SERIAL_PORT].replace("/", "_").replace("\\", "_").replace(":", "_")
                unique_id = f"symi_serial_{port_clean}"
                _LOGGER.info("🔧 Setting unique_id for serial: %s", unique_id)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        # Get available serial ports
        serial_ports = await self.hass.async_add_executor_job(get_serial_ports)

        # Set default port based on platform
        import platform
        if platform.system() == "Windows":
            default_port = "COM3"
            if not serial_ports:
                serial_ports = ["COM1", "COM2", "COM3", "COM4", "COM5"]
        else:
            default_port = "/dev/ttyUSB0"
            if not serial_ports:
                serial_ports = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]

        data_schema = vol.Schema({
            vol.Required(CONF_SERIAL_PORT, default=default_port): vol.In(serial_ports) if serial_ports else str,
            vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In([9600, 19200, 38400, 57600, 115200]),
        })

        return self.async_show_form(
            step_id="serial",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle TCP configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Add connection type to user input
            user_input[CONF_CONNECTION_TYPE] = CONNECTION_TYPE_TCP

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Generate unique ID for TCP connection
                host_clean = user_input[CONF_TCP_HOST].replace(".", "_")
                unique_id = f"symi_tcp_{host_clean}_{user_input[CONF_TCP_PORT]}"
                _LOGGER.info("🔧 Setting unique_id for TCP: %s", unique_id)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_TCP_HOST, default="192.168.1.100"): str,
            vol.Required(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        })

        return self.async_show_form(
            step_id="tcp",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        # For import, assume serial connection if not specified
        if CONF_CONNECTION_TYPE not in import_data:
            import_data[CONF_CONNECTION_TYPE] = CONNECTION_TYPE_SERIAL
        return await self.async_step_user(import_data)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Symi Gateway."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update the config entry with new data
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **user_input}
            )
            return self.async_create_entry(title="", data=user_input)

        # Get current configuration
        current_data = self.config_entry.data
        connection_type = current_data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_SERIAL)

        if connection_type == CONNECTION_TYPE_SERIAL:
            schema = vol.Schema({
                vol.Required(CONF_SERIAL_PORT, default=current_data.get(CONF_SERIAL_PORT, "/dev/ttyUSB0")): str,
                vol.Required(CONF_BAUDRATE, default=current_data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)): vol.In([9600, 19200, 38400, 57600, 115200]),
                vol.Optional("enable_debug", default=False): bool,
            })
        else:
            schema = vol.Schema({
                vol.Required(CONF_TCP_HOST, default=current_data.get(CONF_TCP_HOST, "192.168.1.100")): str,
                vol.Required(CONF_TCP_PORT, default=current_data.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional("enable_debug", default=False): bool,
            })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

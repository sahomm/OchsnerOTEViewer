"""Config flow for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL

from .const import (
    BASE_REGISTER,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_SLAVE_ID): vol.All(int, vol.Range(min=1, max=247)),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=3600)
        ),
    }
)


async def _test_connection(host: str, port: int, slave_id: int) -> None:
    """Raise CannotConnect if the gateway does not answer Object 100 (connection info)."""
    client = AsyncModbusTcpClient(host=host, port=port, timeout=5)
    try:
        await client.connect()
        if not client.connected:
            raise CannotConnect
        result = await client.read_holding_registers(
            address=BASE_REGISTER, count=1, slave=slave_id
        )
        if result.isError():
            raise CannotConnect
    finally:
        client.close()


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class OchsnerOteViewerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ochsner OTE Viewer."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE_ID]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                await _test_connection(
                    user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_SLAVE_ID]
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while testing connection")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Ochsner OTE Viewer ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

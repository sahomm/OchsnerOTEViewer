"""Config flow for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.helpers import selector

from .const import (
    BASE_REGISTER,
    CONF_HAS_AUXILIARY_HEATER,
    CONF_HAS_COOLING,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Valid Modbus addresses for the OTE-Modbus-Gateway are 11-25 (DIP switch pins 6-9,
# see HARDWARE_SETUP.md) - not the full 1-247 Modbus range. Rendered explicitly as a
# NumberSelector in "box" mode so the UI shows a precise text field, not a slider
# (voluptuous vol.Range on a plain int triggers HA's default slider widget, which is
# unusable for picking an exact value out of a wide range).
SLAVE_ID_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=11, max=25, step=1, mode=selector.NumberSelectorMode.BOX)
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_SLAVE_ID): vol.All(SLAVE_ID_SELECTOR, vol.Coerce(int)),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=3600)
        ),
        # Gate sensors that could not be verified against real hardware - see
        # const.py "UNVERIFIED REGISTERS" for why.
        vol.Optional(CONF_HAS_COOLING, default=False): bool,
        vol.Optional(CONF_HAS_AUXILIARY_HEATER, default=False): bool,
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
            address=BASE_REGISTER, count=1, device_id=slave_id
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
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

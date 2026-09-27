"""Config flow for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from . import meter_profiles
from .const import (
    BASE_REGISTER,
    CONF_CONFIGURE_EXTERNAL_SENSORS,
    CONF_EXTERNAL_ENERGY_SENSOR_1,
    CONF_EXTERNAL_ENERGY_SENSOR_2,
    CONF_EXTERNAL_ENERGY_SENSOR_3,
    CONF_EXTERNAL_METER_DEVICE,
    CONF_EXTERNAL_POWER_SENSOR_1,
    CONF_EXTERNAL_POWER_SENSOR_2,
    CONF_EXTERNAL_POWER_SENSOR_3,
    CONF_HAS_AUXILIARY_HEATER,
    CONF_HAS_COOLING,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXTERNAL_ENERGY_SENSOR_KEYS,
    EXTERNAL_POWER_SENSOR_KEYS,
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

# Any existing HA energy sensor can be picked here (Shelly 3EM, another smart meter,
# an ESPHome CT-clamp sensor, ...) - see const.py for why this is three separate
# optional slots instead of one "total" field.
EXTERNAL_ENERGY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        filter=selector.EntityFilterSelectorConfig(domain="sensor", device_class="energy")
    )
)

# Instantaneous power (W) counterpart, for the real-time flow-method COP sensor - see
# const.py CONF_EXTERNAL_POWER_SENSOR_1/2/3.
EXTERNAL_POWER_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        filter=selector.EntityFilterSelectorConfig(domain="sensor", device_class="power")
    )
)

# Step 1: connection basics only. The 6 external-sensor fields live behind the
# CONF_CONFIGURE_EXTERNAL_SENSORS checkbox on a separate step (see
# async_step_external_sensors) instead of being shown to every user up front - most
# installations don't have this hardware, and 6 extra fields on the very first setup
# screen would bury the actually-required connection fields (see DECISIONS.md).
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
        vol.Optional(CONF_CONFIGURE_EXTERNAL_SENSORS, default=False): bool,
    }
)


# Key of the collapsible "Manuelle Konfiguration" section within the external-sensors
# step schema - never stored in the config entry, only ever used to structure the form
# (see async_step_external_sensors, which unpacks it back into flat keys on submit).
SECTION_MANUAL_SENSORS = "manual_sensors"


def _build_external_sensors_schema(
    discovered: list[meter_profiles.DiscoveredMeter],
) -> vol.Schema:
    """Build the step-2 schema. The discovered-device field is only included at all
    if meter_profiles.discover() actually found something - an empty list means
    nothing recognized is present, so there's nothing meaningful to choose from. The 6
    manual entity fields live in a collapsible "Manuelle Konfiguration" section below
    it, collapsed by default only if a device was found (otherwise it's the only
    option, so show it open right away)."""
    schema_dict: dict[Any, Any] = {}

    if discovered:
        options = {meter.device_id: f"{meter.profile.name}: {meter.device_name}" for meter in discovered}
        schema_dict[vol.Optional(CONF_EXTERNAL_METER_DEVICE)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=value, label=label)
                    for value, label in options.items()
                ]
            )
        )

    manual_schema = vol.Schema(
        {
            vol.Optional(CONF_EXTERNAL_ENERGY_SENSOR_1): EXTERNAL_ENERGY_SENSOR_SELECTOR,
            vol.Optional(CONF_EXTERNAL_ENERGY_SENSOR_2): EXTERNAL_ENERGY_SENSOR_SELECTOR,
            vol.Optional(CONF_EXTERNAL_ENERGY_SENSOR_3): EXTERNAL_ENERGY_SENSOR_SELECTOR,
            vol.Optional(CONF_EXTERNAL_POWER_SENSOR_1): EXTERNAL_POWER_SENSOR_SELECTOR,
            vol.Optional(CONF_EXTERNAL_POWER_SENSOR_2): EXTERNAL_POWER_SENSOR_SELECTOR,
            vol.Optional(CONF_EXTERNAL_POWER_SENSOR_3): EXTERNAL_POWER_SENSOR_SELECTOR,
        }
    )
    schema_dict[vol.Optional(SECTION_MANUAL_SENSORS, default={})] = section(
        manual_schema, {"collapsed": bool(discovered)}
    )
    return vol.Schema(schema_dict)


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

    def __init__(self) -> None:
        self._base_data: dict[str, Any] = {}

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
                configure_external_sensors = user_input.pop(
                    CONF_CONFIGURE_EXTERNAL_SENSORS, False
                )
                self._base_data = user_input
                if configure_external_sensors:
                    return await self.async_step_external_sensors()
                return self.async_create_entry(
                    title=f"Ochsner OTE Viewer ({self._base_data[CONF_HOST]})",
                    data=self._base_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_external_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional second step, only reached if the step-1 checkbox was ticked.

        Offers auto-detected meter devices (see meter_profiles.discover()) plus the
        6 manual entity fields as a fallback/override - see DECISIONS.md for why this
        isn't a single open device picker.
        """
        errors: dict[str, str] = {}
        discovered = meter_profiles.discover(self.hass)

        if user_input is not None:
            # section() nests the manual fields under this key - pull them back out
            # into a flat dict of the same CONF_EXTERNAL_*_SENSOR_* keys the manual
            # fields have always used, so a discovered device's resolution below (and
            # coordinator.py downstream) doesn't need to know sections exist at all.
            resolved = dict(user_input.pop(SECTION_MANUAL_SENSORS, {}))

            meter_device_id = user_input.get(CONF_EXTERNAL_METER_DEVICE)
            if meter_device_id:
                match = next(
                    (meter for meter in discovered if meter.device_id == meter_device_id),
                    None,
                )
                if match is None:
                    errors["base"] = "meter_not_recognized"
                else:
                    # A recognized device overrides whatever was manually entered.
                    for i, (energy_entity_id, power_entity_id) in enumerate(match.phases):
                        resolved[EXTERNAL_ENERGY_SENSOR_KEYS[i]] = energy_entity_id
                        resolved[EXTERNAL_POWER_SENSOR_KEYS[i]] = power_entity_id

            if not errors:
                data = {**self._base_data, **resolved}
                return self.async_create_entry(
                    title=f"Ochsner OTE Viewer ({data[CONF_HOST]})",
                    data=data,
                )

        return self.async_show_form(
            step_id="external_sensors",
            data_schema=self.add_suggested_values_to_schema(
                _build_external_sensors_schema(discovered), user_input or {}
            ),
            errors=errors,
        )

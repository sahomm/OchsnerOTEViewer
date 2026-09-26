"""DataUpdateCoordinator for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BASE_REGISTER,
    BLOCK_SIZE,
    COMBINED_COUNTERS,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXTERNAL_ENERGY_SENSOR_KEYS,
    EXTERNAL_POWER_SENSOR_KEYS,
    SENSORS,
    UNAVAILABLE_SENTINELS,
)

_ENERGY_UNIT_TO_KWH = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000,
}
_POWER_UNIT_TO_KW = {
    UnitOfPower.WATT: 0.001,
    UnitOfPower.KILO_WATT: 1,
    UnitOfPower.MEGA_WATT: 1000,
}
# Specific heat capacity of water, kJ/(kg*K). Assumes a water-based heating circuit -
# a water/glycol mix (common in some brine circuits) would be slightly lower; not
# adjusted for since the circuit this sensor reads (heat_generator_flow/return, on the
# building/buffer side) is expected to be plain water on most installations.
_WATER_SPECIFIC_HEAT_KJ_PER_KG_K = 4.186

_LOGGER = logging.getLogger(__name__)


def _to_signed16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


class OchsnerOteViewerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the Ochsner OTE Modbus Gateway and parses the Objects 100-132 block."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data[CONF_PORT]
        self._slave_id: int = entry.data[CONF_SLAVE_ID]
        self._external_energy_entity_ids: list[str] = [
            entry.data[key] for key in EXTERNAL_ENERGY_SENSOR_KEYS if entry.data.get(key)
        ]
        self._external_power_entity_ids: list[str] = [
            entry.data[key] for key in EXTERNAL_POWER_SENSOR_KEYS if entry.data.get(key)
        ]
        self.client = AsyncModbusTcpClient(host=self._host, port=self._port, timeout=5)

    async def _async_update_data(self) -> dict[str, Any]:
        if not self.client.connected:
            await self.client.connect()
            if not self.client.connected:
                raise UpdateFailed(
                    f"Could not connect to Modbus TCP gateway at {self._host}:{self._port}"
                )

        try:
            result = await self.client.read_holding_registers(
                address=BASE_REGISTER, count=BLOCK_SIZE, device_id=self._slave_id
            )
        except ModbusException as err:
            raise UpdateFailed(f"Modbus error while reading register block: {err}") from err

        if result.isError():
            raise UpdateFailed(f"Modbus gateway returned an error response: {result}")

        registers = result.registers
        data: dict[str, Any] = {}

        for description in SENSORS:
            raw = registers[description.offset]
            if raw in UNAVAILABLE_SENTINELS:
                data[description.key] = None
                continue
            value = _to_signed16(raw) if description.signed else raw
            if description.scale != 1:
                value = round(value * description.scale, 2)
            data[description.key] = value

        for counter in COMBINED_COUNTERS:
            ones = registers[counter.ones_offset]
            thousands = registers[counter.thousands_offset]
            data[counter.key] = thousands * 1000 + ones

        data["lifetime_efficiency_jaz"] = self._compute_lifetime_efficiency(data)
        data["computed_cop_flow_method"] = self._compute_flow_method_cop(data)

        return data

    def _sum_external_sensors(
        self, entity_ids: list[str], unit_to_base: dict[str, float]
    ) -> float | None:
        """Sum the given entities' current states, converting each via unit_to_base.
        Returns None if the list is empty, or if any entity is unavailable/unreadable/has
        an unrecognized unit - a partial sum would understate the true total and silently
        skew whichever ratio it feeds into."""
        if not entity_ids:
            return None

        total = 0.0
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                _LOGGER.debug("External sensor %s is unavailable", entity_id)
                return None

            unit = state.attributes.get("unit_of_measurement")
            factor = unit_to_base.get(unit)
            if factor is None:
                _LOGGER.warning(
                    "External sensor %s has unexpected unit %r, ignoring it",
                    entity_id,
                    unit,
                )
                return None

            try:
                total += float(state.state) * factor
            except ValueError:
                _LOGGER.debug("External sensor %s has a non-numeric state", entity_id)
                return None

        return total

    def _compute_lifetime_efficiency(self, data: dict[str, Any]) -> float | None:
        """Heating energy / electrical energy since commissioning - a lifetime average,
        not a calendar-year JAZ/SPF and not an instantaneous value (see README). Uses the
        configured external energy sensors if set, otherwise Ochsner's own
        electrical_energy_* registers (which most installations don't have populated -
        see const.py "UNVERIFIED REGISTERS")."""
        heating_kwh = data.get("heating_energy_kwh")
        heating_mwh = data.get("heating_energy_mwh")
        if heating_kwh is None or heating_mwh is None:
            return None
        heating_total = heating_mwh * 1000 + heating_kwh

        electrical_total = self._sum_external_sensors(
            self._external_energy_entity_ids, _ENERGY_UNIT_TO_KWH
        )
        if electrical_total is None:
            electrical_kwh = data.get("electrical_energy_kwh")
            electrical_mwh = data.get("electrical_energy_mwh")
            if electrical_kwh is None or electrical_mwh is None:
                return None
            electrical_total = electrical_mwh * 1000 + electrical_kwh

        if electrical_total == 0:
            return None

        return round(heating_total / electrical_total, 2)

    def _compute_flow_method_cop(self, data: dict[str, Any]) -> float | None:
        """Instantaneous COP computed independently of Ochsner's own undocumented
        "Leistungszahl COP" register: thermal power from volume_flow x temperature
        spread x specific heat of water, divided by real electrical power from the
        configured external power sensors. Requires those power sensors to be
        configured (there is no Ochsner-native instantaneous power register to fall
        back to) and the pump to actually be circulating."""
        electrical_kw = self._sum_external_sensors(
            self._external_power_entity_ids, _POWER_UNIT_TO_KW
        )
        if not electrical_kw:  # None or 0 - can't divide, or nothing configured
            return None

        flow_l_per_min = data.get("volume_flow")
        flow_temp = data.get("heat_generator_flow_temperature")
        return_temp = data.get("heat_generator_return_temperature")
        if not flow_l_per_min or flow_temp is None or return_temp is None:
            return None

        delta_t = flow_temp - return_temp
        if delta_t <= 0:
            return None

        thermal_kw = flow_l_per_min * delta_t * _WATER_SPECIFIC_HEAT_KJ_PER_KG_K / 60
        return round(thermal_kw / electrical_kw, 2)

    async def async_close(self) -> None:
        """Close the Modbus TCP connection."""
        self.client.close()

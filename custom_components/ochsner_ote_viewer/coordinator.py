"""DataUpdateCoordinator for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, UnitOfEnergy
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
    SENSORS,
    UNAVAILABLE_SENTINELS,
)

_ENERGY_UNIT_TO_KWH = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000,
}

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

        return data

    def _external_electrical_total_kwh(self) -> float | None:
        """Sum the configured external energy sensors (e.g. a Shelly 3EM's per-phase
        entities), converting each to kWh. Returns None if none are configured, or if
        any configured entity is currently unavailable/unreadable - a partial sum would
        under-report consumption and silently skew the efficiency figure."""
        if not self._external_energy_entity_ids:
            return None

        total_kwh = 0.0
        for entity_id in self._external_energy_entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                _LOGGER.debug("External energy sensor %s is unavailable", entity_id)
                return None

            unit = state.attributes.get("unit_of_measurement")
            factor = _ENERGY_UNIT_TO_KWH.get(unit)
            if factor is None:
                _LOGGER.warning(
                    "External energy sensor %s has unexpected unit %r, ignoring it for "
                    "the efficiency calculation",
                    entity_id,
                    unit,
                )
                return None

            try:
                total_kwh += float(state.state) * factor
            except ValueError:
                _LOGGER.debug("External energy sensor %s has a non-numeric state", entity_id)
                return None

        return total_kwh

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

        electrical_total = self._external_electrical_total_kwh()
        if electrical_total is None:
            electrical_kwh = data.get("electrical_energy_kwh")
            electrical_mwh = data.get("electrical_energy_mwh")
            if electrical_kwh is None or electrical_mwh is None:
                return None
            electrical_total = electrical_mwh * 1000 + electrical_kwh

        if electrical_total == 0:
            return None

        return round(heating_total / electrical_total, 2)

    async def async_close(self) -> None:
        """Close the Modbus TCP connection."""
        self.client.close()

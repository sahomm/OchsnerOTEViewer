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
    STORAGE_KEY_JAZ_BASELINES,
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

# Observed value of heat_pump_status ("Statuscode Wärmepumpe") while the compressor is
# actually running. Only empirically observed (0 = idle, 1 = running, 2 = a brief
# transitional state seen for ~1 minute right before switching to 1, likely a startup
# ramp) - other values are possible but unobserved on this system; see const.py's
# SENSORS description.
_HEAT_PUMP_STATUS_RUNNING = 1

# Minimum electrical power (kW, summed across configured phases) required before
# trusting it as "the compressor is genuinely drawing power" for the flow-method COP.
# Observed real operation so far: ~5-8 kW combined. Observed standby/handover draw:
# single-digit watts (~0.009 kW measured during one shutdown transient). This is
# comfortably below any real operating point seen so far and comfortably above
# standby noise - not a guess, but also not yet tested against a full heating season,
# so a heat pump that modulates down much further than observed here could in
# principle dip below this and get wrongly excluded; revisit if that's ever seen.
_MIN_ELECTRICAL_KW_FOR_COP = 0.3

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
        self._entry = entry
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data[CONF_PORT]
        self._slave_id: int = entry.data[CONF_SLAVE_ID]
        self._external_energy_entity_ids: list[str] = [
            entry.data[key] for key in EXTERNAL_ENERGY_SENSOR_KEYS if entry.data.get(key)
        ]
        self._external_power_entity_ids: list[str] = [
            entry.data[key] for key in EXTERNAL_POWER_SENSOR_KEYS if entry.data.get(key)
        ]
        # See _delta_since_baseline() - persisted across restarts in the config entry.
        self._jaz_baselines: dict[str, float] = dict(entry.data.get(STORAGE_KEY_JAZ_BASELINES, {}))
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

    def _delta_since_baseline(self, key: str, current_total: float) -> float | None:
        """Track *change* since a persisted baseline instead of a raw ever-growing
        counter. Both heating_energy and electrical_energy are lifetime counters, but
        they don't necessarily start counting from the same point in time - Ochsner's
        own counters run since the heat pump's commissioning (potentially years), while
        an external meter (or a not-previously-populated Ochsner electricity-meter
        register) only starts from whenever it was added. Dividing one lifetime total
        by the other then produces a meaningless ratio - observed in practice: JAZ=126
        from a multi-year heating total over a few days of freshly-added Shelly data.

        On the first reading (no baseline yet) or if the counter is now *lower* than
        the baseline (the underlying counter itself got reset - possible for external
        sensors just as much as for Ochsner's own registers, e.g. a replaced/reset
        meter), the baseline is (re)anchored to the current value and persisted; no
        delta is returned yet for that reading. Every reading after that returns
        current - baseline. In practice this means lifetime_efficiency_jaz needs some
        real runtime after setup (or after a reset) before it settles on a reliable
        value - see README."""
        baseline = self._jaz_baselines.get(key)
        if baseline is None or current_total < baseline:
            self._jaz_baselines[key] = current_total
            self.hass.config_entries.async_update_entry(
                self._entry,
                data={**self._entry.data, STORAGE_KEY_JAZ_BASELINES: dict(self._jaz_baselines)},
            )
            return None
        return round(current_total - baseline, 2)

    def _compute_lifetime_efficiency(self, data: dict[str, Any]) -> float | None:
        """Heating energy / electrical energy *since this baseline was established*
        (see _delta_since_baseline) - not a calendar-year JAZ/SPF and not an
        instantaneous value either (see README). Uses the configured external energy
        sensors if set, otherwise Ochsner's own electrical_energy_* registers (which
        most installations don't have populated - see const.py "UNVERIFIED
        REGISTERS")."""
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

        heating_delta = self._delta_since_baseline("heating", heating_total)
        electrical_delta = self._delta_since_baseline("electrical", electrical_total)
        if heating_delta is None or electrical_delta is None or electrical_delta == 0:
            return None

        return round(heating_delta / electrical_delta, 2)

    def _compute_flow_method_cop(self, data: dict[str, Any]) -> float | None:
        """Instantaneous COP computed independently of Ochsner's own undocumented
        "Leistungszahl COP" register: thermal power from volume_flow x temperature
        spread x specific heat of water, divided by real electrical power from the
        configured external power sensors. Requires those power sensors to be
        configured (there is no Ochsner-native instantaneous power register to fall
        back to) and the pump to actually be circulating.

        Also requires heat_pump_status to confirm the compressor is actually running -
        observed in practice: right as the compressor shuts off, electrical draw drops
        to ~0 almost instantly while flow/temperature spread are still trailing off
        from pump/thermal inertia, which briefly divides a real (small) thermal power
        by a near-zero electrical power and spikes this ratio to a meaningless value
        (seen: COP=167 during a shutdown transient). Gating on the status code avoids
        that transient - but a second, independent shutdown transient was later
        observed *within* the heat_pump_status=1 window itself: the compressor's own
        electrical draw can drop to near-standby (~9 W measured) up to ~30s *before*
        Ochsner's status code catches up and flips to idle - status and flow both still
        said "running" at that exact poll, yet electrical power had already collapsed
        (seen: COP=2328.24). Neither status nor flow reliably track the compressor's
        real electrical state during this handover, so the denominator itself is
        checked directly as a second, independent guard."""
        if data.get("heat_pump_status") != _HEAT_PUMP_STATUS_RUNNING:
            return None

        electrical_kw = self._sum_external_sensors(
            self._external_power_entity_ids, _POWER_UNIT_TO_KW
        )
        if not electrical_kw or electrical_kw < _MIN_ELECTRICAL_KW_FOR_COP:
            # None/0 (nothing configured), or too close to standby draw to be the
            # compressor actually running - see docstring above.
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

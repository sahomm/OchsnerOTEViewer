"""DataUpdateCoordinator for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import json
import logging
import os
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
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .accounting import Accounting
from .const import (
    ACCOUNTING_SAVE_DELAY_SECONDS,
    ACCOUNTING_STORE_VERSION,
    BASE_REGISTER,
    BLOCK_SIZE,
    COMBINED_COUNTERS,
    CONF_DEBUG_DURATION,
    CONF_DEBUG_EXPIRES,
    CONF_DEBUG_INTERVAL,
    CONF_DEBUG_LOGGING,
    CONF_DHW_FLOW_DETECTION,
    CONF_DHW_FLOW_THRESHOLD,
    CONF_SLAVE_ID,
    DEBUG_FILE_NAME,
    DEBUG_MAX_BYTES,
    DEFAULT_DEBUG_INTERVAL,
    DEFAULT_DHW_FLOW_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DHW_FLOW_THRESHOLD_MAX,
    DHW_FLOW_THRESHOLD_MIN,
    DOMAIN,
    EXTERNAL_ENERGY_SENSOR_KEYS,
    EXTERNAL_POWER_SENSOR_KEYS,
    SENSORS,
    STORAGE_KEY_JAZ_BASELINES,
    accounting_store_key,
    build_connection_id,
)
from .counters import STATE_HELD, STATE_OK, GuardedCounter
from .debug_timer import DEFAULT_DURATION, DURATION_UNLIMITED, compute_expiry, is_expired
from .registers import decode_register

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

# Minimum heating-energy delta (kWh, since the JAZ baseline) before the JAZ is shown at
# all. Observed: one ~30 min heating cycle delivers ~9 kWh, so 1 kWh is reached within
# the first minutes of the first cycle after setup or a counter reset.
_MIN_HEATING_DELTA_KWH_FOR_JAZ = 1.0

_LOGGER = logging.getLogger(__name__)


def _append_debug_line(path: str, line: str) -> None:
    """Blocking file append (run in the executor). Rotates once at DEBUG_MAX_BYTES."""
    try:
        if os.path.getsize(path) > DEBUG_MAX_BYTES:
            os.replace(path, path + ".1")
    except FileNotFoundError:
        pass
    with open(path, "a", encoding="utf-8") as debug_file:
        debug_file.write(line + "\n")


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
        # Why a derived sensor currently has no value (None while it has one) - exposed
        # as the "reason" state attribute so "Unknown" isn't mistaken for an error.
        self.reasons: dict[str, str | None] = {}
        # See _delta_since_baseline() - persisted across restarts in the config entry.
        self._jaz_baselines: dict[str, float] = dict(entry.data.get(STORAGE_KEY_JAZ_BASELINES, {}))
        # Guard the kWh+MWh pairs against the rollover moment - see counters.py. In memory
        # only: the first reading after a start is simply accepted.
        self._heating_guard = GuardedCounter()
        self._electrical_guard = GuardedCounter()
        self._heating_total_exact: float | None = None
        # Operating mode and the heating / hot-water accounting (accounting.py). The
        # totals are loaded from the Store by async_load_accounting() before the first poll.
        self._electrical_total_kwh: float | None = None
        self.accounting_snapshot: dict[str, Any] = {}
        detection, threshold = self._dhw_settings()
        # What the entities are created for; a changed detection switch needs a reload.
        self._dhw_detection_at_setup = detection
        self.accounting = Accounting(threshold if detection else None)
        self._store: Store = Store(
            hass,
            ACCOUNTING_STORE_VERSION,
            accounting_store_key(
                build_connection_id(self._host, self._port, self._slave_id)
            ),
        )
        self.client = AsyncModbusTcpClient(host=self._host, port=self._port, timeout=5)

        # Debug mode (options flow, off by default) - see const.py CONF_DEBUG_LOGGING.
        self._base_scan_interval: int = scan_interval
        self._debug_enabled = False
        self._debug_warned = False
        self._previous_registers: list[int] | None = None
        self._debug_path: str = hass.config.path(DEBUG_FILE_NAME)
        self.apply_options()

    def apply_options(self) -> None:
        """(Re)read the options: debug mode on/off and the matching poll interval.
        Idempotent and cheap - also called whenever the entry is updated for another
        reason (JAZ baselines, or the expiry written below), so it must never reload
        anything."""
        options = self._entry.options
        detection, threshold = self._dhw_settings()
        self.accounting.set_threshold(threshold if detection else None)
        enabled = bool(options.get(CONF_DEBUG_LOGGING, False))
        if enabled:
            now = dt_util.utcnow()
            expires = options.get(CONF_DEBUG_EXPIRES)
            duration = options.get(CONF_DEBUG_DURATION, DEFAULT_DURATION)
            if is_expired(expires, now):
                _LOGGER.info("Debug logging switched off: its time limit has passed")
                self._update_options({CONF_DEBUG_LOGGING: False}, remove=(CONF_DEBUG_EXPIRES,))
                enabled = False
            elif expires is None and duration != DURATION_UNLIMITED:
                # Debug mode was switched on without a stored expiry (by an older
                # version): start the time limit now, once.
                self._update_options({CONF_DEBUG_EXPIRES: compute_expiry(duration, now)})
        if enabled and not self._debug_enabled:
            self._previous_registers = None
            _LOGGER.info("Debug logging enabled, writing to %s", self._debug_path)
        elif self._debug_enabled and not enabled:
            _LOGGER.info("Debug logging disabled")
        self._debug_enabled = enabled
        interval = (
            options.get(CONF_DEBUG_INTERVAL, DEFAULT_DEBUG_INTERVAL)
            if enabled
            else self._base_scan_interval
        )
        self.update_interval = timedelta(seconds=interval)

    def _dhw_settings(self) -> tuple[bool, float]:
        """Hot-water detection switch and flow threshold (l/min): setup values in
        entry.data, overridden by the options."""
        source = {**self._entry.data, **self._entry.options}
        detection = bool(source.get(CONF_DHW_FLOW_DETECTION, False))
        try:
            threshold = float(source.get(CONF_DHW_FLOW_THRESHOLD, DEFAULT_DHW_FLOW_THRESHOLD))
        except (TypeError, ValueError):
            threshold = DEFAULT_DHW_FLOW_THRESHOLD
        return detection, min(max(threshold, DHW_FLOW_THRESHOLD_MIN), DHW_FLOW_THRESHOLD_MAX)

    @property
    def dhw_detection_changed(self) -> bool:
        """True if the detection switch differs from what the entities were created for."""
        return self._dhw_settings()[0] != self._dhw_detection_at_setup

    @property
    def dhw_detection_enabled(self) -> bool:
        return self._dhw_detection_at_setup

    @property
    def has_electrical_source(self) -> bool:
        """An electricity source for the accounting: external energy sensors or Ochsner's
        own register (same condition as the JAZ). Valid once the first poll has run."""
        return self.has_external_energy_sensors or (
            self.data is not None
            and self.data.get("electrical_energy_kwh") is not None
            and self.data.get("electrical_energy_mwh") is not None
        )

    async def async_load_accounting(self) -> None:
        """Load the cumulative totals saved earlier (a removed entry keeps them)."""
        try:
            self.accounting.load(await self._store.async_load())
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not read the saved COP totals, starting from zero", exc_info=True)

    async def async_reset_accumulators(self) -> None:
        """Discard the cumulative COP totals (options form)."""
        self.accounting.reset()
        await self._store.async_save(self.accounting.to_dict())
        _LOGGER.info("The cumulative COP totals were reset")

    def _update_accounting(self, data: dict[str, Any], now_ts: float) -> None:
        mode = self.accounting.update(
            now_ts,
            data.get("heat_pump_status"),
            data.get("volume_flow"),
            data.get("heat_generator_flow_temperature"),
            data.get("heat_generator_return_temperature"),
            self._heating_total_exact,
            self._electrical_total_kwh,
            self.update_interval.total_seconds() if self.update_interval else 60.0,
        )
        snapshot = self.accounting.snapshot()
        self.accounting_snapshot = snapshot
        last_run = snapshot.get("last_run") or {}
        data["operating_mode"] = mode
        for key in (
            "hot_water_heat_energy",
            "heating_electrical_energy",
            "hot_water_electrical_energy",
            "cop_heating",
            "cop_hot_water",
            "cop_total",
        ):
            data[key] = snapshot[key]
        data["last_run_cop"] = last_run.get("cop")
        self._store.async_delay_save(self.accounting.to_dict, ACCOUNTING_SAVE_DELAY_SECONDS)

    def _update_options(self, changes: dict[str, Any], remove: tuple[str, ...] = ()) -> None:
        """Write options without touching the others (the options flow merges likewise)."""
        options = {k: v for k, v in self._entry.options.items() if k not in remove}
        options.update(changes)
        self.hass.config_entries.async_update_entry(self._entry, options=options)

    @property
    def has_external_power_sensors(self) -> bool:
        """Any external power sensor configured (auto-detected or picked manually)."""
        return bool(self._external_power_entity_ids)

    @property
    def has_external_energy_sensors(self) -> bool:
        """Any external energy sensor configured (auto-detected or picked manually)."""
        return bool(self._external_energy_entity_ids)

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
            data[description.key] = decode_register(
                registers[description.offset],
                description.scale,
                description.signed,
                description.unavailable_sentinels,
            )

        for counter in COMBINED_COUNTERS:
            ones = registers[counter.ones_offset]
            thousands = registers[counter.thousands_offset]
            data[counter.key] = thousands * 1000 + ones

        now_ts = dt_util.utcnow().timestamp()
        self._electrical_total_kwh = None
        self._heating_total_exact = self._guarded_total(
            self._heating_guard,
            data.get("heating_energy_mwh"),
            data.get("heating_energy_kwh"),
            now_ts,
        )
        data["heating_energy_total"] = (
            round(self._heating_total_exact, 2) if self._heating_total_exact is not None else None
        )
        data["lifetime_efficiency_jaz"] = self._compute_lifetime_efficiency(data)
        data["computed_cop_flow_method"] = self._compute_flow_method_cop(data)
        external_energy = self._sum_external_sensors(
            self._external_energy_entity_ids, _ENERGY_UNIT_TO_KWH
        )
        data["electrical_energy_external"] = (
            round(external_energy, 3) if external_energy is not None else None
        )
        self._update_accounting(data, now_ts)

        if self._debug_enabled:
            await self._async_write_debug(registers, data)

        return data

    async def _async_write_debug(self, registers: list[int], data: dict[str, Any]) -> None:
        """Append one JSON line per poll. Never allowed to break the sensor update."""
        try:
            if is_expired(self._entry.options.get(CONF_DEBUG_EXPIRES), dt_util.utcnow()):
                _LOGGER.info("Debug logging switched off: its time limit has passed")
                self._update_options({CONF_DEBUG_LOGGING: False}, remove=(CONF_DEBUG_EXPIRES,))
                return

            previous = self._previous_registers
            changed = (
                {
                    str(offset): [old, new]
                    for offset, (old, new) in enumerate(zip(previous, registers))
                    if old != new
                }
                if previous is not None
                else {}
            )
            self._previous_registers = list(registers)

            flow = data.get("volume_flow")
            flow_temp = data.get("heat_generator_flow_temperature")
            return_temp = data.get("heat_generator_return_temperature")
            delta_t = (
                round(flow_temp - return_temp, 2)
                if flow_temp is not None and return_temp is not None
                else None
            )
            thermal_kw = (
                round(flow * delta_t * _WATER_SPECIFIC_HEAT_KJ_PER_KG_K / 60, 2)
                if flow is not None and delta_t is not None
                else None
            )
            record = {
                "ts": dt_util.now().isoformat(),
                "registers": list(registers),
                "changed": changed,
                "derived": {
                    "delta_t": delta_t,
                    "thermal_kw": thermal_kw,
                    "electrical_kw": self._sum_external_sensors(
                        self._external_power_entity_ids, _POWER_UNIT_TO_KW
                    ),
                    "electrical_kwh_external": data.get("electrical_energy_external"),
                    "cop_flow_method": data.get("computed_cop_flow_method"),
                },
                "reasons": dict(self.reasons),
            }
            await self.hass.async_add_executor_job(
                _append_debug_line, self._debug_path, json.dumps(record, separators=(",", ":"))
            )
        except Exception:  # noqa: BLE001
            if not self._debug_warned:
                self._debug_warned = True
                _LOGGER.warning("Could not write the debug file", exc_info=True)

    def _guarded_total(
        self, guard: GuardedCounter, mwh: float | None, kwh: float | None, now_ts: float
    ) -> float | None:
        """MWh*1000 + kWh of a register pair, with the rollover moment held back (see
        counters.py). None while either register has no value."""
        if mwh is None or kwh is None:
            return None
        value, state = guard.update(mwh * 1000 + kwh, now_ts)
        if state != STATE_OK:
            _LOGGER.info(
                "Energy counter pair looks inconsistent (%s): reading %s, using %s",
                "held" if state == STATE_HELD else "accepted as reset",
                mwh * 1000 + kwh,
                value,
            )
        return value

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
        key = "lifetime_efficiency_jaz"
        heating_total = self._heating_total_exact
        if heating_total is None:
            self.reasons[key] = "heating_energy_unavailable"
            return None

        electrical_total = self._sum_external_sensors(
            self._external_energy_entity_ids, _ENERGY_UNIT_TO_KWH
        )
        if electrical_total is None:
            electrical_kwh = data.get("electrical_energy_kwh")
            electrical_mwh = data.get("electrical_energy_mwh")
            if electrical_kwh is None or electrical_mwh is None:
                self.reasons[key] = "no_electrical_energy_source"
                return None
            electrical_total = self._guarded_total(
                self._electrical_guard,
                electrical_mwh,
                electrical_kwh,
                dt_util.utcnow().timestamp(),
            )

        self._electrical_total_kwh = electrical_total
        heating_delta = self._delta_since_baseline("heating", heating_total)
        electrical_delta = self._delta_since_baseline("electrical", electrical_total)
        # Until there is real data the sensor reads 0.0 (documented in the README) rather
        # than "Unknown", which users take for an error. Without a minimum delta, a
        # re-anchored baseline divided by a few watts of standby draw would instead
        # publish an arbitrary ratio, and one cycle's first minutes are too noisy to mean
        # anything. One cycle delivers ~9 kWh of heat.
        if heating_delta is None or electrical_delta is None:
            self.reasons[key] = "waiting_for_first_measurement"
            return 0.0
        if heating_delta < _MIN_HEATING_DELTA_KWH_FOR_JAZ or electrical_delta <= 0:
            self.reasons[key] = "waiting_for_heating_data"
            return 0.0

        self.reasons[key] = None
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
        key = "computed_cop_flow_method"
        if not self._external_power_entity_ids:
            self.reasons[key] = "no_power_sensors_configured"
            return None
        # While the compressor isn't running this reads 0.0 (documented in the README)
        # instead of "Unknown", which users take for an error. A genuine fault (power
        # sensors unavailable) still returns None so it can't pass as a normal idle 0.
        # Trade-off: the 0.0 is recorded in long-term statistics, so the hourly mean of
        # a heating hour is diluted by the idle minutes - use max/history for analysis.
        if data.get("heat_pump_status") != _HEAT_PUMP_STATUS_RUNNING:
            self.reasons[key] = "compressor_not_running"
            return 0.0

        electrical_kw = self._sum_external_sensors(
            self._external_power_entity_ids, _POWER_UNIT_TO_KW
        )
        if electrical_kw is None:
            self.reasons[key] = "power_sensors_unavailable"
            return None
        if electrical_kw < _MIN_ELECTRICAL_KW_FOR_COP:
            # Too close to standby draw to be the compressor actually running - see
            # docstring above.
            self.reasons[key] = "electrical_power_below_minimum"
            return 0.0

        flow_l_per_min = data.get("volume_flow")
        flow_temp = data.get("heat_generator_flow_temperature")
        return_temp = data.get("heat_generator_return_temperature")
        if not flow_l_per_min or flow_temp is None or return_temp is None:
            self.reasons[key] = "no_flow"
            return 0.0

        delta_t = flow_temp - return_temp
        if delta_t <= 0:
            self.reasons[key] = "no_temperature_spread"
            return 0.0

        self.reasons[key] = None
        thermal_kw = flow_l_per_min * delta_t * _WATER_SPECIFIC_HEAT_KJ_PER_KG_K / 60
        return round(thermal_kw / electrical_kw, 2)

    async def async_close(self) -> None:
        """Save the COP totals and close the Modbus TCP connection."""
        try:
            await self._store.async_save(self.accounting.to_dict())
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not save the COP totals", exc_info=True)
        self.client.close()

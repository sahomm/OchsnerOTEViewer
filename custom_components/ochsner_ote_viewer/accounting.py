"""Operating mode and heating / hot-water accounting - plain Python, no Home Assistant.

Fed once per poll with the heat pump status, the volume flow, the flow/return
temperatures, the (guarded) heating-energy counter and the electrical energy counter, it

* names the operating mode (standby, starting, running, heating, hot water, defrost,
  run-on, unknown),
* splits electricity and heat into heating and hot water and keeps cumulative totals
  (kWh), from which the COPs are derived, and
* tracks single compressor runs for a "COP of the last run".

Rules (see README):
* The heat of a poll interval and the electricity of the same interval belong to the mode
  at the END of the interval.
* The Ochsner heating counter does not count hot-water charging, apart from a few steps at
  the valve changeover. Counter steps during hot water are ignored everywhere, otherwise
  that heat would be counted twice (once in the counter, once as flow x delta-T). Counter
  steps in every other mode (also standby and run-on) belong to the heating heat.
* Hot-water heat = volume flow x (flow - return) x 4.186 / 60, only while the mode is hot
  water.
* Standby electricity is part of the total only, not of heating.
* Without a hot-water flow threshold, heating and hot-water COP are unknown and the total
  COP is calculated from the flow integral over all time instead.
* A first reading, a gap (3 x poll interval + 30 s) or an implausible step only re-anchors:
  heat and electricity of that interval are dropped together.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MODE_STANDBY = "standby"
MODE_STARTING = "starting"
MODE_RUNNING = "running"
MODE_HEATING = "heating"
MODE_HOT_WATER = "hot_water"
MODE_DEFROST = "defrost"
MODE_RUN_ON = "run_on"
MODE_UNKNOWN = "unknown"

MODES = (
    MODE_STANDBY,
    MODE_STARTING,
    MODE_RUNNING,
    MODE_HEATING,
    MODE_HOT_WATER,
    MODE_DEFROST,
    MODE_RUN_ON,
    MODE_UNKNOWN,
)

# Observed values of the heat pump status register (10D); the meaning comes from
# observation, not from the manufacturer's manual.
STATUS_STANDBY = 0
STATUS_ACTIVE = (1, 29)
STATUS_STARTING = 2
STATUS_DEFROST = (12, 9)

REASON_NOT_CONFIGURED = "dhw_detection_not_configured"
REASON_FLOW_UNAVAILABLE = "volume_flow_unavailable"
REASON_UNKNOWN_STATUS = "unknown_status"
REASON_WAITING = "waiting_for_data"

METHOD_COUNTER_PLUS_DHW = "counter_plus_dhw"
METHOD_FLOW_INTEGRAL = "flow_integral"

WATER_SPECIFIC_HEAT_KJ_PER_KG_K = 4.186

DHW_HYSTERESIS_L_MIN = 1.0
# Counter steps are lumpy (observed up to 0.5 kWh in one 10 s poll), so the slack is
# generous; the rate part only bounds what a long interval can contain.
COUNTER_SLACK_KWH = 1.0
COUNTER_MAX_KW = 40.0
ELECTRIC_SLACK_KWH = 0.2
ELECTRIC_MAX_KW = 25.0
GAP_POLLS = 3
GAP_EXTRA_SECONDS = 30.0
# Minimum electricity in a denominator before a COP is shown.
MIN_ELECTRIC_KWH = 0.5
MIN_RUN_ELECTRIC_KWH = 0.1
# A run ends after this long in standby (counter steps after the compressor stop still count).
RUN_END_STANDBY_SECONDS = 120.0

STORE_VERSION = 1

_ACC_KEYS = (
    "counter_heat",  # heating counter kWh, all modes except hot water
    "hot_water_heat",  # flow x delta-T in hot water
    "electric_heating",  # heating, starting, defrost, run-on
    "electric_hot_water",
    "electric_standby",
    "electric_other",  # running/unknown (no split possible)
    "flow_heat",  # flow integral over all time (fallback), defrost negative
)


class _Run:
    __slots__ = (
        "start",
        "last_active",
        "counter_heat",
        "hot_water_heat",
        "electric",
        "electric_hot_water",
        "flow_heat",
        "flow_temp_max",
        "defrost_seconds",
        "partial",
        "standby_since",
    )

    def __init__(self, start: float, partial: bool) -> None:
        self.start = start
        self.last_active = start
        self.counter_heat = 0.0
        self.hot_water_heat = 0.0
        self.electric = 0.0
        self.electric_hot_water = 0.0
        self.flow_heat = 0.0
        self.flow_temp_max: Optional[float] = None
        self.defrost_seconds = 0.0
        self.partial = partial
        self.standby_since: Optional[float] = None


def thermal_kw(
    flow_l_min: Optional[float], flow_temp: Optional[float], return_temp: Optional[float]
) -> Optional[float]:
    if flow_l_min is None or flow_temp is None or return_temp is None:
        return None
    return flow_l_min * (flow_temp - return_temp) * WATER_SPECIFIC_HEAT_KJ_PER_KG_K / 60.0


class Accounting:
    def __init__(self, dhw_flow_threshold: Optional[float] = None) -> None:
        """`dhw_flow_threshold` in l/min, or None if hot-water detection is off."""
        self._threshold = dhw_flow_threshold
        self.acc: Dict[str, float] = {k: 0.0 for k in _ACC_KEYS}
        self._in_dhw = False
        self._last_time: Optional[float] = None
        self._last_counter: Optional[float] = None
        self._last_electric: Optional[float] = None
        self._run: Optional[_Run] = None
        self.last_run: Optional[Dict[str, Any]] = None
        self.mode = MODE_UNKNOWN
        self.mode_reason: Optional[str] = REASON_WAITING
        self.status_code: Optional[int] = None

    # -- configuration -------------------------------------------------------------

    @property
    def detection_enabled(self) -> bool:
        return self._threshold is not None

    def set_threshold(self, threshold: Optional[float]) -> None:
        """Takes effect immediately (no reload); the hysteresis state is kept."""
        self._threshold = threshold

    # -- persistence -----------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {"v": STORE_VERSION, "acc": dict(self.acc), "last_run": self.last_run}

    def load(self, data: Optional[Dict[str, Any]]) -> None:
        """Restore totals; anything unreadable is ignored. The first poll afterwards only
        anchors, and a run in progress is not restored."""
        if not isinstance(data, dict) or data.get("v") != STORE_VERSION:
            return
        acc = data.get("acc")
        if isinstance(acc, dict):
            for key in _ACC_KEYS:
                value = acc.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    self.acc[key] = float(value)
        last_run = data.get("last_run")
        if isinstance(last_run, dict):
            self.last_run = last_run

    def reset(self) -> None:
        self.acc = {k: 0.0 for k in _ACC_KEYS}
        self.last_run = None
        self._run = None
        self._last_time = None
        self._last_counter = None
        self._last_electric = None

    # -- mode ----------------------------------------------------------------------------

    def _classify(self, status: Optional[int], flow: Optional[float]) -> str:
        self.status_code = status
        self.mode_reason = None
        if status == STATUS_STANDBY:
            self._in_dhw = False
            if flow is not None and flow > 0:
                return MODE_RUN_ON
            return MODE_STANDBY
        if status == STATUS_STARTING:
            self._in_dhw = False
            return MODE_STARTING
        if status in STATUS_DEFROST:
            return MODE_DEFROST
        if status in STATUS_ACTIVE:
            if self._threshold is None:
                self.mode_reason = REASON_NOT_CONFIGURED
                return MODE_RUNNING
            if flow is None:
                self.mode_reason = REASON_FLOW_UNAVAILABLE
                return MODE_RUNNING
            half = DHW_HYSTERESIS_L_MIN / 2.0
            if flow >= self._threshold + half:
                self._in_dhw = True
            elif flow <= self._threshold - half:
                self._in_dhw = False
            return MODE_HOT_WATER if self._in_dhw else MODE_HEATING
        self.mode_reason = REASON_UNKNOWN_STATUS
        return MODE_UNKNOWN

    # -- main entry ------------------------------------------------------------------------

    def update(
        self,
        now: float,
        status: Optional[int],
        flow: Optional[float],
        flow_temp: Optional[float],
        return_temp: Optional[float],
        counter_kwh: Optional[float],
        electric_kwh: Optional[float],
        interval_s: float,
    ) -> str:
        """Process one poll (`now` in seconds, `interval_s` = current poll interval).
        Returns the operating mode."""
        mode = self._classify(status, flow)
        self.mode = mode

        inputs_ok = counter_kwh is not None and electric_kwh is not None
        prev_time = self._last_time
        prev_counter = self._last_counter
        prev_electric = self._last_electric
        if inputs_ok:
            self._last_time, self._last_counter, self._last_electric = (
                now,
                counter_kwh,
                electric_kwh,
            )
        else:
            self._last_time = self._last_counter = self._last_electric = None

        self._track_run_boundaries(now, mode, flow_temp)

        if not inputs_ok or prev_time is None or prev_counter is None or prev_electric is None:
            self._mark_partial()
            return mode
        dt = now - prev_time
        if dt <= 0 or dt > GAP_POLLS * interval_s + GAP_EXTRA_SECONDS:
            self._mark_partial()
            return mode
        d_counter = counter_kwh - prev_counter
        d_electric = electric_kwh - prev_electric
        if (
            d_counter < 0
            or d_counter > COUNTER_SLACK_KWH + COUNTER_MAX_KW * dt / 3600.0
            or d_electric < 0
            or d_electric > ELECTRIC_SLACK_KWH + ELECTRIC_MAX_KW * dt / 3600.0
        ):
            self._mark_partial()
            return mode

        thermal = thermal_kw(flow, flow_temp, return_temp)
        heat_flow = thermal * dt / 3600.0 if thermal is not None else 0.0
        self._accumulate(mode, dt, d_counter, d_electric, heat_flow)
        return mode

    def _accumulate(
        self, mode: str, dt: float, d_counter: float, d_electric: float, heat_flow: float
    ) -> None:
        acc = self.acc
        counter_heat = 0.0
        hot_water_heat = 0.0
        if mode == MODE_HOT_WATER:
            hot_water_heat = heat_flow
            acc["electric_hot_water"] += d_electric
        else:
            counter_heat = d_counter
            if mode == MODE_STANDBY:
                acc["electric_standby"] += d_electric
            elif mode in (MODE_HEATING, MODE_STARTING, MODE_DEFROST, MODE_RUN_ON):
                acc["electric_heating"] += d_electric
            else:
                acc["electric_other"] += d_electric
        acc["counter_heat"] += counter_heat
        acc["hot_water_heat"] += hot_water_heat
        acc["flow_heat"] += heat_flow

        run = self._run
        if run is not None:
            run.counter_heat += counter_heat
            run.hot_water_heat += hot_water_heat
            run.electric += d_electric
            if mode == MODE_HOT_WATER:
                run.electric_hot_water += d_electric
            run.flow_heat += heat_flow
            if mode == MODE_DEFROST:
                run.defrost_seconds += dt

    # -- runs -------------------------------------------------------------------------------

    def _mark_partial(self) -> None:
        if self._run is not None:
            self._run.partial = True

    def _track_run_boundaries(
        self, now: float, mode: str, flow_temp: Optional[float]
    ) -> None:
        active = mode not in (MODE_STANDBY, MODE_RUN_ON)
        run = self._run
        if run is None:
            if active:
                # Begins with status 2 (clean start); any other first active mode means the
                # run was already going (restart, enabled detection, first poll): partial.
                self._run = _Run(now, partial=mode != MODE_STARTING)
                run = self._run
            else:
                return
        if active:
            run.last_active = now
            run.standby_since = None
            if flow_temp is not None and (
                run.flow_temp_max is None or flow_temp > run.flow_temp_max
            ):
                run.flow_temp_max = flow_temp
        else:
            if run.standby_since is None:
                run.standby_since = now
            elif now - run.standby_since >= RUN_END_STANDBY_SECONDS:
                self._finish_run()

    def _finish_run(self) -> None:
        run = self._run
        self._run = None
        if run is None:
            return
        heat = run.counter_heat + run.hot_water_heat
        if self._threshold is None:
            heat = run.flow_heat
            method = METHOD_FLOW_INTEGRAL
        else:
            method = METHOD_COUNTER_PLUS_DHW
        cop = round(heat / run.electric, 2) if run.electric >= MIN_RUN_ELECTRIC_KWH else None
        share = None
        if self._threshold is not None and heat > 0:
            share = round(run.hot_water_heat / heat, 3)
        self.last_run = {
            "cop": cop,
            "method": method,
            "duration_min": round((run.last_active - run.start) / 60.0, 1),
            "flow_temp_max": run.flow_temp_max,
            "heat_kwh": round(heat, 2),
            "electric_kwh": round(run.electric, 2),
            "hot_water_share": share,
            "defrost_min": round(run.defrost_seconds / 60.0, 1),
            "partial": run.partial,
        }

    # -- outputs ----------------------------------------------------------------------------

    @property
    def electric_total(self) -> float:
        a = self.acc
        return (
            a["electric_heating"]
            + a["electric_hot_water"]
            + a["electric_standby"]
            + a["electric_other"]
        )

    def snapshot(self) -> Dict[str, Any]:
        """Values and attributes for the sensors."""
        a = self.acc
        detect = self._threshold is not None
        electric_total = self.electric_total
        out: Dict[str, Any] = {
            "operating_mode": self.mode,
            "status_code": self.status_code,
            "mode_reason": self.mode_reason,
            "hot_water_heat_energy": round(a["hot_water_heat"], 3),
            "heating_electrical_energy": round(a["electric_heating"], 3),
            "hot_water_electrical_energy": round(a["electric_hot_water"], 3),
            "cop_heating": None,
            "cop_heating_reason": None,
            "cop_hot_water": None,
            "cop_hot_water_reason": None,
            "cop_total": None,
            "cop_total_reason": None,
            "cop_total_method": METHOD_COUNTER_PLUS_DHW if detect else METHOD_FLOW_INTEGRAL,
            "share_hot_water_electric": None,
            "share_hot_water_heat": None,
            "last_run": self.last_run,
        }
        if not detect:
            out["cop_heating_reason"] = REASON_NOT_CONFIGURED
            out["cop_hot_water_reason"] = REASON_NOT_CONFIGURED
        else:
            if a["electric_heating"] >= MIN_ELECTRIC_KWH:
                out["cop_heating"] = round(a["counter_heat"] / a["electric_heating"], 2)
            else:
                out["cop_heating_reason"] = REASON_WAITING
            if a["electric_hot_water"] >= MIN_ELECTRIC_KWH:
                out["cop_hot_water"] = round(a["hot_water_heat"] / a["electric_hot_water"], 2)
            else:
                out["cop_hot_water_reason"] = REASON_WAITING
        if electric_total >= MIN_ELECTRIC_KWH:
            heat = a["flow_heat"] if not detect else a["counter_heat"] + a["hot_water_heat"]
            out["cop_total"] = round(heat / electric_total, 2)
            if detect:
                out["share_hot_water_electric"] = round(a["electric_hot_water"] / electric_total, 3)
                if heat > 0:
                    out["share_hot_water_heat"] = round(a["hot_water_heat"] / heat, 3)
        else:
            out["cop_total_reason"] = REASON_WAITING
        return out

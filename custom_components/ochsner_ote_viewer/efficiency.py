"""Reset-proof heating / electricity sums for the JAZ sensor - plain Python, no Home Assistant.

The JAZ sensor (heating energy / electrical energy) used to be the difference of two
ever-growing counters against two stored baselines. When ONE of the counters is reset (the
Ochsner controller starts a new statistics period every year, an external meter can be
replaced or reset), only that baseline was re-anchored; the other kept its old value and
the ratio became wrong for months.

This module keeps two running sums instead. Every reading adds the step since the last
reading of the same counter:

* a normal step (0 ... plausible for the elapsed time) is added,
* a decrease is a counter reset: the new value counts as energy since the reset,
* an implausibly large jump (a replaced meter, a wrong value) only re-anchors, so nothing
  is added for it.

A reset of one counter therefore never touches the other, and no setting is needed: it
works whenever the reset happens.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Plausibility ceiling for the power a counter can accumulate at (see counters.py).
DEFAULT_MAX_KW = 40.0
DEFAULT_SLACK_KWH = 1.0
# After a reset the guard in counters.py holds the new reading back for up to 300 s, so
# the value that finally arrives can already contain that much running time.
RESET_LOOKBACK_SECONDS = 330.0
# Below this heating energy the JAZ is not shown yet (reads 0.0), as before.
MIN_HEATING_KWH_FOR_JAZ = 1.0
# Migration from the old baselines: a seed that gives a JAZ below this value with at
# least MIGRATION_MIN_ELECTRICAL_KWH of electricity is physically impossible (a heat pump
# does not run below COP 1); it comes from a counter reset that was only half handled.
MIGRATION_MIN_RATIO = 0.5
MIGRATION_MIN_ELECTRICAL_KWH = 50.0


class _Sum:
    """Running sum of one counter, reset-aware."""

    def __init__(self, max_kw: float, slack_kwh: float) -> None:
        self._max_kw = max_kw
        self._slack_kwh = slack_kwh
        self.total = 0.0
        self.last: Optional[float] = None
        self.last_time: Optional[float] = None

    def feed(self, value: float, now: float) -> None:
        if self.last is None or self.last_time is None:
            self.last, self.last_time = value, now
            return
        elapsed = max(now - self.last_time, 0.0)
        step = value - self.last
        limit = self._slack_kwh + self._max_kw * elapsed / 3600.0
        if step < 0:
            # Counter reset: what it shows now was counted since the reset (which may lie
            # up to RESET_LOOKBACK_SECONDS back, see above).
            reset_limit = limit + self._max_kw * RESET_LOOKBACK_SECONDS / 3600.0
            if value <= reset_limit:
                self.total += value
        elif step <= limit:
            self.total += step
        # else: implausible jump, re-anchor only
        self.last, self.last_time = value, now


class LifetimeEfficiency:
    """Heating energy and electrical energy since the sums were started, and their ratio."""

    def __init__(
        self, max_kw: float = DEFAULT_MAX_KW, slack_kwh: float = DEFAULT_SLACK_KWH
    ) -> None:
        self._heating = _Sum(max_kw, slack_kwh)
        self._electrical = _Sum(max_kw, slack_kwh)
        self.loaded = False

    # ---- persistence -------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "heating": round(self._heating.total, 4),
            "electrical": round(self._electrical.total, 4),
            "last_heating": self._heating.last,
            "last_electrical": self._electrical.last,
            "last_time": self._heating.last_time,
        }

    def load(self, data: Optional[Dict[str, Any]]) -> None:
        """Restore the saved sums. Returns silently on missing or unreadable data."""
        if not isinstance(data, dict):
            return
        try:
            self._heating.total = float(data["heating"])
            self._electrical.total = float(data["electrical"])
            last_time = data.get("last_time")
            for part, key in ((self._heating, "last_heating"), (self._electrical, "last_electrical")):
                value = data.get(key)
                part.last = float(value) if value is not None else None
                part.last_time = float(last_time) if last_time is not None else None
        except (KeyError, TypeError, ValueError):
            self._heating = _Sum(self._heating._max_kw, self._heating._slack_kwh)
            self._electrical = _Sum(self._electrical._max_kw, self._electrical._slack_kwh)
            return
        self.loaded = True

    def seed_from_baselines(
        self,
        heating_total: float,
        electrical_total: float,
        heating_baseline: Optional[float],
        electrical_baseline: Optional[float],
        now: float,
    ) -> bool:
        """First start after the update, without saved sums: take over what the old
        baselines had accumulated. Returns True if the old values were taken over, False
        if they were dropped as inconsistent (or missing) and the sums start at zero."""
        self._heating = _Sum(self._heating._max_kw, self._heating._slack_kwh)
        self._electrical = _Sum(self._electrical._max_kw, self._electrical._slack_kwh)
        self._heating.last, self._heating.last_time = heating_total, now
        self._electrical.last, self._electrical.last_time = electrical_total, now
        self.loaded = True
        if heating_baseline is None or electrical_baseline is None:
            return False
        heating = heating_total - heating_baseline
        electrical = electrical_total - electrical_baseline
        if heating < 0 or electrical < 0:
            return False
        if electrical >= MIGRATION_MIN_ELECTRICAL_KWH and heating / electrical < MIGRATION_MIN_RATIO:
            return False
        self._heating.total = heating
        self._electrical.total = electrical
        return True

    # ---- use ---------------------------------------------------------------------------
    def update(self, heating_total: float, electrical_total: float, now: float) -> None:
        self._heating.feed(heating_total, now)
        self._electrical.feed(electrical_total, now)

    @property
    def heating(self) -> float:
        return self._heating.total

    @property
    def electrical(self) -> float:
        return self._electrical.total

    def ratio(self) -> Optional[float]:
        """None until there is enough data (the sensor then reads 0.0)."""
        if self._heating.total < MIN_HEATING_KWH_FOR_JAZ or self._electrical.total <= 0:
            return None
        return round(self._heating.total / self._electrical.total, 2)

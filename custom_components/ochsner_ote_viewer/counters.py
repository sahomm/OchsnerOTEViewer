"""Guard for combined energy counters (MWh * 1000 + kWh) - plain Python, no Home Assistant.

The gateway data block is refreshed from the eBUS with up to ~1 min delay, so the two
registers of a counter pair (kWh and MWh) do not necessarily change in the same poll when
the kWh register rolls over into the MWh register. For a moment the combined value is then
about one MWh too low (kWh wrapped first) or too high (MWh incremented first). Treating
that as a real reading would re-anchor the JAZ baseline wrongly or spike a derived value.

The guard makes no assumption about where the register wraps. A new combined value is
accepted only if it can be reached from the last accepted one at a plausible power;
otherwise the last accepted value is held. If the odd value persists for HOLD_SECONDS it
is taken as a genuine counter reset and accepted.
"""
from __future__ import annotations

from typing import Optional, Tuple

# Plausibility ceiling for the thermal/electrical power a counter can accumulate at.
# Observed maximum thermal power is ~25 kW; 40 kW leaves generous headroom.
DEFAULT_MAX_KW = 40.0
# One counter step is 0.1 kWh; allow a few steps of slack on top of the rate limit.
DEFAULT_SLACK_KWH = 0.5
# How long an implausible value may be held before it counts as a real reset. Longer than
# the gateway's up-to-1-min update delay.
DEFAULT_HOLD_SECONDS = 300.0

STATE_OK = "ok"
STATE_HELD = "held"
STATE_RESET = "reset"


class GuardedCounter:
    """Holds the last plausible value of a ever-growing counter."""

    def __init__(
        self,
        max_kw: float = DEFAULT_MAX_KW,
        slack_kwh: float = DEFAULT_SLACK_KWH,
        hold_seconds: float = DEFAULT_HOLD_SECONDS,
    ) -> None:
        self._max_kw = max_kw
        self._slack_kwh = slack_kwh
        self._hold_seconds = hold_seconds
        self._last_good: Optional[float] = None
        self._last_good_time: Optional[float] = None
        self._pending_since: Optional[float] = None

    @property
    def last_good(self) -> Optional[float]:
        return self._last_good

    def update(self, total: float, now: float) -> Tuple[float, str]:
        """Feed a new combined value read at time `now` (seconds, any monotonic-ish
        clock). Returns (value to use, STATE_OK | STATE_HELD | STATE_RESET)."""
        if self._last_good is None or self._last_good_time is None:
            self._accept(total, now)
            return total, STATE_OK

        elapsed = max(now - self._last_good_time, 0.0)
        upper = self._last_good + self._slack_kwh + self._max_kw * elapsed / 3600.0
        if self._last_good <= total <= upper:
            self._accept(total, now)
            return total, STATE_OK

        if self._pending_since is None:
            self._pending_since = now
        if now - self._pending_since >= self._hold_seconds:
            self._accept(total, now)
            return total, STATE_RESET
        return self._last_good, STATE_HELD

    def _accept(self, total: float, now: float) -> None:
        self._last_good = total
        self._last_good_time = now
        self._pending_since = None

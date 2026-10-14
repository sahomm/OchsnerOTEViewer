"""Expiry handling for the debug mode - plain Python, no Home Assistant.

The expiry is stored in the config entry options as an ISO-8601 UTC string, so a restart,
reload or update of the integration does not restart the timer (it used to be kept in
memory only).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

DURATION_72H = "72h"
DURATION_UNLIMITED = "unlimited"
DEFAULT_DURATION = DURATION_72H
DURATION_HOURS = {DURATION_72H: 72}


def compute_expiry(duration: str, now: datetime) -> Optional[str]:
    """ISO UTC expiry for a freshly started debug run; None means "no time limit"."""
    hours = DURATION_HOURS.get(duration)
    if hours is None:
        return None
    return (now.astimezone(timezone.utc) + timedelta(hours=hours)).isoformat()


def is_expired(expires_iso: Optional[str], now: datetime) -> bool:
    """True if a stored expiry exists and has passed. An unreadable value counts as
    expired (fail safe: better to switch the debug file off than to run unbounded)."""
    if not expires_iso:
        return False
    try:
        expires = datetime.fromisoformat(expires_iso)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return now >= expires

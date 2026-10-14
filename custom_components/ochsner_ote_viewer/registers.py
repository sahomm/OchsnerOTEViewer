"""Decoding of a single Modbus register value - plain Python, no Home Assistant."""
from __future__ import annotations

from typing import Iterable, Optional, Union


def to_signed16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


def decode_register(
    raw: int,
    scale: float,
    signed: bool,
    unavailable_sentinels: Iterable[int],
) -> Optional[Union[int, float]]:
    """Return the scaled value, or None if raw is one of the "no value" sentinels.

    The sentinel check happens on the raw value, before the sign conversion - so which
    sentinels are valid per register matters: 0xFFFF (65535) is a genuine -0.1 for a
    signed temperature register that hovers around zero (observed: heat source registers).
    """
    if raw in unavailable_sentinels:
        return None
    value = to_signed16(raw) if signed else raw
    if scale != 1:
        value = round(value * scale, 2)
    return value

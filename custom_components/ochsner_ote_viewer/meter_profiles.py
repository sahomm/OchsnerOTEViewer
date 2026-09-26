"""Registry of recognizable "external 3-phase meter" device profiles.

Lets a user pick a single Home Assistant device (e.g. a Shelly 3EM) during setup
instead of manually selecting 6 individual energy/power entities. Each profile below
describes how to recognize one specific meter model/generation from its Home
Assistant device/entity registry structure, and how to locate its three energy +
three power entities from it.

To support another meter, add a new profile to METER_PROFILES - nothing else in this
integration needs to change, since detection just resolves to the same
CONF_EXTERNAL_ENERGY_SENSOR_1/2/3 / CONF_EXTERNAL_POWER_SENSOR_1/2/3 keys that the
manual entity-picker fields also produce (see const.py and config_flow.py). See the
README "Kompatible Zähler" section for the current list and how to contribute one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

# (energy_entity_id, power_entity_id) for one phase.
PhaseEntityPair = tuple[str, str]


@dataclass(frozen=True)
class MeterProfile:
    """One recognizable meter device model/generation.

    `resolve` receives the Home Assistant device the user picked and must return
    exactly 3 (energy, power) entity-id pairs if - and only if - that device matches
    this profile's expected structure, or None otherwise. It must never guess: a
    partial/uncertain match should return None so detection falls through to the
    next profile (or fails cleanly, prompting the user to fill the fields manually).
    """

    key: str
    name: str
    resolve: Callable[[HomeAssistant, dr.DeviceEntry], list[PhaseEntityPair] | None]


def _resolve_shelly_3em_gen1(
    hass: HomeAssistant, device: dr.DeviceEntry
) -> list[PhaseEntityPair] | None:
    """Shelly 3EM (Gen1, official 'shelly' integration).

    Verified against a real device (2026-09): the official `shelly` integration
    creates one main/hub device (diagnostics: WiFi, uptime, firmware update, reboot
    button - no via_device_id of its own) plus exactly 3 separate child devices, one
    per phase, each linked to the hub via `via_device_id`. Each phase's child device
    holds that phase's `..._energy`, `..._power`, `..._energy_returned`, `..._voltage`,
    `..._current` and `..._power_factor` entities. We match on the exact `_energy`/
    `_power` entity_id suffixes (not `_energy_returned`/`_power_factor`, which happen
    to contain but not end with those words). The user must pick the hub device.

    Only matches if the entity_ids still carry their original suffixes - a user who
    renamed these entities will need to fill the 6 fields manually instead.
    """
    if device.via_device_id is not None:
        return None  # must be the hub, not one of the per-phase child devices

    device_registry = dr.async_get(hass)
    children = [d for d in device_registry.devices.values() if d.via_device_id == device.id]
    if len(children) != 3:
        return None

    entity_registry = er.async_get(hass)
    phases: list[PhaseEntityPair] = []
    for child in children:
        energy_entity_id: str | None = None
        power_entity_id: str | None = None
        for entity in er.async_entries_for_device(entity_registry, child.id):
            if entity.entity_id.endswith("_energy"):
                energy_entity_id = entity.entity_id
            elif entity.entity_id.endswith("_power"):
                power_entity_id = entity.entity_id
        if energy_entity_id is None or power_entity_id is None:
            return None
        phases.append((energy_entity_id, power_entity_id))

    return phases


# Add new meter profiles here as they get verified against real hardware - see
# README "Kompatible Zähler" for the current list and how to contribute one.
METER_PROFILES: tuple[MeterProfile, ...] = (
    MeterProfile(
        key="shelly_3em_gen1",
        name="Shelly 3EM (Gen1)",
        resolve=_resolve_shelly_3em_gen1,
    ),
)


def detect(
    hass: HomeAssistant, device_id: str
) -> tuple[MeterProfile, list[PhaseEntityPair]] | None:
    """Try every known meter profile against the given device.

    Returns the first matching profile plus its resolved (energy, power) entity
    pairs, or None if no profile recognizes this device.
    """
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        return None

    for profile in METER_PROFILES:
        phases = profile.resolve(hass, device)
        if phases is not None:
            return profile, phases

    return None

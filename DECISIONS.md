# Design decisions & history: external electricity sensors

Internal working log so design discussions about this feature don't get lost between
sessions. Not end-user documentation (see README.md for that) - this is the "why", kept
in one place as the design evolves.

## Context

Ochsner's own OTE registers for electricity (`electrical_energy_kwh`/`_mwh`) require an
Ochsner-side electricity-meter accessory that most installations, including the one this
project is built against, don't have - it reads permanently "unavailable" there. Without
it, neither a lifetime efficiency (JAZ/SPF) sensor nor a real-time COP sensor can be
computed. Both need an external electricity source instead: JAZ needs cumulative energy
(kWh), the flow-method COP needs instantaneous power (W).

## v0.5.0 (2026-09-26): six manual entity fields

First implementation: `config_flow.py` gained 6 optional `EntitySelector` fields
(`external_energy_sensor_1/2/3`, `external_power_sensor_1/2/3`), filtered by
`device_class` (`energy`/`power`). The user manually picks the matching entity for each
of the 3 phases, for both quantities. Rationale for per-phase rather than one "total"
field: some 3-phase meters (confirmed for Shelly Pro 3EM) have a known, still-open
Home Assistant bug where the device's own "total" entity mirrors a single phase instead
of summing all three ([home-assistant/core#155155](https://github.com/home-assistant/core/issues/155155)).
Summing 3 explicitly-picked entities ourselves in `coordinator.py` sidesteps that.

## v0.6.0 (2026-09-27, commit 886a52c): meter-profile auto-detection, first attempt

User feedback: 6 fields is a lot of manual picking, and "wouldn't it be nicer to just
pick one device and have the integration figure out the rest?" (using the user's own
Shelly 3EM Gen1 as the example).

Built `meter_profiles.py`: an explicitly extensible registry of `MeterProfile` entries,
each knowing how to recognize one meter model/generation from the device/entity
registry and locate its 3 energy + 3 power entities. Shipped with one verified profile,
Shelly 3EM (Gen1, official `shelly` integration) - checked against the user's real
device: HA creates one "hub" device (diagnostics only: WiFi, uptime, firmware, reboot)
plus 3 separate child devices linked via `via_device_id`, one per phase, each holding
that phase's `..._energy`/`..._power`/etc. entities with predictable suffixes.

Config flow got one new optional field: a plain `selector.DeviceSelector`, filtered to
devices that have at least one `sensor`/`device_class: energy` entity, so the user could
pick a device and have `meter_profiles.detect()` try to resolve it.

**Problem found immediately (same day):** this filter is wrong for exactly the device
it's meant to support. The Shelly 3EM *hub* device (the one the profile actually needs
selected) carries no energy-class entity itself - only its 3 per-phase *child* devices
do. So the filtered picker excluded the hub and instead offered the 3 phase sub-devices
(which the profile correctly rejects, since it requires `via_device_id is None`), plus
every unrelated device in the house that happens to expose any energy sensor. Not
useful - see user screenchot from 2026-09-27.

## v0.7.0 (2026-09-27, shipped): active discovery + separate onboarding step

Corrected requirement, from the user directly (paraphrased): the integration should
proactively scan the whole device registry for devices matching a *known* profile, and
offer only the actual matches - not an open "pick any device" field. If no known device
is found, the user falls back to the existing 6 manual fields (already filtered to the
right sensor class).

Separately, the user also asked whether the 6 external-sensor fields could be moved off
the main setup screen entirely - either onto a second page, or behind an "Advanced"
toggle - so a first-time user isn't confronted with 6+ extra fields they likely don't
need. Given the choice between a dedicated config-flow step (a real second page) and
Home Assistant's newer `section()` schema helper (a collapsible block on the same page),
the user picked the dedicated step: it's a long-established, fully-verified HA pattern,
versus `section()` which would have needed unverified assumptions about its exact data
shape.

Shipped:
- `meter_profiles.py`: replaced the single-device `detect()` with `discover(hass) ->
  list[DiscoveredMeter]`, which runs every registered profile against every device in
  the registry and returns every match (device id/name, profile, resolved phase
  entities).
- `config_flow.py` is now two steps:
  - `async_step_user` (page 1): host/port/slave/scan_interval/cooling/aux-heater, plus
    one new checkbox `configure_external_sensors` (default off). If left off, the entry
    is created immediately after the connection test - no second page at all. If
    checked, control passes to step 2 instead of creating the entry yet.
  - `async_step_external_sensors` (page 2, only reached when the checkbox was ticked):
    calls `discover()` and, only if it found something, shows a closed `SelectSelector`
    choice of the actual matches (e.g. "Shelly 3EM (Gen1): Shelly 3EM Waermepumpe").
    The 6 manual fields are always shown below it as the fallback/override. Picking a
    discovered device still just resolves into the same 6
    `CONF_EXTERNAL_ENERGY_SENSOR_*`/`CONF_EXTERNAL_POWER_SENSOR_*` keys, so
    `coordinator.py` needed no changes at all, again.
- The `configure_external_sensors` checkbox is a pure flow-routing flag, popped off
  before the entry is created - it's never stored in the config entry itself.

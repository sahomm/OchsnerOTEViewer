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

## v0.8.0 (2026-09-27, shipped): collapsible manual section + wording pass

Live-tested against the user's real instance: `discover()` correctly found and listed
all 4 of the user's Shelly 3EM (Gen1) devices by name ("ATON", "Netz", "Waermepumpe",
"Wallbox"), and picking "Waermepumpe" correctly resolved and stored its 6 entities -
the JAZ sensor started computing a value instead of staying "unavailable", confirming
the whole discovery -> resolution -> coordinator pipeline works end to end.

Two follow-up requests from that test:
1. The step-1 checkbox's raw key (`configure_external_sensors`) rendered untranslated
   in the UI. Root cause: a stale frontend translation cache from before this key
   existed (older keys on the same page, `has_cooling` etc., rendered fine) - not a
   bug in this repo, but the wording was reworded anyway to be more concrete/tangible
   for non-technical users while at it ("Genauere Effizienzwerte für die Wärmepumpe
   einrichten (optional, per externem Stromzähler wie z. B. Shelly 3EM)" instead of a
   dry "Externe Stromsensoren einrichten").
2. The 6 manual fields, sitting right below the discovered-device dropdown with no
   visual separation, needed a heading ("Manuelle Konfiguration") plus small-print
   explanation of when they're actually needed. Implemented with Home Assistant's
   `section()` schema helper (`homeassistant.data_entry_flow.section`) instead of a
   third config-flow step, since the ask was specifically for grouping *within* the
   existing page. Verified against real HA core source (the `generic` camera
   integration's "Advanced options" section) before using it, to confirm: (a) the
   exact schema shape - `vol.Optional(key, default={}): section(vol.Schema({...}),
   {"collapsed": bool})` - and (b) that HA does NOT flatten a section's fields into
   the top-level `user_input` automatically; the code must pop `user_input[key]` as a
   nested dict itself. `config_flow.py` does exactly that, flattening it back into the
   same flat `CONF_EXTERNAL_*_SENSOR_*` keys before merging - `coordinator.py` again
   needed no changes. Collapsed by default only when a device was actually discovered
   (otherwise the section is the only option, so it opens by default).

**Found in the same live test, not yet addressed:** the resulting JAZ value (126.1) is
not trustworthy. Ochsner's own `heating_energy_kwh/mwh` is a lifetime counter since the
heat pump's commissioning (10,674 kWh here); the newly-added Shelly 3EM only had ~84
kWh summed across its 3 phases (it started counting recently). Dividing a multi-year
heating total by a few days/weeks of electricity data produces a meaningless ratio -
not a bug in the meter-detection feature, but a pre-existing gap in how
`_compute_lifetime_efficiency` frames "lifetime" that becomes obvious now that real
external data flows through it. Flagged to the user 2026-09-27; not yet decided how to
address (documentation-only caveat vs. rethinking the metric, e.g. tracking it as a
period-over-period figure via HA's own long-term statistics instead of a raw
ever-growing ratio).

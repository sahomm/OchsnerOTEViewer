# OchsnerOTEViewer

[🇩🇪 Deutsch](README.md) | 🇬🇧 English

Home Assistant integration for reading data from OCHSNER heat pumps with **OTE controller
generation** via the official **OTE Modbus Gateway** (TEM ZIF180, eBUS↔Modbus RTU).

This project was built by [sahomm](https://github.com/sahomm) with the help of Claude
(Anthropic).

> **Disclaimer:** This is a private community project and is not affiliated with OCHSNER
> Wärmepumpen GmbH in any way. All trademarks belong to their respective owners. The
> OCHSNER logo (`custom_components/ochsner_ote_viewer/brand/`) is used, as is common
> practice across the Home Assistant community, solely to identify the product this
> integration communicates with - without implying endorsement or partnership. Source:
> official vector artwork from ochsner.com.

## Upgrade note (as of v0.11.0)

⚠️ Had an older version installed already (before v0.11.0)? This version changes how
sensors are internally identified (stable connection details instead of a random internal
ID) - necessary so a future remove+re-add of the integration no longer orphans the entire
history. As a one-time transition: after updating to v0.11.0, please **remove the
integration once and re-add it with the same connection details** (Devices & Services →
Ochsner OTE Viewer → Delete, then add again) - otherwise you'll get duplicate entities (old,
orphaned ones plus new ones). From that point on, history survives future remove+re-add
cycles as long as host/port/Modbus address stay the same.

## Status

🚧 **Early development stage (v0.1) – the integration exists and has been verified
against a real gateway, but has not yet been end-to-end tested inside a running Home
Assistant instance.**

**This integration currently provides read-only access** to your OCHSNER heat pump –
temperatures, status, energy counters, operating hours, error codes. No values are written
and no settings on the heat pump are changed.

A later extension with control features is conceivable, but deliberately not part of the
current version: write access via the OTE Modbus Gateway requires changing the controller
configuration in a way that can affect the system's own safety-relevant protection
functions. That would only be pursued after careful, explicit review – not casually added
as a "convenience feature".

## Is this project for you?

OCHSNER offers **several different, each optional** accessories for smart home /
remote-access integration. This project covers exactly one of them:

| Accessory | Interface | Covered by this project? |
|---|---|---|
| **OTE Modbus Gateway** (TEM ZIF180) | Modbus RTU over RS485 | ✅ Yes, exactly this one |
| web2com module (TEM RC7000/RC7020) or OTE room terminal with touch display | SOAP/HTTP over Ethernet | ❌ No – see [derbernhard/Ochsner_W2C_HACS](https://github.com/derbernhard/Ochsner_W2C_HACS) or [ahackl/HA_cc_web2com](https://github.com/ahackl/HA_cc_web2com) |
| OTS controller (Siemens Climatix, newer generation) | JSON API over network | ❌ No – see [permissionBRICK/OTS-HomeAssistant](https://github.com/permissionBRICK/OTS-HomeAssistant) |

### How do I find out which hardware I have?

**The heat pump's own nameplate does not tell you this** – it only lists electrical
ratings, refrigerant data, and performance figures (mandatory information for CE marking
and the Pressure Equipment Directive), never optional communication accessories fitted
afterwards.

Instead, check one of these:
1. **Look inside the electrical cabinet:** Search for a small DIN-rail module labeled
   **"TEM ZIF180"** or **"eBus-Modbus IF"**, usually near the rest of the control
   electronics.
2. **In your installation documentation:** Look for a line item such as "OTE Modbus
   interface" or "ZIF180" on your heating installer's order confirmation/invoice.

If you find a web2com module or touch-display room terminal instead of the ZIF180, one of
the alternative projects linked above is probably the better fit for you.

## Required hardware

The OTE Modbus Gateway speaks **Modbus RTU over RS485** – no Ethernet out of the box. You
therefore need an additional RS485 adapter:

- **For permanent production use (recommended):** An RS485-to-Ethernet gateway, e.g. the
  [Waveshare RS232/485/422 TO POE ETH (B)](https://www.waveshare.com/rs232-485-422-to-poe-eth-b.htm).
  Benefit: no USB passthrough needed if Home Assistant runs in a VM/Proxmox; a single cable
  for power (PoE) and data.
- **For an initial connectivity test (optional, cheaper):** A simple USB-to-RS485 adapter
  (e.g. Waveshare USB TO RS485), connected directly to the machine running Home Assistant.

See [HARDWARE_SETUP.en.md](HARDWARE_SETUP.en.md) for exact configuration details
(DIP switches, wiring, network setup).

## Installation

1. In Home Assistant: **HACS → Integrations → ⋮ (menu, top right) → Custom repositories**
2. Add `https://github.com/sahomm/OchsnerOTEViewer`, category **Integration**
3. Search for "Ochsner OTE Viewer" in HACS and install it, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → "Ochsner OTE Viewer"**
5. Enter the host/IP and port of your RS485-to-Ethernet gateway, and the Modbus address of
   your OTE Modbus Gateway (see [HARDWARE_SETUP.en.md](HARDWARE_SETUP.en.md))

During setup, the integration also asks whether your system has an **active cooling
function** and/or an **Ochsner-controlled auxiliary heater** - this determines which
sensors get created (see next section). A "Set up external electricity sensors" checkbox
optionally takes you to a second page for the SPF/COP calculation (see "Unverified
registers" below) - leave it unchecked if you don't need that.

## Unverified registers

The system this project was built against has neither an active cooling function nor an
Ochsner-controlled auxiliary heater (its own backup heating elements are wired directly
into the buffer via a separate UVR16x2 controller, bypassing Ochsner's own "auxiliary
heater" logic entirely). The corresponding registers (cooling buffer/cooling energy,
auxiliary heater status/counters) follow the manual's description, but **could never be
verified against a system that actually has these features**. They are therefore only
created if you explicitly enable them during setup. If you have one of these features and
can confirm (or correct) the readings, please open an issue or PR.

**Efficiency sensor (SPF):** the "Efficiency since first measurement (seasonal performance
factor/SPF)" sensor is heating energy ÷ electrical energy - but **not** from the raw
lifetime counter values, from the **change since the first successful reading** (or since
a detected counter reset) instead. Why: Ochsner's own heating-energy counter runs since the
system's commissioning (often years), while a freshly added external electricity meter only
has a few days of data - dividing the raw lifetime totals would produce a meaningless number
(observed in practice: an SPF of 126 instead of a realistic ~3-5). This applies regardless of
whether the electrical side comes from Ochsner's own register or an external sensor.

⏳ **This means it takes a while after setup (or after a detected counter reset) before this
sensor settles on a reliable value** - how long depends on how much the heat pump actually
heats in the meantime. Expect "unavailable" or a still-unreliable value for a while at first,
that's expected. Combining the kWh/MWh register pairs (assumed as `MWh × 1000 + kWh`) is
likewise not explicitly documented in the manual, only sanity-checked. This sensor also
needs an Ochsner-side electricity-meter accessory on the OTE that many installations
(including the one this project was built against) don't have - it will then permanently
read "unavailable", which is expected.

**Alternative: external electricity sensor.** The "Set up external electricity sensors"
checkbox takes you to a second setup page where you can optionally specify up to three
existing Home Assistant energy sensors (e.g. a Shelly 3EM's three per-phase entities),
which are then used instead of Ochsner's own registers for the efficiency calculation -
we sum the three values ourselves. This deliberately avoids relying on the
"total" entity many 3-phase meters provide: Shelly (Pro) 3EM has a known, still-open bug in
Home Assistant's own integration where the "total" energy entity incorrectly mirrors a
single phase instead of summing all three
([home-assistant/core#155155](https://github.com/home-assistant/core/issues/155155)) - a
wrong total would be worse than none at all.

⚠️ **Safety note:** this integration only reads the value of an entity that already exists
in Home Assistant - it never touches your electrical installation itself. If you're
**installing new metering hardware** for this purpose (e.g. a Shelly 3EM with current
transformers in your fuse box): that is work on live mains conductors with a **risk of
death** - have it installed exclusively by a qualified electrician. Also make sure the
sensor you pick actually measures the heat pump's own circuit, not your whole household.

**Compatible meters (auto-detection):** On the second setup page, the integration searches
your Home Assistant installation for known meter devices by itself. If one is found, it
shows up above as a ready-made choice ("Recognized meter device") - picking it fills in the
6 fields below automatically (`meter_profiles.py`). There's deliberately no open "pick any
device" field: an earlier version of this had exactly that problem (e.g. offering individual
phase sub-devices instead of the correct hub device). Currently supported:

| Device | Status |
|---|---|
| Shelly 3EM (Gen1), official `shelly` integration | ✅ verified |
| Shelly Pro 3EM (Gen2) and other meters | ❌ not yet - structure unknown, please fill in manually |

If nothing known is found, this field is simply left out and you fill in the 6 fields under
"Manual configuration" instead (collapsed if a device was found, expanded automatically
otherwise) - that always works regardless. Support for more meters can be added via PR: a new
`MeterProfile` entry in `meter_profiles.py` with a `resolve()` function that locates the right
entities from the device/entity registry.

**Computed COP (flow method):** in addition to Ochsner's own (undocumented) "Leistungszahl
COP" register, there's a second, independently-computed COP sensor:

```
Thermal power [kW] = volume flow [L/min] x (flow temp - return temp) [K] x 4.186 / 60
COP = thermal power / electrical power (from the optional external power sensors)
```

4.186 kJ/(kg*K) is the specific heat capacity of water - with a water/glycol mix in the
heating circuit the real value would be slightly lower, which isn't accounted for here.
This sensor needs the **power sensors** (Watts), not the energy sensors (kWh) above - an
instantaneous value like COP needs instantaneous power, not energy counters. It's only
computed while the heat pump status code shows "running" - right as the compressor shuts
off, electrical draw drops to near 0 almost instantly while flow and temperature spread are
still trailing off from pump/water inertia; without this guard the division would briefly
spike to a meaningless value (observed: a COP of 167 during a shutdown transient). It's
deliberately a **separate, additional** sensor, not a replacement for the Ochsner register -
comparing the two over the coming heating season is the point, to work out what that
undocumented register actually represents. The "Heating capacity (raw, unverified)" sensor is
enabled by default for exactly this reason (but hidden, see next section), so Home
Assistant's long-term statistics start tracking its history from now on.

## Sensor organization

With ~27 sensors per heat pump, some sorting helps. Home Assistant's device page doesn't
support custom named section headers, but it does have a built-in split into **Sensors**
(everyday-relevant, shown first) and **Diagnostics** (technical, its own collapsed block -
status codes, refrigerant-circuit pressures, error codes, wear counters like operating
hours/switch cycles). Everything stays active and keeps recording history/statistics either
way, this is purely a visual grouping.

Two sensors are additionally **hidden** by default (not disabled - they keep running in the
background for the planned correlation analysis over the heating season), because their raw
value is more confusing than helpful on its own:

- **"COP (Ochsner register, unverified)"** - confirmed via three direct live polls (not just
  suspected), during the only heating cycle observed so far since the integration was
  installed: idle before, then actively running (heat pump status = 1, real ~21 kW thermal
  output measured via flow), then idle again after a shutdown transient - the register read
  the exact same value (25.5) at all three moments, including while actually running. It
  didn't respond live to actual operation the way its name suggests during this one cycle -
  whether that holds up over more
  cycles across the season remains to be seen. Why is unclear either way (e.g. a rarely-updated
  internal parameter, or a fixed design value rather than a measurement).
- **"Heating capacity (raw, unverified)"** - shows values like "-100" that don't mean
  anything without context.

Hidden sensors can be made visible again any time from the entity's settings. For the two
core computed sensors (SPF, computed COP) as well as status-code and counter names, the
common abbreviation now comes first with the full description in parentheses after it (e.g.
"SPF (efficiency since first measurement)"). A hover tooltip, which some might expect, isn't
something Home Assistant's default UI currently supports for individual entities - the name
is the only lever an integration has direct control over here.

## Contributing

Issues and pull requests are welcome – especially feedback from owners of other OCHSNER
heat pump models with an OTE controller (e.g. brine/water heat pumps, or with a cooling
function/auxiliary heater), to help extend the
register list and compatibility. Also welcome: new entries in the meter compatibility list
above (`meter_profiles.py`) for other 3-phase meters besides the currently supported Shelly
3EM Gen1.

## License

[MIT](LICENSE)

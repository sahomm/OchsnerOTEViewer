"""Constants and register map for the Ochsner OTE Viewer integration.

Register map derived from Ochsner's official "ZBH-OTE-Modbus-Gateway" accessory manual
(gueltig ab OTE Software-Version V6.18). All addresses below are 0-based Modbus holding
register addresses (Ochsner's own PDF lists them 1-based, decimal - subtract 1).

Only read-only "Istwerte" (actual values) are exposed as sensors. Objects 101-10A are
write-only setpoint/mode registers (Sollwerte) and are intentionally NOT exposed - see
README "Status" section for why write access is out of scope for now.

UNVERIFIED REGISTERS: the original author's installation has neither an active cooling
function nor an Ochsner-controlled auxiliary heater (their backup heating elements are
wired into the buffer via a separate Technische Alternative UVR16x2, bypassing Ochsner's
own "Zusatzheizung" logic entirely). The cooling-buffer/cooling-energy registers and the
"Zusatzheizung" (auxiliary heater) status/counters have therefore never been cross-checked
against a system that actually uses those features - the parsing (offsets/scale) follows
the manual, but real-world values have not been confirmed. These sensors are gated behind
the `has_cooling` / `has_auxiliary_heater` options set during integration setup, and are
simply not created unless enabled. If you have one of these features and can confirm (or
correct) the readings, please open an issue or PR.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)

DOMAIN = "ochsner_ote_viewer"


def build_connection_id(host: str, port: int, slave_id: int) -> str:
    """Stable identifier for one physical OTE Modbus Gateway, independent of the
    config entry's own internal entry_id (which is randomly regenerated every time
    the integration is removed and re-added). Used for the config entry's own
    unique_id (config_flow.py) *and* the device/entity identifiers (sensor.py) - so
    removing and re-adding the integration with the same connection details
    reconnects to the same device/entities/history instead of orphaning it. See
    DECISIONS.md for why this replaced an entry_id-based scheme."""
    return f"{host}:{port}:{slave_id}"


CONF_SLAVE_ID = "slave_id"
CONF_HAS_COOLING = "has_cooling"
CONF_HAS_AUXILIARY_HEATER = "has_auxiliary_heater"
# Step-1 checkbox that routes the config flow to the (optional) second step for
# external electricity sensors - keeps the first-time setup screen focused on the
# connection basics instead of showing 6+ extra fields to everyone up front. Only
# used to control config-flow navigation, never stored in the final config entry.
CONF_CONFIGURE_EXTERNAL_SENSORS = "configure_external_sensors"

# Internal (not user-facing/not shown in any form) config-entry key the coordinator
# uses to persist the heating/electrical energy readings it first saw, so
# lifetime_efficiency_jaz can be computed from the *change* since then rather than
# from Ochsner's raw since-commissioning counter - see coordinator.py
# _delta_since_baseline() for why: dividing a years-old counter by a freshly added
# external meter's few-day counter produces a meaningless ratio. Applies the same way
# regardless of whether the electrical side comes from Ochsner's own register or an
# external sensor - both are just "some ever-growing counter" from this sensor's
# point of view.
STORAGE_KEY_JAZ_BASELINES = "_jaz_baselines"
# Optional external electricity sensors (e.g. a Shelly 3EM's three per-phase energy
# entities) used for the lifetime-efficiency sensor instead of Ochsner's own
# electrical_energy_* registers. Three separate slots rather than one "total" entity
# because 3-phase meters often only expose per-phase cumulative energy - and at least
# one popular device (Shelly Pro 3EM) has a known HA-integration bug where its own
# "total" entity silently mirrors a single phase instead of summing all three
# (home-assistant/core#155155). We sum whichever slots are filled in ourselves instead
# of trusting any pre-computed total.
CONF_EXTERNAL_ENERGY_SENSOR_1 = "external_energy_sensor_1"
CONF_EXTERNAL_ENERGY_SENSOR_2 = "external_energy_sensor_2"
CONF_EXTERNAL_ENERGY_SENSOR_3 = "external_energy_sensor_3"
EXTERNAL_ENERGY_SENSOR_KEYS = (
    CONF_EXTERNAL_ENERGY_SENSOR_1,
    CONF_EXTERNAL_ENERGY_SENSOR_2,
    CONF_EXTERNAL_ENERGY_SENSOR_3,
)

# Same idea, but instantaneous power (W) instead of cumulative energy (kWh) - needed for
# a real-time COP (a power ratio), separate from the energy sensors above (an energy
# ratio, used for the lifetime JAZ/SPF sensor).
CONF_EXTERNAL_POWER_SENSOR_1 = "external_power_sensor_1"
CONF_EXTERNAL_POWER_SENSOR_2 = "external_power_sensor_2"
CONF_EXTERNAL_POWER_SENSOR_3 = "external_power_sensor_3"
EXTERNAL_POWER_SENSOR_KEYS = (
    CONF_EXTERNAL_POWER_SENSOR_1,
    CONF_EXTERNAL_POWER_SENSOR_2,
    CONF_EXTERNAL_POWER_SENSOR_3,
)

# Optional convenience alternative to filling in the 6 entity fields above by hand:
# pick a single HA device (e.g. a Shelly 3EM) and let meter_profiles.detect() figure
# out its 3 energy + 3 power entities itself. Only ever used inside config_flow.py -
# once resolved, it writes into the same CONF_EXTERNAL_*_SENSOR_* keys above, so
# nothing downstream (coordinator.py) needs to know this shortcut exists. See
# meter_profiles.py and README "Kompatible Zähler" for which devices are recognized.
CONF_EXTERNAL_METER_DEVICE = "external_meter_device"

DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 30

# Feature flags used to gate sensors that could not be validated against real hardware -
# see the "requires_feature" docstring note below for why.
FEATURE_COOLING = "cooling"
FEATURE_AUXILIARY_HEATER = "auxiliary_heater"

# Object 100 "Verbindungs-Info" sits at Modbus address 257 (1-based, per Ochsner PDF) ->
# 256 0-based. The gateway reserves 51 contiguous registers per heat pump unit (Objects
# 100-132), so a single bulk read covers everything needed.
BASE_REGISTER = 256
BLOCK_SIZE = 51

# Ochsner appears to use two different "value not available" sentinels across this
# register map (observed empirically, not explicitly documented): 0x8000 (32768) and
# 0xFFFF (65535). Both are treated as "no value" rather than shown as a nonsense number.
UNAVAILABLE_SENTINELS = (32768, 65535)


@dataclass(frozen=True)
class OchsnerSensorDescription:
    """Describes a single directly-readable sensor register."""

    key: str
    offset: int  # offset from BASE_REGISTER
    scale: float = 1.0
    signed: bool = False
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_registry_enabled_default: bool = True
    # Groups technical/maintenance values (status codes, pressures, error codes, raw
    # unverified registers) into HA's collapsed "Diagnose" section on the device page,
    # instead of the flat alphabetical list everything defaulted to before - see
    # README for the reasoning behind each choice.
    entity_category: EntityCategory | None = None
    # False only for registers that are actively misleading to look at directly (e.g.
    # a raw "-100" or a COP that never changes) but still needed enabled+recorded for
    # this project's own long-term correlation analysis - see compressor_cop and
    # heating_capacity below. Entities stay enabled/hidden, not disabled: history and
    # long-term statistics keep accumulating, they're just not shown by default.
    entity_registry_visible_default: bool = True
    # If set, this sensor is only created when the user enabled the matching feature
    # during setup (has_cooling / has_auxiliary_heater). See the module note above
    # "UNVERIFIED REGISTERS" for why this exists.
    requires_feature: str | None = None


@dataclass(frozen=True)
class OchsnerDerivedSensorDescription:
    """A sensor computed from other already-parsed values, not read directly
    from a register offset."""

    key: str
    unit: str | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


@dataclass(frozen=True)
class OchsnerCombinedCounterDescription:
    """Describes a counter split across two registers (ones 0-999 + thousands 0-999),
    as documented for Schaltzyklen/Betriebsstunden in the Ochsner PDF."""

    key: str
    ones_offset: int
    thousands_offset: int
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.TOTAL_INCREASING
    entity_category: EntityCategory | None = None
    requires_feature: str | None = None


# Offsets are relative to BASE_REGISTER (256). Objekt-Nr in the Ochsner PDF -> offset:
# 10C->12, 10D->13, 10E->14, 10F->15, 110->16, 111->17, 112->18, 113->19, 114->20,
# 115->21, 116->22, 117->23, 118->24, 119->25, 11A->26, 11B->27, 11C->28, 11D->29,
# 11E->30, 11F->31, 120->32, 121->33, 122->34, 123->35, 124->36, 125->37, 126->38,
# 127->39, 128->40, 129->41, 12A->42, 12B->43, 12C->44, 12D->45, 12F->47, 130->48,
# 131->49, 132->50
SENSORS: tuple[OchsnerSensorDescription, ...] = (
    OchsnerSensorDescription(
        key="outdoor_temperature",
        offset=12,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="heat_pump_status",
        offset=13,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="heat_generator_flow_temperature",
        offset=14,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="heat_generator_return_temperature",
        offset=15,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="heat_source_outlet_temperature",
        offset=16,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="heat_source_inlet_temperature",
        offset=17,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="suction_gas_pressure",
        offset=18,
        scale=0.1,
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="hot_gas_pressure",
        offset=19,
        scale=0.1,
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="volume_flow",
        offset=20,
        scale=0.1,
        unit=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
    ),
    # Confirmed via direct live polls and long-term statistics across 2 independent
    # heating cycles so far, not just guessed: idle before, actively running
    # (heat_pump_status=1, real ~21 kW thermal output measured via volume_flow), then
    # idle again - the register read the exact same value (25.5) every single time,
    # including *during* both runs (hourly statistics min=mean=max=25.5 straight
    # through the second cycle's running hour too). So it does not track
    # live/instantaneous compressor operation the way its name suggests, at least not
    # in what's been observed so far. (Note: an unchanged entry in HA's own state
    # history proves nothing by itself - the recorder only ever logs a new row when a
    # value changes, so a genuinely constant register would look identical there; the
    # direct live polls and the statistics spanning an active running hour are what
    # actually establish this.) Whether this is a slow-updating internal parameter, a
    # fixed rated/design value, or something else entirely is unknown - not guessed at
    # further here; more heating cycles over the season will keep testing whether this
    # holds up. Hidden by default (not disabled) so it doesn't mislead users into
    # treating it as a live COP reading, while staying enabled/recorded for comparison
    # against computed_cop_flow_method over the coming heating season (see that
    # sensor's own comment).
    OchsnerSensorDescription(
        key="compressor_cop",
        offset=21,
        scale=0.1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
    ),
    OchsnerSensorDescription(
        key="heat_generator_control_status",
        offset=26,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
    OchsnerSensorDescription(
        key="heat_manager_status",
        offset=31,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="system_temperature_setpoint",
        offset=32,
        scale=0.1,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="system_temperature",
        offset=33,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    # Enabled by default (unlike other "undocumented unit" fields) so its history
    # accumulates in HA's long-term statistics from now on - the plan is to correlate it
    # against computed_cop_flow_method's independently-derived thermal power over a full
    # heating season to work out what this register actually represents. Hidden by
    # default (not disabled) since a raw, sign-flipping, unverified-unit value like
    # "-100" is actively confusing to look at directly - it keeps recording either way.
    #
    # UPDATED HYPOTHESIS (2026-09-29, 2 cycles observed): this is very likely NOT a
    # heating capacity/power value at all, despite the manual's naming - and it's not a
    # fixed-duration ramp timer either (an earlier version of this comment guessed
    # that from the first cycle alone). Cross-referencing minute-by-minute values
    # against system_temperature/system_temperature_setpoint ("Anlagentemperatur"/
    # "-Sollwert") during a second cycle showed this register tracking
    # (setpoint - actual temperature) almost exactly, clamped to ±100:
    #   deviation +4.2 C -> 100 (saturated)   deviation +0.3 C -> 15
    #   deviation +1.4 C -> 75                deviation +0.1 C -> 5
    #   deviation +1.0 C -> 50                deviation -0.3 C -> -5
    #   deviation +0.7 C -> 35                deviation -1.2 C -> -45
    # i.e. large shortfall below setpoint -> saturated +100 (maximum demand), closing
    # in on setpoint -> value falls roughly proportionally, overshooting past setpoint
    # -> goes negative. This reads as a proportional (P/PID-style) heating demand/
    # modulation output on a ±100 internal scale, not a kW measurement - the
    # "ramp" seen in the first cycle was this same mechanism, just coincidentally
    # looking timer-like because the temperature happened to cross setpoint at a
    # fairly steady rate that time. Still a hypothesis, not confirmed by Ochsner
    # documentation - keep watching more cycles, ideally ones with a different
    # setpoint/demand situation, to stress-test it.
    OchsnerSensorDescription(
        key="heating_capacity",
        offset=34,
        scale=0.1,
        signed=True,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
    ),
    OchsnerSensorDescription(
        key="buffer_temperature_top",
        offset=35,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="buffer_temperature_middle",
        offset=36,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    OchsnerSensorDescription(
        key="cooling_buffer_temperature_middle",
        offset=37,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        requires_feature=FEATURE_COOLING,
    ),
    OchsnerSensorDescription(
        key="cooling_buffer_temperature_bottom",
        offset=38,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        requires_feature=FEATURE_COOLING,
    ),
    OchsnerSensorDescription(
        key="cooling_energy_kwh",
        offset=39,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires_feature=FEATURE_COOLING,
    ),
    OchsnerSensorDescription(
        key="cooling_energy_mwh",
        offset=40,
        unit=UnitOfEnergy.MEGA_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires_feature=FEATURE_COOLING,
    ),
    OchsnerSensorDescription(
        key="last_error_function_number",
        offset=41,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="last_error_code",
        offset=42,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerSensorDescription(
        key="heat_pump_state_code",
        offset=45,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # scale=0.1: this register counts in 0.1 kWh steps, not whole kWh. Verified against
    # a real cycle (2026-10-01): the register advanced 94 counts, which is 9.4 kWh at
    # 0.1 kWh/count - matching an independent flow x delta-T thermal estimate (~9.6 kWh)
    # to within 2 %, with the Shelly-measured electrical energy for that cycle (3.15 kWh)
    # giving a cycle COP of ~3.0 (same as computed_cop_flow_method). Treated as whole
    # kWh, the JAZ came out ~10x too high (~29). The kWh/MWh *rollover* behaviour is not
    # yet observed (the register is at ~4250 counts, i.e. ~425 kWh) - still unconfirmed.
    # Only this register is verified; electrical_energy_kwh/cooling_energy_kwh have no
    # evidence either way and are left unscaled.
    OchsnerSensorDescription(
        key="heating_energy_kwh",
        offset=47,
        scale=0.1,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    OchsnerSensorDescription(
        key="heating_energy_mwh",
        offset=48,
        unit=UnitOfEnergy.MEGA_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    OchsnerSensorDescription(
        key="electrical_energy_kwh",
        offset=49,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    OchsnerSensorDescription(
        key="electrical_energy_mwh",
        offset=50,
        unit=UnitOfEnergy.MEGA_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)

COMBINED_COUNTERS: tuple[OchsnerCombinedCounterDescription, ...] = (
    OchsnerCombinedCounterDescription(
        key="heat_pump_switch_cycles",
        ones_offset=22,
        thousands_offset=23,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerCombinedCounterDescription(
        key="heat_pump_operating_hours",
        ones_offset=24,
        thousands_offset=25,
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OchsnerCombinedCounterDescription(
        key="auxiliary_heater_switch_cycles",
        ones_offset=27,
        thousands_offset=28,
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
    OchsnerCombinedCounterDescription(
        key="auxiliary_heater_operating_hours",
        ones_offset=29,
        thousands_offset=30,
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
)

# Efficiency since this sensor first got a reading (or since its tracked baseline was
# last reset - see coordinator.py _delta_since_baseline), computed as the *change* in
# heating_energy divided by the *change* in electrical_energy, not their raw lifetime
# totals - see _delta_since_baseline for why (a years-old Ochsner counter divided by a
# freshly-added external meter's few-day counter is meaningless). ASSUMPTION, not
# explicitly documented in the Ochsner PDF: the kWh/MWh register pairs are combined as
# mwh*1000 + kwh (with heating_energy_kwh already scaled to real kWh, see its comment) -
# the manual only spells out a combination for Schaltzyklen/Betriebsstunden, not for the
# energy pairs. This sensor is only ever populated once electrical_energy_kwh/mwh (or the
# configured external sensors) are themselves available, which for Ochsner's own
# register requires an electricity meter accessory feeding it - many installations
# (including the one this project was built against) will show Ochsner's own register
# as unavailable, which is expected, not a bug (use the external sensors instead).
DERIVED_SENSORS: tuple[OchsnerDerivedSensorDescription, ...] = (
    OchsnerDerivedSensorDescription(key="lifetime_efficiency_jaz"),
    # Instantaneous COP, computed independently of Ochsner's own (undocumented-unit)
    # "Leistungszahl COP" register: thermal power from volume_flow x (flow temp - return
    # temp) x specific heat of water, divided by real electrical power from the external
    # power sensors (see EXTERNAL_POWER_SENSOR_KEYS). Only available while volume_flow > 0
    # and the power sensors are configured and available. This is a separate sensor from
    # compressor_cop, not a replacement - comparing the two over the coming heating season
    # is the point (see heating_capacity's comment above).
    OchsnerDerivedSensorDescription(key="computed_cop_flow_method"),
)

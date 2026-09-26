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
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)

DOMAIN = "ochsner_ote_viewer"

CONF_SLAVE_ID = "slave_id"
CONF_HAS_COOLING = "has_cooling"
CONF_HAS_AUXILIARY_HEATER = "has_auxiliary_heater"
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
    OchsnerSensorDescription(key="heat_pump_status", offset=13, state_class=None),
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
    ),
    OchsnerSensorDescription(
        key="hot_gas_pressure",
        offset=19,
        scale=0.1,
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
    ),
    OchsnerSensorDescription(
        key="volume_flow",
        offset=20,
        scale=0.1,
        unit=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
    ),
    # Instantaneous COP. Only meaningful while the compressor is actually running
    # (heat_pump_status != 0) - while idle, this register can hold a stale/undefined
    # value (observed: 25.5 during idle, physically implausible as an instant COP).
    OchsnerSensorDescription(
        key="compressor_cop",
        offset=21,
        scale=0.1,
    ),
    OchsnerSensorDescription(
        key="heat_generator_control_status",
        offset=26,
        state_class=None,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
    OchsnerSensorDescription(key="heat_manager_status", offset=31, state_class=None),
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
    OchsnerSensorDescription(
        key="heating_capacity",
        offset=34,
        scale=0.1,
        signed=True,
        entity_registry_enabled_default=False,
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
    OchsnerSensorDescription(key="last_error_function_number", offset=41, state_class=None),
    OchsnerSensorDescription(key="last_error_code", offset=42, state_class=None),
    OchsnerSensorDescription(key="heat_pump_state_code", offset=45, state_class=None),
    OchsnerSensorDescription(
        key="heating_energy_kwh",
        offset=47,
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
    ),
    OchsnerCombinedCounterDescription(
        key="heat_pump_operating_hours",
        ones_offset=24,
        thousands_offset=25,
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
    ),
    OchsnerCombinedCounterDescription(
        key="auxiliary_heater_switch_cycles",
        ones_offset=27,
        thousands_offset=28,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
    OchsnerCombinedCounterDescription(
        key="auxiliary_heater_operating_hours",
        ones_offset=29,
        thousands_offset=30,
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        requires_feature=FEATURE_AUXILIARY_HEATER,
    ),
)

# Lifetime-average efficiency, computed in the coordinator as
# (heating_energy_kwh + heating_energy_mwh) / (electrical_energy_kwh + electrical_energy_mwh)
# once both totals are combined. ASSUMPTION, not explicitly documented in the Ochsner PDF:
# the kWh/MWh register pairs are combined as mwh*1000 + kwh, the same pattern the manual
# spells out for Schaltzyklen/Betriebsstunden - but that combination note is only given for
# those, not restated for the energy pairs. Sanity-checked against real data (heating_energy
# = 3674 kWh + 7 MWh = 10,674 kWh total over ~2272 operating hours on a 17 kW-class heat
# pump - a plausible multi-year total), but not independently confirmed. This sensor is
# only ever populated once electrical_energy_kwh/mwh are themselves available, which
# requires an Ochsner-side electricity meter accessory feeding that register - many
# installations (including the one this project was built against) will show this as
# unavailable, which is expected, not a bug.
DERIVED_SENSORS: tuple[OchsnerDerivedSensorDescription, ...] = (
    OchsnerDerivedSensorDescription(key="lifetime_efficiency_jaz"),
)

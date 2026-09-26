"""Constants and register map for the Ochsner OTE Viewer integration.

Register map derived from Ochsner's official "ZBH-OTE-Modbus-Gateway" accessory manual
(gueltig ab OTE Software-Version V6.18). All addresses below are 0-based Modbus holding
register addresses (Ochsner's own PDF lists them 1-based, decimal - subtract 1).

Only read-only "Istwerte" (actual values) are exposed as sensors. Objects 101-10A are
write-only setpoint/mode registers (Sollwerte) and are intentionally NOT exposed - see
README "Status" section for why write access is out of scope for now.
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

DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 30

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
    OchsnerSensorDescription(
        key="compressor_cop",
        offset=21,
        scale=0.1,
        entity_registry_enabled_default=False,
    ),
    OchsnerSensorDescription(
        key="heat_generator_control_status", offset=26, state_class=None
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
        entity_registry_enabled_default=False,
    ),
    OchsnerSensorDescription(
        key="cooling_buffer_temperature_bottom",
        offset=38,
        scale=0.1,
        signed=True,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_registry_enabled_default=False,
    ),
    OchsnerSensorDescription(
        key="cooling_energy_kwh",
        offset=39,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    OchsnerSensorDescription(
        key="cooling_energy_mwh",
        offset=40,
        unit=UnitOfEnergy.MEGA_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
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
    ),
    OchsnerCombinedCounterDescription(
        key="auxiliary_heater_operating_hours",
        ones_offset=29,
        thousands_offset=30,
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
    ),
)

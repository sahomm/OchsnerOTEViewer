"""Sensor platform for the Ochsner OTE Viewer integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .accounting import MODES
from .const import (
    ACCOUNTING_SENSORS,
    COMBINED_COUNTERS,
    CONF_HAS_AUXILIARY_HEATER,
    CONF_HAS_COOLING,
    CONF_SLAVE_ID,
    DERIVED_SENSORS,
    DOMAIN,
    ENTITY_ID_PREFIX,
    FEATURE_AUXILIARY_HEATER,
    NEEDS_ALWAYS,
    NEEDS_ELECTRIC,
    NEEDS_ELECTRIC_DHW,
    FEATURE_COOLING,
    SENSORS,
    OchsnerAccountingSensorDescription,
    OchsnerCombinedCounterDescription,
    OchsnerDerivedSensorDescription,
    OchsnerSensorDescription,
    build_connection_id,
)
from .coordinator import OchsnerOteViewerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors from a config entry."""
    coordinator: OchsnerOteViewerCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_features = set()
    if entry.data.get(CONF_HAS_COOLING):
        enabled_features.add(FEATURE_COOLING)
    if entry.data.get(CONF_HAS_AUXILIARY_HEATER):
        enabled_features.add(FEATURE_AUXILIARY_HEATER)

    def _wanted(requires_feature: str | None) -> bool:
        return requires_feature is None or requires_feature in enabled_features

    # Ochsner's own electricity registers read "no value" without Ochsner's meter
    # accessory (most installations) - don't create permanently empty entities. Checked
    # at setup only; adding the accessory later needs a reload.
    _needs_value = {"electrical_energy_kwh", "electrical_energy_mwh"}

    entities: list[SensorEntity] = [
        OchsnerSensor(coordinator, entry, description)
        for description in SENSORS
        if _wanted(description.requires_feature)
        and (description.key not in _needs_value or coordinator.data.get(description.key) is not None)
    ]
    entities.extend(
        OchsnerCombinedCounterSensor(coordinator, entry, description)
        for description in COMBINED_COUNTERS
        if _wanted(description.requires_feature)
    )
    def _derived_wanted(key: str) -> bool:
        # Derived sensors are only created when their input exists, so users without
        # any matching meter don't get a permanently empty entity. Independent of the
        # meter brand: any configured external sensor counts, however it was chosen.
        # Evaluated at setup only - adding a meter or an Ochsner meter accessory later
        # needs a reload of the integration.
        if key == "computed_cop_flow_method":
            return coordinator.has_external_power_sensors
        if key == "electrical_energy_external":
            return coordinator.has_external_energy_sensors
        if key == "lifetime_efficiency_jaz":
            return coordinator.has_external_energy_sensors or (
                coordinator.data.get("electrical_energy_kwh") is not None
                and coordinator.data.get("electrical_energy_mwh") is not None
            )
        return True

    entities.extend(
        OchsnerDerivedSensor(coordinator, entry, description)
        for description in DERIVED_SENSORS
        if _derived_wanted(description.key)
    )
    # Operating mode and the heating / hot-water accounting. Every key needs an explicit
    # condition here (_derived_wanted above answers True for unknown keys).
    def _accounting_wanted(needs: str) -> bool:
        if needs == NEEDS_ALWAYS:
            return True
        if needs == NEEDS_ELECTRIC:
            return coordinator.has_electrical_source
        if needs == NEEDS_ELECTRIC_DHW:
            return coordinator.has_electrical_source and coordinator.dhw_detection_enabled
        return False

    entities.extend(
        OchsnerAccountingSensor(coordinator, entry, description)
        for description in ACCOUNTING_SENSORS
        if _accounting_wanted(description.needs)
    )
    async_add_entities(entities)


class _OchsnerBaseSensor(CoordinatorEntity[OchsnerOteViewerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OchsnerOteViewerCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        # Built from the stable connection details (same formula as the config entry's
        # own unique_id in config_flow.py), not entry.entry_id - entry_id is randomly
        # regenerated every time the integration is removed and re-added, which would
        # silently orphan every entity's history/long-term statistics on that occasion
        # even though nothing about the physical device changed.
        connection_id = build_connection_id(
            entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SLAVE_ID]
        )
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{connection_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, connection_id)},
            name="Ochsner Wärmepumpe",
            manufacturer="Ochsner",
            model="OTE-Modbus-Gateway (TEM ZIF180)",
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key)


class OchsnerSensor(_OchsnerBaseSensor):
    """A directly-readable Modbus register exposed as a sensor."""

    def __init__(
        self,
        coordinator: OchsnerOteViewerCoordinator,
        entry: ConfigEntry,
        description: OchsnerSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_visible_default = description.entity_registry_visible_default


class OchsnerCombinedCounterSensor(_OchsnerBaseSensor):
    """A counter combined from an 'ones' and a 'thousands' register."""

    def __init__(
        self,
        coordinator: OchsnerOteViewerCoordinator,
        entry: ConfigEntry,
        description: OchsnerCombinedCounterDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category


class OchsnerDerivedSensor(_OchsnerBaseSensor):
    """A sensor computed from other already-parsed coordinator values."""

    def __init__(
        self,
        coordinator: OchsnerOteViewerCoordinator,
        entry: ConfigEntry,
        description: OchsnerDerivedSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._attr_native_unit_of_measurement = description.unit
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_device_class = description.device_class

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Explain a missing value (e.g. compressor_not_running) - "Unknown" alone
        looks like an error to users."""
        reason = self.coordinator.reasons.get(self._key)
        return {"reason": reason} if reason else None


class OchsnerAccountingSensor(_OchsnerBaseSensor):
    """Operating mode and the cumulative heating / hot-water figures (accounting.py)."""

    def __init__(
        self,
        coordinator: OchsnerOteViewerCoordinator,
        entry: ConfigEntry,
        description: OchsnerAccountingSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        # Explicit entity ID, so a device area is not prefixed (see const.ENTITY_ID_PREFIX);
        # only applies when the entity is first registered, existing IDs stay.
        self.entity_id = f"sensor.{ENTITY_ID_PREFIX}_{description.key}"
        self._attr_native_unit_of_measurement = description.unit
        self._attr_state_class = description.state_class
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.entity_category
        if description.device_class == SensorDeviceClass.ENUM:
            self._attr_options = list(MODES)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.accounting_snapshot
        if not snapshot:
            return None
        key = self._key
        attributes: dict[str, Any] = {}
        if key == "operating_mode":
            attributes["status_code"] = snapshot.get("status_code")
            if snapshot.get("mode_reason"):
                attributes["reason"] = snapshot["mode_reason"]
        elif key in ("cop_heating", "cop_hot_water"):
            if snapshot.get(f"{key}_reason"):
                attributes["reason"] = snapshot[f"{key}_reason"]
        elif key == "cop_total":
            attributes["method"] = snapshot.get("cop_total_method")
            if snapshot.get("cop_total_reason"):
                attributes["reason"] = snapshot["cop_total_reason"]
            for name in ("share_hot_water_electric", "share_hot_water_heat"):
                if snapshot.get(name) is not None:
                    attributes[name] = snapshot[name]
        elif key == "last_run_cop":
            last_run = snapshot.get("last_run")
            if not last_run:
                attributes["reason"] = "no_run_yet"
            else:
                if last_run.get("cop") is None:
                    attributes["reason"] = "waiting_for_data"
                for name, value in last_run.items():
                    if name != "cop" and value is not None:
                        attributes[name] = value
        return attributes or None

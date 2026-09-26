"""Sensor platform for the Ochsner OTE Viewer integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMBINED_COUNTERS, DOMAIN, SENSORS, OchsnerCombinedCounterDescription, OchsnerSensorDescription
from .coordinator import OchsnerOteViewerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors from a config entry."""
    coordinator: OchsnerOteViewerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        OchsnerSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.extend(
        OchsnerCombinedCounterSensor(coordinator, entry, description)
        for description in COMBINED_COUNTERS
    )
    async_add_entities(entities)


class _OchsnerBaseSensor(CoordinatorEntity[OchsnerOteViewerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OchsnerOteViewerCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
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

"""The Ochsner OTE Viewer integration (read-only Modbus sensors)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import OchsnerOteViewerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ochsner OTE Viewer from a config entry."""
    coordinator = OchsnerOteViewerCoordinator(hass, entry)
    await coordinator.async_load_accounting()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options without a reload, except a changed hot-water detection
    switch (the entry is also updated for the JAZ baselines, which must not trigger one)."""
    coordinator: OchsnerOteViewerCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is not None:
        coordinator.apply_options()
        if coordinator.dhw_detection_changed:
            # The hot-water switch decides which sensors exist; the threshold alone
            # takes effect without a reload.
            hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: OchsnerOteViewerCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
    return unload_ok

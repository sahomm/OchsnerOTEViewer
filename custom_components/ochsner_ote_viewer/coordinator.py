"""DataUpdateCoordinator for the Ochsner OTE Viewer integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BASE_REGISTER,
    BLOCK_SIZE,
    COMBINED_COUNTERS,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SENSORS,
    UNAVAILABLE_SENTINELS,
)

_LOGGER = logging.getLogger(__name__)


def _to_signed16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


class OchsnerOteViewerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the Ochsner OTE Modbus Gateway and parses the Objects 100-132 block."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data[CONF_PORT]
        self._slave_id: int = entry.data[CONF_SLAVE_ID]
        self.client = AsyncModbusTcpClient(host=self._host, port=self._port, timeout=5)

    async def _async_update_data(self) -> dict[str, Any]:
        if not self.client.connected:
            await self.client.connect()
            if not self.client.connected:
                raise UpdateFailed(
                    f"Could not connect to Modbus TCP gateway at {self._host}:{self._port}"
                )

        try:
            result = await self.client.read_holding_registers(
                address=BASE_REGISTER, count=BLOCK_SIZE, device_id=self._slave_id
            )
        except ModbusException as err:
            raise UpdateFailed(f"Modbus error while reading register block: {err}") from err

        if result.isError():
            raise UpdateFailed(f"Modbus gateway returned an error response: {result}")

        registers = result.registers
        data: dict[str, Any] = {}

        for description in SENSORS:
            raw = registers[description.offset]
            if raw in UNAVAILABLE_SENTINELS:
                data[description.key] = None
                continue
            value = _to_signed16(raw) if description.signed else raw
            if description.scale != 1:
                value = round(value * description.scale, 2)
            data[description.key] = value

        for counter in COMBINED_COUNTERS:
            ones = registers[counter.ones_offset]
            thousands = registers[counter.thousands_offset]
            data[counter.key] = thousands * 1000 + ones

        return data

    async def async_close(self) -> None:
        """Close the Modbus TCP connection."""
        self.client.close()

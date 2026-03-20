"""Sensoren für den Bosch BPT-S 4.6 PV Inverter."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bosch_bpt_inverter"
DEBUG_LOGGING = False

ENDPOINT_INTERVALS = {
    "YieldStatus": timedelta(seconds=300),
    "InverterInfo": timedelta(hours=1),
    "DcPower": timedelta(seconds=60),
    "AcPower": timedelta(seconds=60),
    "StringVoltageAndCurrent": timedelta(seconds=60),
    "GridVoltageAndCurrent": timedelta(seconds=60),
}

SENSOR_DEFINITIONS = {
    "YieldStatus": [
        ("yieldDaily", "Ertrag Heute", "mdi:calendar-today", "kWh", "energy", None),
        ("yieldTotal", "Gesamtertrag", "mdi:chart-line", "kWh", "energy", "total_increasing"),
        ("yieldYearly", "Jahresertrag", "mdi:calendar", "kWh", "energy", None),
    ],
    "InverterInfo": [
        ("serialNumber", "Seriennummer", "mdi:barcode", None, None, None),
        ("deviceName", "Gerätename", "mdi:rename-box", None, None, None),
        ("model", "Modell", "mdi:chip", None, None, None),
        ("nominalPower", "Nennleistung", "mdi:flash", "kW", "power", None),
        ("numberOfStringInputs", "String-Eingänge", "mdi:connection", None, None, None),
        ("firmware", "Firmware", "mdi:memory", None, None, None),
    ],
    "DcPower": [
        ("powerA", "Power A", "mdi:flash", "W", "power", None),
        ("powerB", "Power B", "mdi:flash", "W", "power", None),
    ],
    "AcPower": [
        ("powerL1", "Power L1", "mdi:flash", "W", "power", None),
        ("status", "Status", "mdi:information-outline", None, None, None),
    ],
    "StringVoltageAndCurrent": [
        ("uStringA", "Spannung String A", "mdi:power-plug", "V", "voltage", None),
        ("iStringA", "Strom String A", "mdi:current-ac", "A", "current", None),
        ("uStringB", "Spannung String B", "mdi:power-plug", "V", "voltage", None),
        ("iStringB", "Strom String B", "mdi:current-ac", "A", "current", None),
    ],
    "GridVoltageAndCurrent": [
        ("iGridL1", "Strom L1", "mdi:current-ac", "A", "current", None),
        ("uGridL1", "Spannung L1", "mdi:power-plug", "V", "voltage", None),
        ("fGrid", "Netzfrequenz", "mdi:chart-bar", "Hz", "frequency", None),
    ],
}


class BoschInverterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordinator zum Abrufen der Daten für einen bestimmten Endpunkt."""

    def __init__(
        self,
        hass: HomeAssistant,
        resource: str,
        headers: dict[str, str],
        scan_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {resource}",
            update_interval=scan_interval,
        )
        self.resource = resource
        self.headers = headers

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(15):
                    async with session.get(self.resource, headers=self.headers, ssl=False) as response:
                        if response.status != 200:
                            raise UpdateFailed(f"Fehlerhafte Antwort: {response.status}")

                        data = await response.json(content_type=None)
                        if not isinstance(data, dict):
                            raise UpdateFailed(f"Unerwartetes Antwortformat: {type(data).__name__}")

                        if DEBUG_LOGGING:
                            _LOGGER.debug("Bosch API %s -> %s", self.resource, data)

                        return data
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Fehler beim Abrufen der Daten: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Fehler beim Abrufen der Daten: {err}") from err


class BoschInverterSensor(CoordinatorEntity[BoschInverterCoordinator], SensorEntity):
    """Sensor für einen bestimmten Bosch-Wert."""

    def __init__(
        self,
        coordinator: BoschInverterCoordinator,
        endpoint: str,
        key: str,
        name: str,
        icon: str,
        unit: str | None,
        device_class: str | None,
        state_class: str | None,
    ) -> None:
        super().__init__(coordinator)
        self.endpoint = endpoint
        self.key = key
        self._attr_name = f"Bosch Wechselrichter {name}"
        self._attr_unique_id = f"bpt/{endpoint}/{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

        if device_class == "energy":
            self._attr_state_class = state_class
        else:
            self._attr_state_class = state_class if state_class is not None else ("measurement" if unit else None)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and isinstance(self.coordinator.data, dict)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None

        raw = data.get(self.key)
        if raw is None:
            return None

        if self._attr_native_unit_of_measurement is not None:
            try:
                return round(float(raw), 2)
            except (ValueError, TypeError):
                return None

        return raw


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Initialisiert alle Sensoren der Bosch-BPT-Inverter-Integration."""
    conf = hass.data.get(DOMAIN)
    if not conf:
        _LOGGER.error("Konfigurationsdaten nicht gefunden!")
        return

    base_resource = conf.get("resource")
    if not base_resource:
        _LOGGER.error("Resource URL nicht in der Konfiguration gefunden!")
        return

    headers = {"Authorization": "Basic QWxsOkFsbA=="}
    entities: list[BoschInverterSensor] = []

    for endpoint, scan_interval in ENDPOINT_INTERVALS.items():
        resource = f"{base_resource}/pvi?rName={endpoint}"
        coordinator = BoschInverterCoordinator(hass, resource, headers, scan_interval)

        # Bei YAML-Setup darf ein temporär nicht erreichbarer Wechselrichter nicht das komplette
        # Laden der Plattform abbrechen. Daher nur normal refreshen, nicht first_refresh.
        await coordinator.async_refresh()

        for key, name, icon, unit, device_class, state_class in SENSOR_DEFINITIONS.get(endpoint, []):
            entities.append(
                BoschInverterSensor(
                    coordinator,
                    endpoint,
                    key,
                    name,
                    icon,
                    unit,
                    device_class,
                    state_class,
                )
            )

    async_add_entities(entities)

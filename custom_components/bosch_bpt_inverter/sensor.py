"""
Erweiterte Sensor-Integration für den Bosch BPT-S 4.6 PV Inverter.

Diese Integration ruft für verschiedene Endpunkte (YieldStatus, InverterInfo, DcPower, AcPower,
StringVoltageAndCurrent, GridVoltageAndCurrent) Daten über die REST-API ab und erstellt für jeden Endpunkt
die definierten Sensoren.

Die Basis-URL wird in der configuration.yaml definiert, z. B.:
  
  bosch_bpt_inverter:
    resource: "http://192.168.xxx.xxx"

Die Debug-Logeinträge werden nur ausgegeben, wenn DEBUG_LOGGING auf True gesetzt ist.

"""

from datetime import timedelta
import logging
import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bosch_bpt_inverter"

# Setze DEBUG_LOGGING auf True, um zusätzliche Logausgaben zu aktivieren.
DEBUG_LOGGING = False

# Scan-Intervalle für die einzelnen Endpunkte
ENDPOINT_INTERVALS = {
    "YieldStatus": timedelta(seconds=300),
    "InverterInfo": timedelta(hours=1),
    "DcPower": timedelta(seconds=60),
    "AcPower": timedelta(seconds=60),
    "StringVoltageAndCurrent": timedelta(seconds=60),
    "GridVoltageAndCurrent": timedelta(seconds=60),
}

# Sensordefinitionen pro Endpunkt
# Jede Definition: (key, Name, Icon, Einheit, device_class, state_class)
# Für energy-Sensoren, die nicht kumulativ sein sollen (z. B. yieldDaily, yieldYearly), wird state_class explizit auf None gesetzt.
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
        ("numberOfStringInputs", "String-Eingänge", "mdi:connections", None, None, None),
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


class BoschInverterCoordinator(DataUpdateCoordinator):
    """Koordinator zum Abrufen der Daten für einen bestimmten Endpunkt.

    Setzt die URL aus der Basis-URL und dem Query-Parameter 'rName'.
    """

    def __init__(self, hass: HomeAssistant, resource: str, headers: dict, scan_interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN} {resource}", update_interval=scan_interval)
        self.resource = resource
        self.headers = headers

    async def _async_update_data(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(10):
                    # ssl=False unterbindet SSL-Prüfung, da der Wechselrichter HTTP nutzt.
                    async with session.get(self.resource, headers=self.headers, ssl=False) as response:
                        if response.status != 200:
                            raise UpdateFailed(f"Fehlerhafte Antwort: {response.status}")
                        return await response.json(content_type=None)
        except Exception as err:
            raise UpdateFailed(f"Fehler beim Abrufen der Daten: {err}")


class BoschInverterSensor(SensorEntity):
    """Sensor für einen bestimmten Wert des Bosch Wechselrichters, basierend auf einem Endpunkt.

    Wandelt numerische Werte (sofern eine Einheit definiert ist) in Float um und rundet auf zwei Dezimalstellen.
    Gibt bei Sensoren ohne definierte Einheit (z. B. Seriennummer, Modell) den Rohwert als String zurück.
    """

    def __init__(self, coordinator: DataUpdateCoordinator, endpoint: str,
                 key: str, name: str, icon: str, unit: str | None,
                 device_class: str | None, state_class: str | None) -> None:
        self.coordinator = coordinator
        self.endpoint = endpoint
        self.key = key
        self._attr_name = f"Bosch Wechselrichter {name}"
        self._attr_unique_id = f"bpt/{endpoint}/{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        # Für energy-Sensoren übernehmen wir den übergebenen state_class-Wert (muss None oder total/total_increasing sein).
        # Für andere Sensoren wird, falls keine state_class definiert wurde und eine Einheit vorliegt, "measurement" verwendet.
        if device_class == "energy":
            self._attr_state_class = state_class
        else:
            self._attr_state_class = state_class if state_class is not None else ("measurement" if unit is not None else None)

    @property
    def native_value(self) -> any:
        raw = self.coordinator.data.get(self.key)
        if self._attr_native_unit_of_measurement is not None:
            try:
                return round(float(raw), 2)
            except (ValueError, TypeError):
                return raw
        return raw

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities: AddEntitiesCallback, discovery_info=None
) -> None:
    """Initialisiert alle Sensoren der Bosch BPT Inverter Integration.

    Für jeden definierten Endpunkt wird ein DataUpdateCoordinator erstellt und die zugehörigen Sensoren
    gemäß SENSOR_DEFINITIONS erzeugt.
    """
    if DEBUG_LOGGING:
        _LOGGER.warning("Bosch BPT Inverter Sensoren werden eingerichtet (Plattformsetup)!")
    conf = hass.data.get(DOMAIN)
    if not conf:
        _LOGGER.error("Konfigurationsdaten nicht gefunden!")
        return
    base_resource = conf.get("resource")
    if not base_resource:
        _LOGGER.error("Resource URL nicht in der Konfiguration gefunden!")
        return
    headers = {"Authorization": "Basic QWxsOkFsbA=="}

    entities = []
    for endpoint, scan_interval in ENDPOINT_INTERVALS.items():
        resource = f"{base_resource}/pvi?rName={endpoint}"
        coordinator = BoschInverterCoordinator(hass, resource, headers, scan_interval)
        await coordinator.async_refresh()
        sensor_defs = SENSOR_DEFINITIONS.get(endpoint, [])
        for sensor_def in sensor_defs:
            key, name, icon, unit, device_class, state_class = sensor_def
            entities.append(BoschInverterSensor(coordinator, endpoint, key, name, icon, unit, device_class, state_class))
    async_add_entities(entities)

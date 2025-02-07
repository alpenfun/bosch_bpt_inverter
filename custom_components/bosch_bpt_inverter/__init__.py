"""Bosch BPT-S 4.6 PV Inverter Integration."""
import logging
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

DOMAIN = "bosch_bpt_inverter"
_LOGGER = logging.getLogger(__name__)

# Setze DEBUG_LOGGING auf True, um zusätzliche Logausgaben zu aktivieren.
DEBUG_LOGGING = False

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setzt die Integration über die configuration.yaml auf.

    Speichert die Konfigurationsdaten in hass.data und lädt die Sensor-Plattform.
    """
    if DOMAIN not in config:
        return False

    conf = config[DOMAIN]
    hass.data.setdefault(DOMAIN, conf)

    if DEBUG_LOGGING:
        _LOGGER.warning("Bosch BPT Inverter Integration wird geladen!")
        _LOGGER.warning(f"Konfigurationsdatei erkannt: {conf}")

    # Lade die Sensor-Plattform (Legacy-Plattform-Setup)
    hass.async_create_task(
        async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    return True

__all__ = ["BoschBPTInverterEntity"]

class BoschBPTInverterEntity(CoordinatorEntity):
    """Basisklasse für Bosch BPT Inverter Sensoren."""
    def __init__(self, coordinator):
        super().__init__(coordinator)

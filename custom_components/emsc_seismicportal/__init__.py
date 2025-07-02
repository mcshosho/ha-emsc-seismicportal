"""
Custom integration to integrate sesimicpotal from emsc with Home Assistant.

For more details about this integration, please refer to
https://github.com/mcshosho/ha-emsc-sesismicportal
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # noqa: ARG001
    """Set up the EMSC Seismic Portal component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EMSC Earthquake from a config entry."""
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the config entry to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the sensor platform
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    # Remove data
    hass.data[DOMAIN].pop(entry.entry_id)
    return True

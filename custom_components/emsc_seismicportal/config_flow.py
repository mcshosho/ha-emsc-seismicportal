"""Adds config flow for Earthquake sensors."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback

from .const import (  # Define these constants in a `const.py` file
    DEFAULT_HISTORY_LENGTH,
    DEFAULT_NAME,
    DOMAIN,
)


class EMSCEarthquakeFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EMSC Earthquake integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Get the coordinates of zone.home
        home_zone = self.hass.states.get("zone.home")
        if home_zone:
            home_latitude = home_zone.attributes.get(CONF_LATITUDE)
            home_longitude = home_zone.attributes.get(CONF_LONGITUDE)
        else:
            home_latitude = None
            home_longitude = None

        if user_input is not None:
            # Save the configuration
            return self.async_create_entry(
                title=user_input.get("name", DEFAULT_NAME),
                data=user_input,
            )

        # Default form schema
        schema = vol.Schema(
            {
                vol.Optional("name", default=DEFAULT_NAME): str,
                vol.Required("center_latitude", default=home_latitude): vol.Coerce(
                    float
                ),
                vol.Required("center_longitude", default=home_longitude): vol.Coerce(
                    float
                ),
                vol.Required("radius_km"): vol.Coerce(float),
                vol.Required("min_mag"): vol.Coerce(float),
                vol.Required("total_max_mag"): vol.Coerce(float),
                vol.Required(
                    "history_length", default=DEFAULT_HISTORY_LENGTH
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> EMSCEarthquakeOptionsFlowHandler:
        """Get the options flow for this handler."""
        return EMSCEarthquakeOptionsFlowHandler()


class EMSCEarthquakeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for EMSC Earthquake integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options for the custom integration."""
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input, options=self.config_entry.options
            )
            return self.async_create_entry(
                title=self.config_entry.title, data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(
                    "center_latitude",
                    default=self.config_entry.data.get("center_latitude"),
                ): vol.Coerce(float),
                vol.Required(
                    "center_longitude",
                    default=self.config_entry.data.get("center_longitude"),
                ): vol.Coerce(float),
                vol.Required(
                    "radius_km",
                    default=self.config_entry.data.get("radius_km"),
                ): vol.Coerce(float),
                vol.Required(
                    "min_mag",
                    default=self.config_entry.data.get("min_mag"),
                ): vol.Coerce(float),
                vol.Required(
                    "total_max_mag",
                    default=self.config_entry.data.get("total_max_mag"),
                ): vol.Coerce(float),
                vol.Required(
                    "history_length",
                    default=self.config_entry.data.get(
                        "history_length", DEFAULT_HISTORY_LENGTH
                    ),
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

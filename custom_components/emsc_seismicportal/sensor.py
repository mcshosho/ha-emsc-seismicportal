import asyncio
import json
import logging
import ssl
from concurrent.futures import ThreadPoolExecutor
from math import atan2, cos, radians, sin, sqrt

import aiohttp
import websockets
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_HISTORY_LENGTH,
    DEFAULT_NAME,
    DOMAIN,
    PING_INTERVAL,
    WEBSOCKET_URL,
)

_LOGGER = logging.getLogger(__name__)

ssl_executor = ThreadPoolExecutor(max_workers=1)


class EarthquakeHistory:
    def __init__(self, max_len=10):
        self.max_len = max_len
        self._history = []

    def add_or_update(self, quake):
        for idx, q in enumerate(self._history):
            if q["unid"] == quake["unid"]:
                self._history[idx] = quake
                return
        self._history.insert(0, quake)
        self._history = self._history[: self.max_len]

    def update_by_unid(self, unid, new_data):
        for idx, q in enumerate(self._history):
            if q["unid"] == unid:
                self._history[idx].update(new_data)
                return True
        return False

    def get_history(self):
        return list(self._history)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up EMSC Earthquake sensor based on a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]

    name = config.get("name", DEFAULT_NAME)
    center_latitude = config.get("center_latitude")
    center_longitude = config.get("center_longitude")
    radius_km = config.get("radius_km")
    total_max_mag = config.get("total_max_mag")
    min_mag = config.get("min_mag")

    history = EarthquakeHistory(max_len=DEFAULT_HISTORY_LENGTH)
    sensor = EMSCEarthquakeSensor(
        hass,
        name,
        center_latitude,
        center_longitude,
        radius_km,
        min_mag,
        total_max_mag,
        history,
    )
    history_sensor = EMSCEarthquakeHistorySensor(history)
    async_add_entities([sensor, history_sensor], True)
    hass.loop.create_task(sensor.connect_to_websocket())


class EMSCEarthquakeSensor(RestoreEntity, SensorEntity):
    """Representation of an EMSC Earthquake sensor."""

    def __init__(
        self,
        hass,
        name,
        center_latitude,
        center_longitude,
        radius_km,
        min_mag,
        total_max_mag,
        history,
    ):
        """Initialize the sensor."""
        self.hass = hass
        self._name = name
        self._state = None
        self._attributes = {}
        self._ssl_context = None
        self.center_latitude = center_latitude
        self.center_longitude = center_longitude
        self.radius_km = radius_km
        self.total_max_mag = total_max_mag
        self.min_mag = min_mag
        self.history = history
        self._last_unid = None

    @property
    def name(self):
        # Return the name of the sensor.
        return self._name

    @property
    def state(self):
        # Return the state of the sensor.
        return self._state

    @property
    def extra_state_attributes(self):
        # Return additional attributes of the sensor.
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this sensor."""
        return f"emsc_earthquake_{self._name}"

    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:waveform"

    async def connect_to_websocket(self):
        # Connect to the EMSC WebSocket API and process messages.
        while True:
            try:
                # Create SSL context in a separate thread
                self._ssl_context = await self.async_create_ssl_context()

                _LOGGER.info("Connecting to WebSocket: %s", WEBSOCKET_URL)
                async with websockets.connect(
                    WEBSOCKET_URL, ssl=self._ssl_context, ping_interval=PING_INTERVAL
                ) as websocket:
                    _LOGGER.info("Connected to WebSocket. Listening for messages...")
                    await self.listen_to_websocket(websocket)
            except Exception as e:
                _LOGGER.error("WebSocket error: %s", e)
                await asyncio.sleep(10)  # Retry after a delay

    async def async_create_ssl_context(self):
        # Create and return SSL context in a separate thread to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(ssl_executor, self.create_ssl_context)

    def create_ssl_context(self):
        # Create SSL context (blocking call, moved to separate thread).
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        return ssl_context

    async def listen_to_websocket(self, websocket):
        # Listen for messages on the WebSocket.
        try:
            async for message in websocket:
                await self.process_message(message)
        except websockets.ConnectionClosed:
            _LOGGER.warning("WebSocket connection closed.")
        except Exception as e:
            _LOGGER.error("Error while listening to WebSocket: %s", e)

    def is_within_radius(self, earthquake_latitude, earthquake_longitude):
        """Check if the given earthquake is within the specified radius."""
        # Calculate distance between central point and the earthquake location
        R = 6371.0  # Radius of Earth in kilometers

        lat1 = radians(self.center_latitude)
        lon1 = radians(self.center_longitude)
        lat2 = radians(earthquake_latitude)
        lon2 = radians(earthquake_longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = R * c
        _LOGGER.debug("Distance (km): %s", distance)

        return distance <= self.radius_km

    async def get_more_info_url(self, unid):
        url = (
            f"https://www.seismicportal.eu/eventid/api/convert"
            f"?source_id={unid}&source_catalog=UNID&out_catalog=EMSC"
        )
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(url) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json()

                    # Handle case where API returns a list
                    if isinstance(data, list):
                        if len(data) > 0 and isinstance(data[0], dict):
                            eventid = data[0].get("eventid")
                        else:
                            _LOGGER.warning(
                                "API returned empty list or invalid format for %s",
                                unid,
                            )
                            return None
                    # Handle case where API returns a dict
                    elif isinstance(data, dict):
                        eventid = data.get("eventid")
                    else:
                        _LOGGER.warning(
                            "API returned unexpected data type for %s: %s",
                            unid,
                            type(data),
                        )
                        return None
                    if eventid:
                        return f"https://www.emsc-csem.org/Earthquake/earthquake.php?id={eventid}"
                    else:
                        _LOGGER.warning("No eventid found in response for %s", unid)

        except Exception as e:
            _LOGGER.warning("Failed to fetch more_info for %s: %s", unid, e)
        return None

    async def process_message(self, message):
        # Process an incoming WebSocket message.
        _LOGGER.debug("Received WebSocket message: %s", message)
        try:
            data = json.loads(message)
            action = data.get("action", "unknown")
            info = data.get("data", {}).get("properties", {})

            lat = info.get("lat")
            lon = info.get("lon")
            mag = info.get("mag")
            unid = info.get("unid")

            if not (lat and lon and mag and unid):
                _LOGGER.info("Skipping event, missing required fields.")
                return

            more_info_url = await self.get_more_info_url(unid)

            quake_data = {
                "action": action,
                "unid": unid,
                "time": info.get("time"),
                "magnitude": mag,
                "region": info.get("flynn_region"),
                "depth": info.get("depth"),
                "lat": lat,
                "lon": lon,
                "magtype": info.get("magtype"),
                "more_info": more_info_url,
            }

            if (
                self.is_within_radius(lat, lon) and mag >= self.min_mag
            ) or mag >= self.total_max_mag:
                if action == "create":
                    self._state = mag
                    self._attributes = quake_data
                    self._last_unid = unid
                    self.history.add_or_update(quake_data)
                    _LOGGER.info("Processed new earthquake data: %s", quake_data)
                    self.async_write_ha_state()
                elif action == "update":
                    if self._last_unid == unid:
                        self._state = mag
                        self._attributes = quake_data
                        self.history.add_or_update(quake_data)
                        _LOGGER.info("Updated current earthquake data: %s", quake_data)
                        self.async_write_ha_state()
                    else:
                        updated = self.history.update_by_unid(unid, quake_data)
                        if updated:
                            _LOGGER.info(
                                "Updated earthquake in history: %s", quake_data
                            )
            else:
                # If the earthquake is outside the bounds, skip this event
                _LOGGER.info(
                    "Skipping event, parameters out of bounds: lat=%s, lon=%s", lat, lon
                )
                return
        except Exception as e:
            _LOGGER.error("Error processing WebSocket message: %s", e)

    async def async_added_to_hass(self):
        """Restore state and attributes on Home Assistant startup."""
        last_state = await self.async_get_last_state()
        if last_state:
            self._state = last_state.state
            self._attributes = dict(last_state.attributes)
            self._last_unid = self._attributes.get("unid")
            # Optionally, restore the latest quake to history
            if self._attributes and self.history is not None:
                self.history.add_or_update(self._attributes)


class EMSCEarthquakeHistorySensor(RestoreEntity, SensorEntity):
    def __init__(self, history, name="Earthquake History"):
        self._name = name
        self.history = history

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return len(self.history.get_history())

    @property
    def extra_state_attributes(self):
        return {"history": self.history.get_history()}

    @property
    def unique_id(self):
        """Return a unique ID for this sensor."""
        return f"emsc_earthquakes_history_{self._name}"

    @property
    def icon(self):
        return "mdi:history"

    async def async_added_to_hass(self):
        """Restore history on Home Assistant startup."""
        last_state = await self.async_get_last_state()
        if last_state:
            history_list = last_state.attributes.get("history", [])
            if self.history is not None:
                for quake in reversed(history_list):
                    self.history.add_or_update(quake)

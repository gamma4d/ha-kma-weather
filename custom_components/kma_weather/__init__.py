"""KMA (기상청) weather integration — official 동네예보 (data.go.kr) source.

UI-configured (config flow): Settings → Devices & Services → Add Integration →
"KMA Weather". The data.go.kr service key (DECODED 일반 인증키) is entered in the
UI and validated live before the entry is created.

Why KMA direct API: the official 동네예보 API is the most reliable, structurally
clear public Korean weather source (deterministic 8×/day issuance; all required
fields 온도/습도/강수확률/시간당강수량/최고최저기온/날씨상태 + forecast). Location →
5km grid (nx, ny), base_time scheduling, and value parsing live in kma.py; this
module wires a per-entry coordinator + weather/sensor platforms.

The DECODED key matters: aiohttp URL-encodes params once, so a URL-encoded
("Encoding") key would double-encode → auth failure. Use the "일반 인증키
(Decoding)" value from data.go.kr 마이페이지.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import kma
from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import KmaCoordinator

_LOGGER = logging.getLogger(__name__)

# Everything KMA provides lives in the single weather entity (current + hourly +
# daily forecast). No scattered per-field/per-step sensors.
PLATFORMS: list[Platform] = [Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a KMA weather config entry."""
    data = entry.data
    name = data.get(CONF_NAME, DEFAULT_NAME)
    lat = data.get(CONF_LATITUDE, hass.config.latitude)
    lon = data.get(CONF_LONGITUDE, hass.config.longitude)
    nx, ny = kma.latlon_to_grid(lat, lon)

    coordinator = KmaCoordinator(
        hass,
        name=name,
        api_key=data[CONF_API_KEY],
        nx=nx,
        ny=ny,
        update_interval=DEFAULT_SCAN_INTERVAL,
    )
    # Raises ConfigEntryNotReady on a failed first fetch → HA retries setup.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "KMA weather '%s' set up at grid (nx=%d, ny=%d) from (%.4f, %.4f)",
        name, nx, ny, lat, lon,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a KMA weather config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

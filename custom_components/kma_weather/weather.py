"""KMA weather entity — the single entity holding all KMA-provided data.

Current conditions (temperature/humidity/condition/wind) as entity state +
attributes, plus the full hourly (24h) and daily (~5d) forecast via the native
async_forecast_hourly/daily methods (consumed through `weather.get_forecasts`).
No separate per-field/per-step sensors. See docs/18 §8 for the wiring.
"""

from __future__ import annotations

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DATA_CURRENT, DATA_DAILY, DATA_HOURLY, DEFAULT_NAME, DOMAIN
from .coordinator import KmaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the KMA weather entity from a config entry."""
    coordinator: KmaCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([KmaWeather(coordinator, name, entry.entry_id)])


class KmaWeather(CoordinatorEntity[KmaCoordinator], WeatherEntity):
    """A WeatherEntity backed by the KMA coordinator."""

    _attr_attribution = "기상청 (KMA) 동네예보 — data.go.kr"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(self, coordinator: KmaCoordinator, name: str, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_weather"

    @property
    def _current(self) -> dict:
        return (self.coordinator.data or {}).get(DATA_CURRENT, {})

    @property
    def condition(self) -> str | None:
        return self._current.get("condition")

    @property
    def native_temperature(self) -> float | None:
        return self._current.get("temperature")

    @property
    def humidity(self) -> float | None:
        return self._current.get("humidity")

    @property
    def native_wind_speed(self) -> float | None:
        return self._current.get("wind_speed")

    @property
    def wind_bearing(self) -> float | None:
        return self._current.get("wind_bearing")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return (self.coordinator.data or {}).get(DATA_HOURLY)

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return (self.coordinator.data or {}).get(DATA_DAILY)

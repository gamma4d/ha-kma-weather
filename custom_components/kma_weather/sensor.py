"""KMA sensors — flat current values + 1h/3h/daily forecast surfaces.

The flat numeric sensors (temperature / humidity / PoP / hourly precip / daily
max+min / condition) are what the room-node bridge reads. The three *forecast*
sensors carry the full ordered forecast list in their `forecast` attribute so any
consumer can pull 1h, 3h, or daily granularity without calling a service.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import kma
from .const import (
    CONF_NAME,
    DATA_3H,
    DATA_CURRENT,
    DATA_DAILY,
    DATA_HOURLY,
    DATA_PUBLISHED,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import KmaCoordinator

MM_PER_HOUR = "mm/h"


def _today_daily(data: dict) -> dict:
    daily = data.get(DATA_DAILY) or []
    today = dt_util.utcnow().astimezone(kma.KST).strftime("%Y-%m-%d")
    for d in daily:
        if d.get("datetime", "").startswith(today):
            return d
    return daily[0] if daily else {}


def _nearest_hourly(data: dict) -> dict:
    hourly = data.get(DATA_HOURLY) or []
    now_iso = dt_util.utcnow().astimezone(kma.KST).isoformat()
    upcoming = [h for h in hourly if h.get("datetime", "") >= now_iso]
    if upcoming:
        return upcoming[0]
    return hourly[-1] if hourly else {}


@dataclass(frozen=True, kw_only=True)
class KmaSensorDescription(SensorEntityDescription):
    """A KMA sensor with a value function over coordinator.data."""

    value_fn: Callable[[dict], object]
    attrs_fn: Callable[[dict], dict] | None = None


SENSORS: tuple[KmaSensorDescription, ...] = (
    KmaSensorDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get(DATA_CURRENT, {}).get("temperature"),
    ),
    KmaSensorDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get(DATA_CURRENT, {}).get("humidity"),
    ),
    KmaSensorDescription(
        key="precipitation",
        name="Precipitation",
        native_unit_of_measurement=MM_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        value_fn=lambda d: d.get(DATA_CURRENT, {}).get("precipitation"),
    ),
    KmaSensorDescription(
        key="precipitation_probability",
        name="Precipitation probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda d: _nearest_hourly(d).get("precipitation_probability"),
    ),
    KmaSensorDescription(
        key="temperature_max",
        name="Temperature max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-high",
        value_fn=lambda d: _today_daily(d).get("native_temperature"),
    ),
    KmaSensorDescription(
        key="temperature_min",
        name="Temperature min",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-low",
        value_fn=lambda d: _today_daily(d).get("native_templow"),
    ),
    KmaSensorDescription(
        key="condition",
        name="Condition",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda d: d.get(DATA_CURRENT, {}).get("condition"),
    ),
    # ---- forecast surfaces: state = a useful scalar, full list in `forecast` attr ----
    KmaSensorDescription(
        key="forecast_1h",
        name="Forecast 1h",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:clock-outline",
        value_fn=lambda d: _nearest_hourly(d).get("native_temperature"),
        attrs_fn=lambda d: {
            "forecast": d.get(DATA_HOURLY) or [],
            "published": d.get(DATA_PUBLISHED),
        },
    ),
    KmaSensorDescription(
        key="forecast_3h",
        name="Forecast 3h",
        icon="mdi:clock-time-three-outline",
        value_fn=lambda d: len(d.get(DATA_3H) or []),
        attrs_fn=lambda d: {
            "forecast": d.get(DATA_3H) or [],
            "published": d.get(DATA_PUBLISHED),
        },
    ),
    KmaSensorDescription(
        key="forecast_daily",
        name="Forecast daily",
        icon="mdi:calendar-week",
        value_fn=lambda d: len(d.get(DATA_DAILY) or []),
        attrs_fn=lambda d: {
            "forecast": d.get(DATA_DAILY) or [],
            "published": d.get(DATA_PUBLISHED),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KmaCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities(
        KmaSensor(coordinator, desc, name, entry.entry_id) for desc in SENSORS
    )


class KmaSensor(CoordinatorEntity[KmaCoordinator], SensorEntity):
    """A single KMA sensor driven by a KmaSensorDescription value function."""

    entity_description: KmaSensorDescription

    def __init__(
        self,
        coordinator: KmaCoordinator,
        description: KmaSensorDescription,
        device_name: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = f"{device_name} {description.name}"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})

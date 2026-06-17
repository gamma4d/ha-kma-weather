"""Constants for the KMA (기상청) weather integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "kma_weather"

# YAML config keys
CONF_API_KEY = "api_key"
CONF_NAME = "name"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_NAME = "KMA"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

# 기상청 공공데이터포털 (data.go.kr) 동네예보 조회서비스 2.0
BASE_VILAGE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
EP_NCST = f"{BASE_VILAGE}/getUltraSrtNcst"   # 초단기실황 (current obs)
EP_ULTRA = f"{BASE_VILAGE}/getUltraSrtFcst"  # 초단기예보 (6h, hourly)
EP_VILAGE = f"{BASE_VILAGE}/getVilageFcst"   # 단기예보 (3d, hourly)

# numOfRows per endpoint — 단기예보 returns many (categories × ~3 days of hours).
ROWS_NCST = 60
ROWS_ULTRA = 120
ROWS_VILAGE = 1000

# coordinator.data keys
DATA_CURRENT = "current"
DATA_HOURLY = "hourly"
DATA_3H = "three_hourly"
DATA_DAILY = "daily"
DATA_PUBLISHED = "published"  # forecast base datetime (ISO, KST)

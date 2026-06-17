"""KMA data coordinator — fetches 초단기실황 + 초단기예보 + 단기예보 and assembles
current conditions + 1h / 3h / daily forecasts via the pure core in kma.py."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import kma
from .const import (
    DATA_3H,
    DATA_CURRENT,
    DATA_DAILY,
    DATA_HOURLY,
    DATA_PUBLISHED,
    DEFAULT_SCAN_INTERVAL,
    EP_NCST,
    EP_ULTRA,
    EP_VILAGE,
    ROWS_NCST,
    ROWS_ULTRA,
    ROWS_VILAGE,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def async_test_key(hass: HomeAssistant, api_key: str, nx: int, ny: int) -> None:
    """One live 초단기실황 fetch to validate a key during config flow.

    Raises kma.KmaError (bad/inactive key, resultCode!=00) or UpdateFailed /
    aiohttp.ClientError (network/HTTP) — the config flow maps these to form errors.
    """
    coord = KmaCoordinator(
        hass, name="validate", api_key=api_key, nx=nx, ny=ny,
        update_interval=DEFAULT_SCAN_INTERVAL,
    )
    now = dt_util.utcnow().astimezone(kma.KST)
    d, t = kma.ultra_ncst_base(now)
    await coord._fetch(EP_NCST, d, t, ROWS_NCST)


class KmaCoordinator(DataUpdateCoordinator):
    """Polls KMA on a fixed cadence and exposes assembled weather data."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str,
        api_key: str,
        nx: int,
        ny: int,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"KMA {name}",
            update_interval=update_interval,
        )
        self._session = async_get_clientsession(hass)
        self._api_key = api_key
        self._nx = nx
        self._ny = ny

    async def _fetch(self, url: str, base_date: str, base_time: str, rows: int) -> list[dict]:
        """One KMA GET -> item list. serviceKey passed via params (aiohttp encodes
        it once — supply the *decoded* data.go.kr key, NOT the URL-encoded one)."""
        params = {
            "serviceKey": self._api_key,
            "pageNo": "1",
            "numOfRows": str(rows),
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": str(self._nx),
            "ny": str(self._ny),
        }
        async with self._session.get(url, params=params, timeout=_TIMEOUT) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise UpdateFailed(f"KMA HTTP {resp.status} for {url}: {text[:200]}")
            try:
                payload = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as exc:
                # data.go.kr returns an XML <OpenAPI_ServiceResponse> error (e.g. bad
                # key / quota) with HTTP 200 — surface it instead of silently failing.
                raise UpdateFailed(f"KMA non-JSON response for {url}: {text[:200]}") from exc
        return kma.extract_items(payload)

    async def _async_update_data(self) -> dict:
        now = dt_util.utcnow().astimezone(kma.KST)
        n_date, n_time = kma.ultra_ncst_base(now)
        u_date, u_time = kma.ultra_fcst_base(now)
        v_date, v_time = kma.vilage_base(now)
        try:
            ncst, ultra, vilage = await asyncio.gather(
                self._fetch(EP_NCST, n_date, n_time, ROWS_NCST),
                self._fetch(EP_ULTRA, u_date, u_time, ROWS_ULTRA),
                self._fetch(EP_VILAGE, v_date, v_time, ROWS_VILAGE),
            )
        except kma.KmaError as exc:
            raise UpdateFailed(f"KMA API error: {exc}") from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise UpdateFailed(f"KMA request failed: {exc}") from exc

        # Hourly = 초단기예보 (next 6h, finer) overlaid on 단기예보 (out to ~3d).
        hourly = kma.merge_hourly(ultra, vilage)

        # forecast issuance time = 단기예보 base_date+base_time (KST)
        published = datetime(
            int(v_date[0:4]), int(v_date[4:6]), int(v_date[6:8]),
            int(v_time[0:2]), int(v_time[2:4]), tzinfo=kma.KST,
        ).isoformat()

        return {
            DATA_CURRENT: kma.build_current(ncst, vilage, now),
            DATA_HOURLY: hourly,
            DATA_3H: kma.build_3h(hourly),
            DATA_DAILY: kma.build_daily(vilage),
            DATA_PUBLISHED: published,
        }

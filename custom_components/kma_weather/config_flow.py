"""UI config flow for the KMA weather integration.

Lets the user enter the data.go.kr service key (and optional location) from
Settings → Devices & Services → Add Integration → KMA Weather, with a LIVE key
validation step so a wrong/inactive key is rejected immediately (instead of
silently producing unavailable entities)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import slugify

from . import kma
from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import async_test_key

_LOGGER = logging.getLogger(__name__)


class KmaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the KMA weather config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            api_key = user_input[CONF_API_KEY].strip()
            nx, ny = kma.latlon_to_grid(lat, lon)

            await self.async_set_unique_id(slugify(name))
            self._abort_if_unique_id_configured()

            try:
                await async_test_key(self.hass, api_key, nx, ny)
            except kma.KmaError as exc:
                # resultCode != 00 — most often the key is wrong, or issued <1-2h
                # ago and not yet active.
                _LOGGER.warning("KMA key validation rejected: %s", exc)
                errors["base"] = "invalid_auth"
            except (UpdateFailed, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                _LOGGER.warning("KMA connection failed during validation: %s", exc)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_API_KEY: api_key,
                        CONF_NAME: name,
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                    },
                )

        suggested = user_input or {}
        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=suggested.get(CONF_API_KEY, "")): str,
                vol.Optional(CONF_NAME, default=suggested.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Optional(
                    CONF_LATITUDE,
                    default=suggested.get(CONF_LATITUDE, self.hass.config.latitude),
                ): cv.latitude,
                vol.Optional(
                    CONF_LONGITUDE,
                    default=suggested.get(CONF_LONGITUDE, self.hass.config.longitude),
                ): cv.longitude,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

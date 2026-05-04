from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AspenDiscoveryAuthError, AspenDiscoveryClient, AspenDiscoveryConnectionError
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class AspenDiscoveryData:
    summary: dict[str, Any] = field(default_factory=dict)
    checkouts: list[dict[str, Any]] = field(default_factory=list)


class AspenDiscoveryCoordinator(DataUpdateCoordinator[AspenDiscoveryData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
        )
        self.client = AspenDiscoveryClient(
            base_url=entry.data[CONF_URL],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> AspenDiscoveryData:
        # Re-login on every update — session expires after ~24 min inactivity
        # and we poll hourly, so maintaining state across polls isn't worthwhile.
        try:
            await self.client.login()
        except AspenDiscoveryAuthError as err:
            raise ConfigEntryAuthFailed from err
        except AspenDiscoveryConnectionError as err:
            raise UpdateFailed(f"Cannot connect to library: {err}") from err

        try:
            summary = await self.client.get_ils_summary()
            checkouts = await self.client.get_checkouts()
        except AspenDiscoveryConnectionError as err:
            raise UpdateFailed(f"Cannot connect to library: {err}") from err

        return AspenDiscoveryData(summary=summary, checkouts=checkouts)

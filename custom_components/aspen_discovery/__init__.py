from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .api import AspenDiscoveryConnectionError
from .const import DOMAIN
from .coordinator import AspenDiscoveryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "calendar"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AspenDiscoveryCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, "renew_all"):

        async def renew_all(call: ServiceCall) -> None:
            for coord in hass.data.get(DOMAIN, {}).values():
                if not isinstance(coord, AspenDiscoveryCoordinator):
                    continue
                try:
                    result = await coord.client.renew_all()
                    _LOGGER.info(
                        "Renew all for %s: %s",
                        (coord.config_entry.title if hasattr(coord, "config_entry") else "library"),
                        result.get("renewalMessage", result),
                    )
                except AspenDiscoveryConnectionError as err:
                    _LOGGER.error("Renew all failed: %s", err)

        hass.services.async_register(DOMAIN, "renew_all", renew_all)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: AspenDiscoveryCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()

        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "renew_all")

    return unload_ok

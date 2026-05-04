from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import (
    AspenDiscoveryAuthError,
    AspenDiscoveryClient,
    AspenDiscoveryConnectionError,
)
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _normalise_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


class AspenDiscoveryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = _normalise_url(user_input[CONF_URL])
            username = user_input[CONF_USERNAME].strip().replace(" ", "")
            password = user_input[CONF_PASSWORD]

            client = AspenDiscoveryClient(
                base_url=url,
                username=username,
                password=password,
            )
            try:
                patron_name = await client.login()
            except AspenDiscoveryAuthError:
                errors["base"] = "invalid_auth"
            except AspenDiscoveryConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                host = urlparse(url).netloc
                await self.async_set_unique_id(f"{host}_{username}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"{patron_name} @ {host}",
                    data={
                        CONF_URL: url,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
            finally:
                await client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

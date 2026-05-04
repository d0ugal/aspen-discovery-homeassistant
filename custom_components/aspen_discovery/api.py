from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant/AspenDiscovery)",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class AspenDiscoveryAuthError(Exception):
    pass


class AspenDiscoveryConnectionError(Exception):
    pass


class AspenDiscoveryClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self.patron_name: str = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(),
                headers=_HEADERS,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> str:
        """Login via AJAX and return the patron's display name."""
        session = await self._get_session()
        try:
            async with session.post(
                f"{self._base_url}/AJAX/JSON",
                params={"method": "loginUser"},
                data={
                    "username": self._username,
                    "password": self._password,
                    "rememberMe": "false",
                },
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise AspenDiscoveryConnectionError(str(err)) from err

        result = data.get("result", {})
        if not result.get("success"):
            raise AspenDiscoveryAuthError("Invalid credentials")

        self.patron_name = result.get("name", "Library patron")
        return self.patron_name

    async def get_ils_summary(self) -> dict[str, Any]:
        """Fetch ILS account summary with checkout, hold and fine counts."""
        session = await self._get_session()
        try:
            async with session.get(
                f"{self._base_url}/MyAccount/AJAX",
                params={"method": "getMenuDataIls"},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise AspenDiscoveryConnectionError(str(err)) from err

        if not data.get("success"):
            return {}
        return data.get("summary", {})

    async def get_checkouts(self) -> list[dict[str, Any]]:
        """Fetch detailed checkout list with per-item due dates.

        Some libraries restrict the /API/UserAPI endpoint by IP. If blocked,
        returns an empty list so sensors still work via get_ils_summary().
        """
        session = await self._get_session()
        try:
            async with session.post(
                f"{self._base_url}/API/UserAPI",
                params={"method": "getPatronCheckedOutItems"},
                data={
                    "username": self._username,
                    "password": self._password,
                    "source": "ils",
                },
            ) as resp:
                if resp.status in (403, 401):
                    _LOGGER.debug(
                        "API endpoint blocked (status %s) — calendar events unavailable",
                        resp.status,
                    )
                    return []
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            _LOGGER.debug("Could not fetch detailed checkouts: %s", err)
            return []

        result = data.get("result", data)
        if not result.get("success"):
            return []
        return result.get("checkedOutItems", [])

    async def renew_all(self) -> dict[str, Any]:
        """Renew all eligible checkouts. Returns the API response dict."""
        session = await self._get_session()
        try:
            async with session.post(
                f"{self._base_url}/API/UserAPI",
                params={"method": "renewAll"},
                data={
                    "username": self._username,
                    "password": self._password,
                },
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise AspenDiscoveryConnectionError(str(err)) from err

        return data.get("result", data)

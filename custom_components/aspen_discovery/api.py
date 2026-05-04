from __future__ import annotations

import calendar as _cal
import logging
from datetime import datetime
from html.parser import HTMLParser
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


class _CheckoutsParser(HTMLParser):
    """Extract checkout records from the HTML fragment returned by getCheckouts AJAX.

    Each checkout block is a <div class="result row [bg-overdue]"> containing
    a result-title span/a and a "Due" label/value pair.
    """

    def __init__(self) -> None:
        super().__init__()
        self._results: list[dict] = []
        self._current: dict | None = None
        self._depth = 0
        self._record_depth: int | None = None
        self._in_title = False
        self._in_label = False
        self._after_due_label = False
        self._in_due_value = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        ad = dict(attrs)
        class_list = ad.get("class", "").split()

        if tag == "div":
            if "result" in class_list and "row" in class_list and self._current is None:
                self._record_depth = self._depth
                self._current = {
                    "title": "",
                    "dueDate": None,
                    "overdue": "bg-overdue" in class_list,
                }
            # Only track div depth — void elements (input, img) never call handle_endtag
            # so including them would permanently drift the counter.
            self._depth += 1

        if self._current is None:
            return

        if tag in ("a", "span") and "result-title" in class_list and "notranslate" in class_list:
            self._in_title = True

        if tag == "div" and "result-label" in class_list:
            self._in_label = True
            self._after_due_label = False

        if tag == "div" and "result-value" in class_list and self._after_due_label:
            self._in_due_value = True
            self._after_due_label = False

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "span"):
            self._in_title = False

        if tag == "div":
            self._depth -= 1

            if self._in_label:
                self._in_label = False
            if self._in_due_value:
                self._in_due_value = False

            if (
                self._record_depth is not None
                and self._depth == self._record_depth
                and self._current is not None
            ):
                if self._current["title"] and self._current["dueDate"]:
                    self._results.append(self._current)
                self._current = None
                self._record_depth = None

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return

        if self._in_title and self._current is not None and not self._current["title"]:
            self._current["title"] = stripped
            self._in_title = False

        if self._in_label:
            self._after_due_label = stripped.lower() == "due"

        if self._in_due_value and self._current is not None and not self._current["dueDate"]:
            # Smarty date_format default: '%b %e, %Y' → "May  4, 2026" (space-padded day)
            date_str = " ".join(stripped.split())
            try:
                dt = datetime.strptime(date_str, "%b %d, %Y")
                self._current["dueDate"] = _cal.timegm(dt.timetuple())
            except ValueError:
                pass

    @property
    def results(self) -> list[dict]:
        return self._results


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

        Tries the JSON UserAPI first; falls back to parsing the session-based
        AJAX HTML response for libraries that block UserAPI by IP.
        """
        result = await self._get_checkouts_via_api()
        if result is not None:
            return result
        return await self._get_checkouts_via_ajax()

    async def _get_checkouts_via_api(self) -> list[dict[str, Any]] | None:
        """JSON UserAPI path — returns None if the endpoint is blocked."""
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
                    _LOGGER.debug("UserAPI blocked (status %s), falling back to AJAX", resp.status)
                    return None
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            _LOGGER.debug("UserAPI fetch failed: %s", err)
            return None

        result = data.get("result", data)
        if not result.get("success"):
            return None
        return result.get("checkedOutItems", [])

    async def _get_checkouts_via_ajax(self) -> list[dict[str, Any]]:
        """Session AJAX path — parses the HTML fragment returned by getCheckouts."""
        session = await self._get_session()
        try:
            async with session.get(
                f"{self._base_url}/MyAccount/AJAX",
                params={"method": "getCheckouts", "source": "ils"},
            ) as resp:
                if resp.status in (403, 401):
                    return []
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            _LOGGER.debug("AJAX checkout fetch failed: %s", err)
            return []

        if not data.get("success"):
            return []

        parser = _CheckoutsParser()
        parser.feed(data.get("checkouts", ""))
        _LOGGER.debug("Parsed %d checkouts from AJAX HTML", len(parser.results))
        return parser.results

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

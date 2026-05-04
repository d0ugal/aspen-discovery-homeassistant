from __future__ import annotations

import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AspenDiscoveryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AspenDiscoveryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AspenDiscoveryCalendar(coordinator, entry)])


def _effective_due(checkout: dict) -> datetime.date | None:
    due_ts = checkout.get("dueDate")
    if not due_ts:
        return None
    due = datetime.date.fromtimestamp(int(due_ts))
    # Overdue items are clamped to today so they appear in the current calendar view.
    return max(due, datetime.date.today())


def _checkout_to_event(checkout: dict) -> CalendarEvent | None:
    due = _effective_due(checkout)
    if due is None:
        return None
    return CalendarEvent(
        start=due,
        end=due + datetime.timedelta(days=1),
        summary=checkout.get("title", "Library item"),
        description=checkout.get("author") or "",
    )


class AspenDiscoveryCalendar(
    CoordinatorEntity[AspenDiscoveryCoordinator], CalendarEntity
):
    _attr_has_entity_name = True
    _attr_name = "Due dates"

    def __init__(
        self, coordinator: AspenDiscoveryCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Aspen Discovery",
        )

    @property
    def event(self) -> CalendarEvent | None:
        checkouts_with_due = [c for c in self.coordinator.data.checkouts if c.get("dueDate")]
        if not checkouts_with_due:
            return None
        soonest = min(checkouts_with_due, key=lambda c: _effective_due(c) or datetime.date.max)
        return _checkout_to_event(soonest)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        start = start_date.date()
        end = end_date.date()
        events = []
        for checkout in self.coordinator.data.checkouts:
            due = _effective_due(checkout)
            if due is None:
                continue
            if start <= due < end:
                event = _checkout_to_event(checkout)
                if event:
                    events.append(event)
        return events

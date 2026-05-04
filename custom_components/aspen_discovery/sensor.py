from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AspenDiscoveryCoordinator


@dataclass(frozen=True)
class AspenSensorEntityDescription(SensorEntityDescription):
    summary_key: str = ""


SENSOR_DESCRIPTIONS: tuple[AspenSensorEntityDescription, ...] = (
    AspenSensorEntityDescription(
        key="checked_out",
        name="Books checked out",
        icon="mdi:book-open",
        native_unit_of_measurement="books",
        state_class=SensorStateClass.MEASUREMENT,
        summary_key="numCheckedOut",
    ),
    AspenSensorEntityDescription(
        key="overdue",
        name="Books overdue",
        icon="mdi:book-alert",
        native_unit_of_measurement="books",
        state_class=SensorStateClass.MEASUREMENT,
        summary_key="numOverdue",
    ),
    AspenSensorEntityDescription(
        key="holds_ready",
        name="Holds ready to collect",
        icon="mdi:book-check",
        native_unit_of_measurement="holds",
        state_class=SensorStateClass.MEASUREMENT,
        summary_key="numAvailableHolds",
    ),
    AspenSensorEntityDescription(
        key="holds_waiting",
        name="Holds waiting",
        icon="mdi:book-clock",
        native_unit_of_measurement="holds",
        state_class=SensorStateClass.MEASUREMENT,
        summary_key="numUnavailableHolds",
    ),
    AspenSensorEntityDescription(
        key="fines",
        name="Outstanding fines",
        icon="mdi:cash",
        state_class=SensorStateClass.MEASUREMENT,
        summary_key="totalFines",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AspenDiscoveryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AspenDiscoverySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class AspenDiscoverySensor(CoordinatorEntity[AspenDiscoveryCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: AspenSensorEntityDescription

    def __init__(
        self,
        coordinator: AspenDiscoveryCoordinator,
        entry: ConfigEntry,
        description: AspenSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Aspen Discovery",
        )

    @property
    def native_value(self) -> int | float | None:
        return self.coordinator.data.summary.get(self.entity_description.summary_key)

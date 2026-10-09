"""Sensors exposed per parcel: status, estimated delivery, last event."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_ICON,
    OPT_PARCELS,
    PUBLIC_TRACKING_URL,
    STATUS_ICONS,
)
from .coordinator import Ship24Coordinator
from .entity import Ship24Entity
from . import Ship24ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ship24ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the three sensors for each configured parcel."""
    coordinator: Ship24Coordinator = entry.runtime_data
    entities = [
        sensor
        for parcel in entry.options.get(OPT_PARCELS, [])
        for sensor in (
            Ship24StatusSensor(coordinator, parcel),
            Ship24EstimatedDeliverySensor(coordinator, parcel),
            Ship24LastEventSensor(coordinator, parcel),
        )
    ]
    async_add_entities(entities)


class Ship24StatusSensor(Ship24Entity, SensorEntity):
    """Overall parcel status (Ship24 status milestone)."""

    _attr_translation_key = "status"

    def __init__(self, coordinator, parcel) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator, parcel, "status")

    @property
    def native_value(self) -> str | None:
        """Return the status milestone, e.g. in_transit, delivered."""
        if (data := self.tracking_data) is None:
            return None
        return data.status

    @property
    def icon(self) -> str:
        """Icon matching the status."""
        status = self.tracking_data.status if self.tracking_data else None
        return STATUS_ICONS.get(status, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the useful raw fields for templates and automations."""
        data = self.tracking_data
        if data is None:
            return {"tracking_number": self.parcel["tracking_number"]}
        last_event = data.last_event
        attributes: dict[str, Any] = {
            "tracking_number": data.tracking_number
            or self.parcel["tracking_number"],
            "status_code": data.status_code,
            "status_category": data.status_category,
            "courier": last_event.courier_code if last_event else None,
            "origin_country": data.origin_country,
            "destination_country": data.destination_country,
            "service": data.service,
            "signed_by": data.signed_by,
            "delivered_at": data.delivered_at.isoformat()
            if data.delivered_at
            else None,
            "tracking_url": PUBLIC_TRACKING_URL.format(
                tracking_number=data.tracking_number
                or self.parcel["tracking_number"]
            ),
        }
        return attributes


class Ship24EstimatedDeliverySensor(Ship24Entity, SensorEntity):
    """Estimated delivery date of the parcel (timestamp)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "estimated_delivery"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, parcel) -> None:
        """Initialize the estimated delivery sensor."""
        super().__init__(coordinator, parcel, "estimated_delivery")

    @property
    def native_value(self) -> str | None:
        """Best estimate: Ship24 estimate, else the courier's latest, else earliest."""
        data = self.tracking_data
        if data is None:
            return None
        moment = (
            data.estimated_delivery_date
            or data.delivery_to
            or data.delivery_from
        )
        return moment.isoformat() if moment else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the courier's delivery window."""
        data = self.tracking_data
        if data is None:
            return {}
        return {
            "delivery_window_from": data.delivery_from.isoformat()
            if data.delivery_from
            else None,
            "delivery_window_to": data.delivery_to.isoformat()
            if data.delivery_to
            else None,
            "service": data.service,
        }


class Ship24LastEventSensor(Ship24Entity, SensorEntity):
    """Most recent tracking event."""

    _attr_translation_key = "last_event"
    _attr_icon = "mdi:history"

    def __init__(self, coordinator, parcel) -> None:
        """Initialize the last event sensor."""
        super().__init__(coordinator, parcel, "last_event")

    @property
    def native_value(self) -> str | None:
        """Raw event text, e.g. 'Delivered to the addressee'."""
        data = self.tracking_data
        if data is None or (event := data.last_event) is None:
            return None
        return event.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Datetime, location and courier of the last event."""
        data = self.tracking_data
        if data is None or (event := data.last_event) is None:
            return {}
        return {
            "occurrence_datetime": event.occurrence_datetime.isoformat()
            if event.occurrence_datetime
            else None,
            "location": event.location,
            "courier": event.courier_code,
            "status_code": event.status_code,
            "status_milestone": event.status_milestone,
        }

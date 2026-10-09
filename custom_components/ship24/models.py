"""Data models for Ship24 tracking data (pure Python, no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def parse_logistics_datetime(value: str | None) -> datetime | None:
    """Parse a Ship24 "logistics date and time".

    Ship24 returns several shapes:
      - "2021-03-04T17:12:57"          (naive, treat as UTC)
      - "2021-03-04T10:12:57.000Z"     (UTC with Z suffix)
      - "2021-03-04T10:12:57+02:00"    (explicit offset)
      - "2021-03-04"                   (date only -> midnight UTC)
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class TrackingEvent:
    """A single tracking event (newest first in the API)."""

    event_id: str | None = None
    status: str | None = None
    occurrence_datetime: datetime | None = None
    location: str | None = None
    courier_code: str | None = None
    status_code: str | None = None
    status_category: str | None = None
    status_milestone: str | None = None

    @classmethod
    def from_api(cls, raw: dict) -> TrackingEvent:
        """Build a TrackingEvent from a raw API event object."""
        return cls(
            event_id=raw.get("eventId"),
            status=raw.get("status"),
            occurrence_datetime=parse_logistics_datetime(raw.get("occurrenceDatetime")),
            location=raw.get("location"),
            courier_code=raw.get("courierCode"),
            status_code=raw.get("statusCode"),
            status_category=raw.get("statusCategory"),
            status_milestone=raw.get("statusMilestone"),
        )


@dataclass
class TrackingData:
    """Parsed tracking results for one parcel."""

    tracker_id: str | None = None
    tracking_number: str | None = None
    # Shipment-level status
    status_code: str | None = None
    status_category: str | None = None
    status_milestone: str | None = None
    # Delivery information
    estimated_delivery_date: datetime | None = None
    delivery_from: datetime | None = None
    delivery_to: datetime | None = None
    service: str | None = None
    signed_by: str | None = None
    # Route
    origin_country: str | None = None
    destination_country: str | None = None
    # Milestone timestamps (milestone -> datetime)
    milestone_timestamps: dict[str, datetime] = field(default_factory=dict)
    events: list[TrackingEvent] = field(default_factory=list)

    @property
    def status(self) -> str | None:
        """Best available status: milestone first, category as fallback."""
        return self.status_milestone or self.status_category

    @property
    def delivered_at(self) -> datetime | None:
        """Datetime of delivery, from milestone timestamps."""
        return self.milestone_timestamps.get("delivered")

    @property
    def last_event(self) -> TrackingEvent | None:
        """Most recent event (API returns events newest first)."""
        return self.events[0] if self.events else None

    @classmethod
    def from_api(cls, raw: dict) -> TrackingData:
        """Build TrackingData from a raw API `tracking` object."""
        tracker = raw.get("tracker") or {}
        shipment = raw.get("shipment") or {}
        delivery = shipment.get("delivery") or {}
        courier_estimate = delivery.get("courierEstimatedDeliveryDate") or {}
        statistics = raw.get("statistics") or {}
        timestamps = statistics.get("timestamps") or {}

        milestone_timestamps: dict[str, datetime] = {}
        milestone_keys = (
            "infoReceivedDatetime",
            "inTransitDatetime",
            "outForDeliveryDatetime",
            "failedAttemptDatetime",
            "availableForPickupDatetime",
            "exceptionDatetime",
            "deliveredDatetime",
        )
        milestone_names = {
            "infoReceivedDatetime": "info_received",
            "inTransitDatetime": "in_transit",
            "outForDeliveryDatetime": "out_for_delivery",
            "failedAttemptDatetime": "failed_attempt",
            "availableForPickupDatetime": "available_for_pickup",
            "exceptionDatetime": "exception",
            "deliveredDatetime": "delivered",
        }
        for key in milestone_keys:
            moment = parse_logistics_datetime(timestamps.get(key))
            if moment is not None:
                milestone_timestamps[milestone_names[key]] = moment

        events = [
            TrackingEvent.from_api(event)
            for event in raw.get("events") or []
            if isinstance(event, dict)
        ]

        return cls(
            tracker_id=tracker.get("trackerId"),
            tracking_number=tracker.get("trackingNumber"),
            status_code=shipment.get("statusCode"),
            status_category=shipment.get("statusCategory"),
            status_milestone=shipment.get("statusMilestone"),
            estimated_delivery_date=parse_logistics_datetime(
                delivery.get("estimatedDeliveryDate")
            ),
            delivery_from=parse_logistics_datetime(courier_estimate.get("from")),
            delivery_to=parse_logistics_datetime(courier_estimate.get("to")),
            service=delivery.get("service"),
            signed_by=delivery.get("signedBy"),
            origin_country=shipment.get("originCountryCode"),
            destination_country=shipment.get("destinationCountryCode"),
            milestone_timestamps=milestone_timestamps,
            events=events,
        )

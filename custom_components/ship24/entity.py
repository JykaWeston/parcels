"""Base entity for Ship24 parcel devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PARCEL_LABEL, PARCEL_TRACKER_ID, PARCEL_TRACKING_NUMBER
from .coordinator import Ship24Coordinator
from .models import TrackingData


class Ship24Entity(CoordinatorEntity[Ship24Coordinator]):
    """Base entity attached to one parcel (one device per parcel)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Ship24Coordinator,
        parcel: dict[str, Any],
        suffix: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.parcel = parcel
        tracker_id = parcel[PARCEL_TRACKER_ID]
        label = parcel.get(PARCEL_LABEL) or parcel[PARCEL_TRACKING_NUMBER]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{tracker_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, tracker_id)},
            name=label,
            model="Parcel",
            manufacturer="Ship24",
        )

    @property
    def tracking_data(self) -> TrackingData | None:
        """Tracking results for this parcel, if any."""
        return self.coordinator.data.get(self.parcel[PARCEL_TRACKER_ID])

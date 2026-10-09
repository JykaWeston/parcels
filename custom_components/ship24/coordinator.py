"""DataUpdateCoordinator fetching all parcel tracking results."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import Ship24ApiClient
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_STATUS_CHANGED,
    OPT_PARCELS,
    PARCEL_LABEL,
    PARCEL_TRACKER_ID,
    PARCEL_TRACKING_NUMBER,
    STATUS_DELIVERED,
    UNSUBSCRIBE_AFTER_DELIVERY_DAYS,
)
from .exceptions import Ship24AuthError, Ship24Error
from .models import TrackingData

_LOGGER = logging.getLogger(__name__)


class Ship24Coordinator(DataUpdateCoordinator[dict[str, TrackingData]]):
    """Poll Ship24 results for every parcel of the config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: Ship24ApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = entry
        self._unsubscribed: set[str] = set()
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(
                    "update_interval", DEFAULT_UPDATE_INTERVAL
                )
            ),
        )

    @property
    def parcels(self) -> list[dict[str, Any]]:
        """Parcels configured in the entry options."""
        return self.entry.options.get(OPT_PARCELS, [])

    async def _async_update_data(self) -> dict[str, TrackingData]:
        """Fetch results for each parcel.

        A failing parcel does not abort the whole update: results are
        collected per parcel and only a total failure raises UpdateFailed.
        """
        results: dict[str, TrackingData] = {}
        previous = self.data or {}
        had_failure = False
        auth_error: Ship24AuthError | None = None

        for parcel in self.parcels:
            tracker_id = parcel[PARCEL_TRACKER_ID]
            try:
                data = await self.client.async_get_results(tracker_id)
            except Ship24AuthError as err:
                # Entry-level problem: stop polling, ask for reauth.
                auth_error = auth_error or err
                continue
            except Ship24Error as err:
                _LOGGER.warning(
                    "Could not fetch results for %s: %s",
                    parcel[PARCEL_TRACKING_NUMBER],
                    err,
                )
                had_failure = True
                continue

            results[tracker_id] = data
            self._fire_status_changed(
                parcel, previous.get(tracker_id), data
            )
            await self._auto_unsubscribe(parcel, data)

        if auth_error is not None:
            raise ConfigEntryAuthFailed from auth_error
        if had_failure and not results and self.parcels:
            raise UpdateFailed("No parcel could be refreshed")
        return results

    @callback
    def _fire_status_changed(
        self,
        parcel: dict[str, Any],
        previous: TrackingData | None,
        current: TrackingData,
    ) -> None:
        """Fire an event when a parcel status changes (skip first refresh)."""
        if previous is None or previous.status == current.status:
            return
        self.hass.bus.async_fire(
            EVENT_STATUS_CHANGED,
            {
                "tracker_id": parcel[PARCEL_TRACKER_ID],
                "tracking_number": parcel[PARCEL_TRACKING_NUMBER],
                "label": parcel.get(PARCEL_LABEL),
                "old_status": previous.status,
                "new_status": current.status,
                "last_event": (
                    current.last_event.status if current.last_event else None
                ),
            },
        )

    async def _auto_unsubscribe(
        self, parcel: dict[str, Any], data: TrackingData
    ) -> None:
        """Unsubscribe delivered parcels after a grace period (hygiene).

        Ship24 auto-disables trackers after delivery; this makes it explicit
        and frees the clientTrackerId slot. Errors are non-fatal.
        """
        tracker_id = parcel[PARCEL_TRACKER_ID]
        if tracker_id in self._unsubscribed:
            return
        delivered_at = data.delivered_at
        if data.status != STATUS_DELIVERED or delivered_at is None:
            return
        if dt_util.utcnow() - delivered_at < timedelta(
            days=UNSUBSCRIBE_AFTER_DELIVERY_DAYS
        ):
            return
        try:
            await self.client.async_unsubscribe(tracker_id)
        except Ship24Error as err:
            _LOGGER.debug("Auto-unsubscribe failed for %s: %s", tracker_id, err)
            return
        self._unsubscribed.add(tracker_id)
        _LOGGER.info(
            "Unsubscribed delivered parcel %s (%s)",
            parcel[PARCEL_TRACKING_NUMBER],
            parcel.get(PARCEL_LABEL),
        )

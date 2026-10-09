"""Async client for the Ship24 Tracking API (pure aiohttp, no Home Assistant imports).

API reference: https://docs.ship24.com — base URL https://api.ship24.com,
authentication via ``Authorization: Bearer <api key>``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .exceptions import (
    Ship24ApiError,
    Ship24AuthError,
    Ship24BadJsonError,
    Ship24ConnectionError,
    Ship24NotFoundError,
    Ship24RateLimitError,
)
from .models import TrackingData

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.ship24.com"
API_PATH = "/public/v1"

# Conservative retry for transient failures (429/5xx), with backoff.
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2.0  # seconds


class Ship24ApiClient:
    """Thin async wrapper around the Ship24 Tracking API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = BASE_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an API request and return the parsed ``data`` payload.

        Raises a typed Ship24Error subclass on failure.
        """
        url = f"{self._base_url}{API_PATH}{path}"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    json=json_body,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as response:
                    if response.status in (401, 403):
                        raise Ship24AuthError(
                            response.status,
                            message="Invalid or unauthorized Ship24 API key",
                        )
                    if response.status == 404:
                        raise Ship24NotFoundError(response.status, message=f"Not found: {path}")
                    if response.status == 429 and attempt < _MAX_RETRIES:
                        await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                        continue
                    if response.status >= 500 and attempt < _MAX_RETRIES:
                        await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                        continue
                    if response.status == 429:
                        raise Ship24RateLimitError(
                            429, message="Ship24 rate limit exceeded"
                        )
                    body = await response.json(content_type=None)
                    if response.status >= 400:
                        raise Ship24ApiError(
                            response.status,
                            code=_first_error_code(body),
                            message=_first_error_message(body),
                        )
                    if body is None:
                        raise Ship24BadJsonError(f"Empty response from {path}")
                    return body
            except (TimeoutError, aiohttp.ClientError) as err:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                    continue
                raise Ship24ConnectionError(f"Cannot reach Ship24 API: {err}") from err
        raise Ship24ConnectionError("Cannot reach Ship24 API")

    async def async_validate_key(self) -> list[dict[str, Any]]:
        """Validate the API key by listing trackers (page 1).

        Returns the raw trackers list; raises Ship24AuthError on bad key.
        """
        body = await self._request("GET", "/trackers", params={"page": 1})
        data = body.get("data") or {}
        return data.get("trackers") or []

    async def async_track(
        self, tracking_number: str, label: str | None = None
    ) -> TrackingData:
        """Create (if needed) and fetch a tracker for a tracking number.

        Uses ``POST /trackers/track`` which is idempotent: calling it twice
        with the same payload will not create a duplicate tracker. The first
        call for a number may take up to a minute while couriers are queried.
        """
        payload: dict[str, Any] = {"trackingNumber": tracking_number}
        if label:
            payload["shipmentReference"] = label
        body = await self._request("POST", "/trackers/track", json_body=payload)
        trackings = _extract_trackings(body)
        if not trackings:
            raise Ship24ApiError(
                200, message=f"No tracking data returned for {tracking_number}"
            )
        return TrackingData.from_api(trackings[0])

    async def async_get_results(self, tracker_id: str) -> TrackingData:
        """Fetch tracking results for an existing tracker id."""
        body = await self._request("GET", f"/trackers/{tracker_id}/results")
        trackings = _extract_trackings(body)
        if not trackings:
            raise Ship24ApiError(
                200, message=f"No tracking data for tracker {tracker_id}"
            )
        return TrackingData.from_api(trackings[0])

    async def async_unsubscribe(self, tracker_id: str) -> None:
        """Stop tracking updates for a tracker (frees the client tracker slot)."""
        await self._request(
            "PATCH", f"/trackers/{tracker_id}", json_body={"isSubscribed": False}
        )


def _extract_trackings(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    trackings = data.get("trackings")
    return [t for t in trackings if isinstance(t, dict)] if trackings else []


def _first_error_code(body: Any) -> str | None:
    try:
        return body["errors"][0]["code"]
    except (KeyError, IndexError, TypeError):
        return None


def _first_error_message(body: Any) -> str | None:
    try:
        return body["errors"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None

"""Tests for the Ship24 API client against a local aiohttp test server.

No mocking library: the client's base_url is pointed at a real HTTP server,
which keeps these tests honest (headers, paths, payloads, status handling).
"""

import sys
from pathlib import Path

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from ship24.api import API_PATH, Ship24ApiClient  # noqa: E402
from ship24.exceptions import (  # noqa: E402
    Ship24ApiError,
    Ship24AuthError,
    Ship24NotFoundError,
    Ship24RateLimitError,
)

API_KEY = "apik_test"

# These tests run a real local HTTP server (aiohttp TestServer), so they
# need sockets — the HA test plugin blocks them by default.
pytestmark = pytest.mark.enable_socket

TRACKERS_LIST = {"data": {"trackers": [{"trackerId": "t1", "trackingNumber": "9400"}]}}

TRACK_RESPONSE = {
    "data": {
        "trackings": [
            {
                "tracker": {"trackerId": "t1", "trackingNumber": "9400"},
                "shipment": {"statusMilestone": "in_transit"},
                "events": [],
            }
        ]
    }
}

RESULTS_RESPONSE = {
    "data": {
        "trackings": [
            {
                "tracker": {"trackerId": "t1", "trackingNumber": "9400"},
                "shipment": {"statusMilestone": "delivered"},
                "events": [],
            }
        ]
    }
}


class FakeShip24Server:
    """Minimal Ship24 API double recording requests and replaying responses."""

    def __init__(self) -> None:
        self.queue: dict[tuple[str, str], list[tuple[int, dict | None]]] = {}
        self.calls: list[dict] = []

    def add(self, method: str, path: str, payload: dict | None = None, status: int = 200) -> None:
        """Queue a response for a (method, path) pair (repeatable)."""
        self.queue.setdefault((method, path), []).append((status, payload))

    async def _handle(self, request: web.Request) -> web.Response:
        body = None
        if request.can_read_body:
            body = await request.json()
        self.calls.append(
            {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
                "json": body,
            }
        )
        queued = self.queue.get((request.method, request.path))
        if queued:
            status, payload = queued.pop(0) if len(queued) > 1 else queued[0]
            return web.json_response(payload, status=status)
        return web.json_response(
            {"errors": [{"code": "not_mocked", "message": f"Unexpected {request.method} {request.path}"}]},
            status=500,
        )

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.server = TestServer(app)
        await self.server.start_server()

    @property
    def base_url(self) -> str:
        return str(self.server.make_url("")).rstrip("/")

    async def stop(self) -> None:
        await self.server.close()


@pytest.fixture
async def server():
    fake = FakeShip24Server()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def client(server):
    async with ClientSession() as session:
        yield Ship24ApiClient(session, API_KEY, base_url=server.base_url)


class TestValidateKey:
    async def test_ok(self, server, client):
        server.add("GET", f"{API_PATH}/trackers", TRACKERS_LIST)
        trackers = await client.async_validate_key()
        assert trackers == [{"trackerId": "t1", "trackingNumber": "9400"}]
        # Auth header must carry the API key.
        call = server.calls[-1]
        assert call["headers"]["Authorization"] == f"Bearer {API_KEY}"

    async def test_invalid_key(self, server, client):
        server.add(
            "GET",
            f"{API_PATH}/trackers",
            {"errors": [{"code": "unauthorized", "message": "Bad key"}]},
            status=401,
        )
        with pytest.raises(Ship24AuthError):
            await client.async_validate_key()


class TestTrack:
    async def test_create(self, server, client):
        server.add("POST", f"{API_PATH}/trackers/track", TRACK_RESPONSE)
        data = await client.async_track("9400", label="Mon colis")
        assert data.tracker_id == "t1"
        assert data.status == "in_transit"
        call = server.calls[-1]
        assert call["json"] == {
            "trackingNumber": "9400",
            "shipmentReference": "Mon colis",
        }

    async def test_no_trackings_returned(self, server, client):
        server.add("POST", f"{API_PATH}/trackers/track", {"data": {"trackings": []}})
        with pytest.raises(Ship24ApiError):
            await client.async_track("9400")


class TestResults:
    async def test_get_results(self, server, client):
        server.add("GET", f"{API_PATH}/trackers/t1/results", RESULTS_RESPONSE)
        data = await client.async_get_results("t1")
        assert data.status == "delivered"

    async def test_not_found(self, server, client):
        server.add(
            "GET",
            f"{API_PATH}/trackers/unknown/results",
            {"errors": [{"code": "not_found", "message": "Tracker not found"}]},
            status=404,
        )
        with pytest.raises(Ship24NotFoundError):
            await client.async_get_results("unknown")


class TestUnsubscribe:
    async def test_unsubscribe(self, server, client):
        server.add(
            "PATCH",
            f"{API_PATH}/trackers/t1",
            {"data": {"tracker": {"trackerId": "t1", "isSubscribed": False}}},
        )
        await client.async_unsubscribe("t1")  # should not raise
        call = server.calls[-1]
        assert call["json"] == {"isSubscribed": False}


class TestErrors:
    async def test_rate_limit_raises_after_retries(self, server, client, monkeypatch):
        monkeypatch.setattr("ship24.api._RETRY_BASE_DELAY", 0)
        for _ in range(3):
            server.add("GET", f"{API_PATH}/trackers/t1/results", {"errors": []}, status=429)
        with pytest.raises(Ship24RateLimitError):
            await client.async_get_results("t1")

    async def test_error_payload_parsed(self, server, client):
        server.add(
            "GET",
            f"{API_PATH}/trackers",
            {
                "errors": [
                    {"code": "invalid_parameter", "message": "trackingNumber invalid"}
                ]
            },
            status=400,
        )
        with pytest.raises(Ship24ApiError) as excinfo:
            await client.async_validate_key()
        assert excinfo.value.code == "invalid_parameter"
        assert "invalid" in excinfo.value.message

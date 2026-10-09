"""Tests for Ship24 model parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from ship24.models import TrackingData, parse_logistics_datetime  # noqa: E402

SAMPLE_TRACKING = {
    "tracker": {
        "trackerId": "26148317-7502-d3ac-44a9-546d240ac0dd",
        "trackingNumber": "9400115901047177598206",
        "isSubscribed": True,
    },
    "shipment": {
        "shipmentId": "f4f888d7-d140-423f-9a48-e0689d27e098",
        "statusCode": "delivery_delivered",
        "statusCategory": "delivery",
        "statusMilestone": "delivered",
        "originCountryCode": "CN",
        "destinationCountryCode": "FR",
        "delivery": {
            "estimatedDeliveryDate": "2021-03-04T18:00:00",
            "courierEstimatedDeliveryDate": {"from": "2021-03-04", "to": "2021-03-05"},
            "service": "Parcel Post",
            "signedBy": "John Doe",
        },
    },
    "events": [
        {
            "eventId": "e1",
            "status": "Delivered to the addressee",
            "occurrenceDatetime": "2021-03-05T17:12:57",
            "location": "SAN RAFAEL, CA 94901",
            "courierCode": "us-post",
            "statusCode": "delivery_delivered",
            "statusCategory": "delivery",
            "statusMilestone": "delivered",
        },
        {
            "eventId": "e0",
            "status": "Out for delivery",
            "occurrenceDatetime": "2021-03-04T10:12:57.000Z",
            "location": "FR",
            "statusMilestone": "out_for_delivery",
        },
    ],
    "statistics": {
        "timestamps": {
            "infoReceivedDatetime": "2021-03-02T15:38:57",
            "inTransitDatetime": "2021-03-02T19:24:57",
            "outForDeliveryDatetime": "2021-03-04T10:12:57",
            "deliveredDatetime": "2021-03-05T17:12:57",
        }
    },
}


class TestParseLogisticsDatetime:
    def test_naive_becomes_utc(self):
        parsed = parse_logistics_datetime("2021-03-04T17:12:57")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 0

    def test_z_suffix(self):
        parsed = parse_logistics_datetime("2021-03-04T10:12:57.000Z")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 0

    def test_explicit_offset(self):
        parsed = parse_logistics_datetime("2021-03-04T10:12:57+02:00")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 7200

    def test_date_only(self):
        parsed = parse_logistics_datetime("2021-03-04")
        assert parsed is not None
        assert (parsed.hour, parsed.minute, parsed.second) == (0, 0, 0)

    def test_none_and_garbage(self):
        assert parse_logistics_datetime(None) is None
        assert parse_logistics_datetime("") is None
        assert parse_logistics_datetime("not a date") is None


class TestTrackingData:
    def test_parse_full_payload(self):
        data = TrackingData.from_api(SAMPLE_TRACKING)
        assert data.tracker_id == "26148317-7502-d3ac-44a9-546d240ac0dd"
        assert data.tracking_number == "9400115901047177598206"
        assert data.status == "delivered"
        assert data.origin_country == "CN"
        assert data.destination_country == "FR"
        assert data.service == "Parcel Post"
        assert data.signed_by == "John Doe"
        assert data.estimated_delivery_date is not None
        assert data.delivery_from is not None
        assert data.delivery_to is not None
        assert len(data.events) == 2
        assert data.last_event.event_id == "e1"
        assert data.last_event.status == "Delivered to the addressee"
        assert data.delivered_at is not None

    def test_milestone_timestamps(self):
        data = TrackingData.from_api(SAMPLE_TRACKING)
        assert set(data.milestone_timestamps) == {
            "info_received",
            "in_transit",
            "out_for_delivery",
            "delivered",
        }

    def test_status_falls_back_to_category(self):
        raw = {
            "tracker": {"trackerId": "x", "trackingNumber": "1"},
            "shipment": {"statusCategory": "pending"},
        }
        data = TrackingData.from_api(raw)
        assert data.status == "pending"
        assert data.events == []
        assert data.last_event is None
        assert data.delivered_at is None

    def test_empty_payload(self):
        data = TrackingData.from_api({})
        assert data.tracker_id is None
        assert data.status is None
        assert data.estimated_delivery_date is None

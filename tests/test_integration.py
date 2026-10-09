"""Integration tests for the ship24 custom component (config flow, setup, sensors)."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ship24.const import (
    CONF_API_KEY,
    DOMAIN,
    OPT_PARCELS,
    PARCEL_LABEL,
    PARCEL_TRACKER_ID,
    PARCEL_TRACKING_NUMBER,
)
from custom_components.ship24.models import TrackingData

pytest_plugins = ("pytest_homeassistant_custom_component",)

PARCEL = {
    PARCEL_TRACKING_NUMBER: "9400115901047177598206",
    PARCEL_LABEL: "Colis 1",
    PARCEL_TRACKER_ID: "t1",
}

RESULTS_PAYLOAD = {
    "data": {
        "trackings": [
            {
                "tracker": {
                    "trackerId": "t1",
                    "trackingNumber": "9400115901047177598206",
                },
                "shipment": {
                    "statusMilestone": "in_transit",
                    "statusCode": "intransit_in_transit",
                    "statusCategory": "in_transit",
                },
                "delivery": {},
                "events": [
                    {
                        "eventId": "e1",
                        "status": "Arrived at sorting center",
                        "occurrenceDatetime": "2026-10-01T10:00:00",
                        "location": "Lille, FR",
                        "courierCode": "chronopost",
                    }
                ],
            }
        ]
    }
}

TRACK_PAYLOAD = {
    "data": {
        "trackings": [
            {
                "tracker": {"trackerId": "t2", "trackingNumber": "NEW1"},
                "shipment": {"statusMilestone": "info_received"},
                "events": [],
            }
        ]
    }
}


async def test_config_flow_creates_entry(hass: HomeAssistant, enable_custom_integrations):
    """A valid API key creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.ship24.api.Ship24ApiClient.async_validate_key",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: "apik_valid"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ship24"
    assert result["data"][CONF_API_KEY] == "apik_valid"


async def test_config_flow_invalid_key(hass: HomeAssistant, enable_custom_integrations):
    """An invalid API key shows invalid_auth."""
    from custom_components.ship24.exceptions import Ship24AuthError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.ship24.api.Ship24ApiClient.async_validate_key",
        side_effect=Ship24AuthError(401, message="Bad key"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: "apik_bad"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_setup_creates_sensors(hass: HomeAssistant, enable_custom_integrations):
    """Setup with one parcel creates the three sensors."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "apik_valid"},
        options={OPT_PARCELS: [PARCEL]},
        version=1,
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.ship24.api.Ship24ApiClient.async_validate_key",
            return_value=[],
        ),
        patch(
            "custom_components.ship24.api.Ship24ApiClient.async_get_results",
            return_value=TrackingData.from_api(RESULTS_PAYLOAD["data"]["trackings"][0]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    status = hass.states.get("sensor.colis_1_status")
    assert status is not None
    assert status.state == "in_transit"
    assert status.attributes["tracking_number"] == "9400115901047177598206"
    assert status.attributes["courier"] == "chronopost"

    last_event = hass.states.get("sensor.colis_1_last_event")
    assert last_event is not None
    assert last_event.state == "Arrived at sorting center"
    assert last_event.attributes["location"] == "Lille, FR"

    delivery = hass.states.get("sensor.colis_1_estimated_delivery")
    assert delivery is not None


async def test_add_parcel_service(hass: HomeAssistant, enable_custom_integrations):
    """The add_parcel service appends the parcel and reloads the sensors."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "apik_valid"},
        options={OPT_PARCELS: []},
        version=1,
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.ship24.api.Ship24ApiClient.async_validate_key",
            return_value=[],
        ),
        patch(
            "custom_components.ship24.api.Ship24ApiClient.async_get_results",
            return_value=TrackingData.from_api(TRACK_PAYLOAD["data"]["trackings"][0]),
        ),
        patch(
            "custom_components.ship24.api.Ship24ApiClient.async_track",
            return_value=TrackingData.from_api(TRACK_PAYLOAD["data"]["trackings"][0]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            "add_parcel",
            {"tracking_number": "NEW1", "label": "Nouveau colis"},
            blocking=True,
        )
        # The options update reloads the entry; run it inside the patch scope.
        await hass.async_block_till_done()

    parcels = entry.options[OPT_PARCELS]
    assert len(parcels) == 1
    assert parcels[0][PARCEL_TRACKER_ID] == "t2"
    assert parcels[0][PARCEL_LABEL] == "Nouveau colis"
    assert hass.states.get("sensor.nouveau_colis_status") is not None

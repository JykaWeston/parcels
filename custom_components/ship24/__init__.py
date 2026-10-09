"""The Ship24 integration: track parcels via the Ship24 API."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Ship24ApiClient
from .const import (
    CONF_API_KEY,
    DOMAIN,
    OPT_PARCELS,
    PARCEL_LABEL,
    PARCEL_TRACKER_ID,
    PARCEL_TRACKING_NUMBER,
)
from .coordinator import Ship24Coordinator
from .exceptions import Ship24AuthError, Ship24Error

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type Ship24ConfigEntry = ConfigEntry[Ship24Coordinator]

ADD_PARCEL_SCHEMA = vol.Schema(
    {
        vol.Required("tracking_number"): cv.string,
        vol.Optional("label"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: Ship24ConfigEntry) -> bool:
    """Set up Ship24 from a config entry."""
    client = Ship24ApiClient(
        async_get_clientsession(hass), entry.data[CONF_API_KEY]
    )
    try:
        await client.async_validate_key()
    except Ship24AuthError as err:
        raise ConfigEntryAuthFailed from err
    except Ship24Error as err:
        raise ConfigEntryNotReady(f"Cannot reach Ship24: {err}") from err

    coordinator = Ship24Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Ship24ConfigEntry) -> bool:
    """Unload a Ship24 config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, "refresh")
        hass.services.async_remove(DOMAIN, "add_parcel")
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, "refresh"):
        return

    async def handle_refresh(call: ServiceCall) -> None:
        """Force a refresh of all Ship24 coordinators."""
        for entry in hass.config_entries.async_entries(DOMAIN):
            if isinstance(coordinator := entry.runtime_data, Ship24Coordinator):
                await coordinator.async_refresh()

    async def handle_add_parcel(call: ServiceCall) -> None:
        """Add a parcel from a service call."""
        tracking_number: str = call.data["tracking_number"].strip()
        label: str = (call.data.get("label") or tracking_number).strip()

        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("No Ship24 account configured")
        entry = entries[0]
        coordinator = entry.runtime_data
        if not isinstance(coordinator, Ship24Coordinator):
            raise HomeAssistantError("Ship24 integration is not ready yet")

        parcels: list[dict] = entry.options.get(OPT_PARCELS, [])
        if any(p[PARCEL_TRACKING_NUMBER] == tracking_number for p in parcels):
            raise HomeAssistantError(
                f"Parcel {tracking_number} is already tracked"
            )

        try:
            # Idempotent on Ship24 side: no duplicate tracker if it exists.
            data = await coordinator.client.async_track(tracking_number, label=label)
        except Ship24Error as err:
            raise HomeAssistantError(f"Ship24 refused the parcel: {err}") from err

        new_options = {
            **entry.options,
            OPT_PARCELS: [
                *parcels,
                {
                    PARCEL_TRACKING_NUMBER: tracking_number,
                    PARCEL_LABEL: label,
                    PARCEL_TRACKER_ID: data.tracker_id,
                },
            ],
        }
        hass.config_entries.async_update_entry(entry, options=new_options)

    hass.services.async_register(DOMAIN, "refresh", handle_refresh)
    hass.services.async_register(DOMAIN, "add_parcel", handle_add_parcel, schema=ADD_PARCEL_SCHEMA)

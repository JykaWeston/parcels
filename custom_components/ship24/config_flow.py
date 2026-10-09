"""Config flow: API key setup + parcel management (options flow)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Ship24ApiClient
from .const import (
    CONF_API_KEY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    OPT_PARCELS,
    OPT_UPDATE_INTERVAL,
    PARCEL_LABEL,
    PARCEL_TRACKER_ID,
    PARCEL_TRACKING_NUMBER,
)
from .exceptions import Ship24AuthError, Ship24Error

ADD_TRACKING_NUMBER = "add_tracking_number"
ADD_LABEL = "add_label"
REMOVE_PARCELS = "remove_parcels"

API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


class Ship24ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Ship24 config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API key and validate it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = Ship24ApiClient(
                async_get_clientsession(self.hass), user_input[CONF_API_KEY]
            )
            try:
                await client.async_validate_key()
            except Ship24AuthError:
                errors["base"] = "invalid_auth"
            except Ship24Error:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Ship24", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=API_KEY_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> Ship24OptionsFlowHandler:
        """Create the options flow."""
        return Ship24OptionsFlowHandler()


class Ship24OptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Manage the parcel list: add parcels, remove parcels, polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a single form to add/remove parcels and set the interval."""
        errors: dict[str, str] = {}
        parcels: list[dict[str, Any]] = self.options.get(OPT_PARCELS, [])

        if user_input is not None:
            keep, removed = self._split_removals(parcels, user_input)
            await self._unsubscribe_parcels(removed)

            add_number = (user_input.get(ADD_TRACKING_NUMBER) or "").strip()
            if add_number:
                add_label = (user_input.get(ADD_LABEL) or "").strip() or add_number
                added = await self._add_parcel(add_number, add_label, errors)
                if added is not None:
                    keep.append(added)

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        **self.options,
                        OPT_PARCELS: keep,
                        OPT_UPDATE_INTERVAL: user_input[OPT_UPDATE_INTERVAL],
                    },
                )

        schema = self._build_schema(parcels)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    def _split_removals(
        self, parcels: list[dict[str, Any]], user_input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split parcels into kept/removed based on the multi-select."""
        to_remove = set(user_input.get(REMOVE_PARCELS) or [])
        keep = [p for p in parcels if p[PARCEL_TRACKING_NUMBER] not in to_remove]
        removed = [p for p in parcels if p[PARCEL_TRACKING_NUMBER] in to_remove]
        return keep, removed

    async def _unsubscribe_parcels(self, removed: list[dict[str, Any]]) -> None:
        """Best-effort unsubscribe of removed parcels."""
        client = Ship24ApiClient(
            async_get_clientsession(self.hass),
            self.config_entry.data[CONF_API_KEY],
        )
        for parcel in removed:
            try:
                await client.async_unsubscribe(parcel[PARCEL_TRACKER_ID])
            except Ship24Error:
                # Tracker may already be gone; removal in HA proceeds anyway.
                pass

    async def _add_parcel(
        self, tracking_number: str, label: str, errors: dict[str, str]
    ) -> dict[str, Any] | None:
        """Create the tracker on Ship24 and return the new parcel dict."""
        parcels: list[dict[str, Any]] = self.options.get(OPT_PARCELS, [])
        if any(p[PARCEL_TRACKING_NUMBER] == tracking_number for p in parcels):
            errors["base"] = "duplicate_parcel"
            return None

        client = Ship24ApiClient(
            async_get_clientsession(self.hass),
            self.config_entry.data[CONF_API_KEY],
        )
        try:
            # First call may take up to a minute while couriers are queried.
            data = await client.async_track(tracking_number, label=label)
        except Ship24AuthError:
            errors["base"] = "invalid_auth"
            return None
        except Ship24Error:
            errors["base"] = "cannot_connect"
            return None

        return {
            PARCEL_TRACKING_NUMBER: tracking_number,
            PARCEL_LABEL: label,
            PARCEL_TRACKER_ID: data.tracker_id,
        }

    def _build_schema(self, parcels: list[dict[str, Any]]) -> vol.Schema:
        """Build the options form schema."""
        schema: dict[Any, Any] = {
            vol.Optional(ADD_TRACKING_NUMBER): str,
            vol.Optional(ADD_LABEL): str,
        }
        if parcels:
            choices = {
                p[PARCEL_TRACKING_NUMBER]: f"{p.get(PARCEL_LABEL) or p[PARCEL_TRACKING_NUMBER]} ({p[PARCEL_TRACKING_NUMBER]})"
                for p in parcels
            }
            schema[vol.Optional(REMOVE_PARCELS)] = cv.multi_select(choices)
        schema[vol.Required(OPT_UPDATE_INTERVAL, default=self.options.get(OPT_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))] = vol.All(
            vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)
        )
        return vol.Schema(schema)

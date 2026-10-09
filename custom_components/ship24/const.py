"""Constants for the Ship24 integration."""

DOMAIN = "ship24"

CONF_API_KEY = "api_key"

# Options
OPT_PARCELS = "parcels"
OPT_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL = 30  # minutes
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 240

# Per-parcel option keys
PARCEL_TRACKING_NUMBER = "tracking_number"
PARCEL_LABEL = "label"
PARCEL_TRACKER_ID = "tracker_id"

# Event fired on the HA bus when a parcel status changes.
EVENT_STATUS_CHANGED = f"{DOMAIN}_status_changed"

# Auto-unsubscribe from Ship24 this many days after delivery (tracker hygiene).
UNSUBSCRIBE_AFTER_DELIVERY_DAYS = 7

# Known Ship24 status milestones.
STATUS_INFO_RECEIVED = "info_received"
STATUS_IN_TRANSIT = "in_transit"
STATUS_OUT_FOR_DELIVERY = "out_for_delivery"
STATUS_FAILED_ATTEMPT = "failed_attempt"
STATUS_AVAILABLE_FOR_PICKUP = "available_for_pickup"
STATUS_EXCEPTION = "exception"
STATUS_DELIVERED = "delivered"

STATUS_ICONS = {
    STATUS_INFO_RECEIVED: "mdi:package-variant-closed",
    STATUS_IN_TRANSIT: "mdi:truck-delivery-outline",
    STATUS_OUT_FOR_DELIVERY: "mdi:truck-delivery",
    STATUS_FAILED_ATTEMPT: "mdi:package-variant-remove",
    STATUS_AVAILABLE_FOR_PICKUP: "mdi:handshake",
    STATUS_EXCEPTION: "mdi:alert-circle",
    STATUS_DELIVERED: "mdi:package-check",
}
DEFAULT_ICON = "mdi:package-variant-closed"

# Public tracking page for a tracking number.
PUBLIC_TRACKING_URL = "https://www.ship24.com/tracking?q={tracking_number}"

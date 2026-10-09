"""Exceptions for the Ship24 API client."""


class Ship24Error(Exception):
    """Base exception for Ship24 errors."""


class Ship24ApiError(Ship24Error):
    """The Ship24 API returned an error response."""

    def __init__(self, status: int, code: str | None = None, message: str | None = None) -> None:
        """Initialize the error."""
        super().__init__(message or f"Ship24 API error (HTTP {status})")
        self.status = status
        self.code = code
        self.message = message


class Ship24AuthError(Ship24ApiError):
    """Authentication failed (invalid or expired API key)."""


class Ship24RateLimitError(Ship24ApiError):
    """Rate limit exceeded (HTTP 429)."""


class Ship24NotFoundError(Ship24ApiError):
    """Resource not found (HTTP 404)."""


class Ship24ConnectionError(Ship24Error):
    """Could not connect to the Ship24 API."""


class Ship24BadJsonError(Ship24Error):
    """The Ship24 API returned malformed JSON."""

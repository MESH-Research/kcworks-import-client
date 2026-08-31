"""Exceptions for the KCWorks import client library."""

from __future__ import annotations


class KCWorksImportError(Exception):
    """Base error for the import client library."""


class ManifestError(KCWorksImportError):
    """Manifest could not be loaded or failed validation."""


class CommunityError(KCWorksImportError):
    """Communities API request failed or returned an unexpected status."""


class ImportRequestError(KCWorksImportError):
    """Transport-level failure talking to the import API."""


class ImportAPIError(KCWorksImportError):
    """Import API returned a non-success HTTP status with a body.

    Attributes:
        status_code: HTTP status code from the response.
        body: Parsed JSON dict, raw text, or ``None``.
        message: Human-readable summary when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: dict | str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Error summary.
            status_code: HTTP status code.
            body: Response body (JSON dict or text).
        """
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.message = message

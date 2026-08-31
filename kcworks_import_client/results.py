"""Result types for the KCWorks import client library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportResult:
    """Outcome of a single-collection import API call.

    Attributes:
        status_code: HTTP status code from the import endpoint.
        data: Successfully imported record descriptors from the response.
        errors: Per-record error objects from the response.
        message: Top-level message from the response (if any).
        body: Full parsed JSON body, or raw text when the response was not JSON.
        ok: ``True`` when the status is 201 (created) or 207 (multi-status).
    """

    status_code: int
    data: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
    body: dict[str, Any] | str | None = None

    @property
    def ok(self) -> bool:
        """Whether the HTTP status indicates success or partial success."""
        return self.status_code in (201, 207)

    @property
    def exit_code(self) -> int:
        """CLI-style exit code: ``0`` when :attr:`ok`, else ``1``."""
        return 0 if self.ok else 1


@dataclass
class MultiCollectionImportResult:
    """Outcome of a multi-collection manifest run.

    Attributes:
        communities: Map of collection slug → community JSON.
        imports: Map of collection slug → :class:`ImportResult` for batches run.
        skipped: Slugs skipped because the entry had no metadata/files.
        ok: ``True`` when every import batch succeeded (or none were run).
    """

    communities: dict[str, dict[str, Any]] = field(default_factory=dict)
    imports: dict[str, ImportResult] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether all executed import batches reported success."""
        return all(result.ok for result in self.imports.values())

    @property
    def exit_code(self) -> int:
        """CLI-style exit code: ``0`` when :attr:`ok`, else ``1``."""
        return 0 if self.ok else 1

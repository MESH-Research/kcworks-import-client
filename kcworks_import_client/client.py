"""HTTP client for the KCWorks single-collection import API."""

from __future__ import annotations

import json
import mimetypes
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

import requests

from .exceptions import ImportAPIError, ImportRequestError
from .results import ImportResult

ProgressCallback = Callable[[str], None]

MetadataInput = str | Path | list[dict[str, Any]] | dict[str, Any]
FileInput = str | Path | tuple[str, BinaryIO] | tuple[str, BinaryIO, str]


def guess_mime_type(file_path: str | Path) -> str:
    """Guess MIME type from a file path, defaulting to octet-stream.

    Args:
        file_path: Path used only for extension / name guessing.

    Returns:
        MIME type string.
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def resolve_import_base_url(*, testing: bool = False) -> tuple[str, bool]:
    """Resolve import API base URL and SSL verification flag.

    Honors ``KCWORKS_IMPORT_API_URL`` when set (SSL verify disabled).

    Args:
        testing: When True and no env override, use ``https://localhost``.

    Returns:
        ``(base_url_without_trailing_slash, verify_ssl)``.
    """
    api_url_env = os.getenv("KCWORKS_IMPORT_API_URL")
    if api_url_env:
        return api_url_env.rstrip("/"), False
    if testing:
        return "https://localhost/api/import", False
    return "https://works.hcommons.org/api/import", True


def serialize_metadata(metadata: MetadataInput) -> str:
    """Serialize metadata input to the JSON string expected by the API.

    Args:
        metadata: Path to a JSON file, a JSON string, a list of record dicts,
            or a single record dict (wrapped into a one-element array).

    Returns:
        JSON text for the multipart ``metadata`` form field.

    Raises:
        TypeError: If ``metadata`` is an unsupported type.
    """
    if isinstance(metadata, Path):
        return metadata.read_text(encoding="utf-8")
    if isinstance(metadata, str):
        # Path-like string that exists on disk → read file; else treat as JSON text.
        if os.path.isfile(metadata):
            with open(metadata, encoding="utf-8") as handle:
                return handle.read()
        return metadata
    if isinstance(metadata, dict):
        return json.dumps([metadata])
    if isinstance(metadata, list):
        return json.dumps(metadata)
    raise TypeError(
        "metadata must be a path, JSON string, list of dicts, or a single dict"
    )


def resolve_output_file_path(output_dir: str, collection_id: str) -> str:
    """Build a timestamped import-report file path under ``output_dir``.

    This helper does not prompt or read environment variables; callers
    (typically CLI wrappers) must supply the directory.

    Args:
        output_dir: Existing directory for the report, or an existing file
            path whose parent directory will be used.
        collection_id: Collection id/slug embedded in the filename.

    Returns:
        Absolute path to a new ``kcworks_import_{id}_{timestamp}.json`` file.

    Raises:
        ValueError: If ``output_dir`` is empty or does not resolve to an
            existing directory.
    """
    if not output_dir:
        raise ValueError("output_dir is required")

    now_string = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    cid = collection_id
    if len(cid) > 20:
        cid = cid[:20] + "..." + cid[-10:]
    file_name = f"kcworks_import_{cid}_{now_string}.json"

    if os.path.isfile(output_dir):
        resolved_dir = os.path.dirname(os.path.abspath(output_dir))
    elif os.path.isdir(output_dir):
        resolved_dir = os.path.abspath(output_dir)
    else:
        raise ValueError(f"Report output directory does not exist: {output_dir}")

    return os.path.join(resolved_dir, file_name)


class ImportClient:
    """Client for ``POST /api/import/<collection>``.

    Example::

        from kcworks_import_client import ImportClient

        client = ImportClient(api_key="...")
        result = client.import_works(
            "my-collection",
            metadata=[{"metadata": {"title": "..."}}],
            files=["paper.pdf"],
        )
        if result.ok:
            print(result.data)
    """

    def __init__(
        self,
        api_key: str,
        *,
        testing: bool = False,
        base_url: str | None = None,
        verify_ssl: bool | None = None,
        session: requests.Session | None = None,
    ) -> None:
        """Create a client.

        Args:
            api_key: Bearer token for the import API.
            testing: Use the localhost instance when ``base_url`` is omitted
                and ``KCWORKS_IMPORT_API_URL`` is unset.
            base_url: Override import API base (no trailing slash, should end
                with ``/import`` or be a full override). When omitted, resolved
                via :func:`resolve_import_base_url`.
            verify_ssl: Override TLS verification. Defaults from URL resolution
                when ``None``.
            session: Optional ``requests.Session`` for connection reuse.

        Raises:
            ValueError: If ``api_key`` is empty.
        """
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.testing = testing
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
            self.verify_ssl = True if verify_ssl is None else verify_ssl
        else:
            resolved_url, resolved_verify = resolve_import_base_url(testing=testing)
            self.base_url = resolved_url
            self.verify_ssl = resolved_verify if verify_ssl is None else verify_ssl
        self.session = session or requests.Session()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def import_url(self, collection_id: str) -> str:
        """Build the full import URL for a collection.

        Args:
            collection_id: Collection ID or slug.

        Returns:
            Absolute URL for the multipart import POST.
        """
        return f"{self.base_url}/{collection_id}"

    def import_works(
        self,
        collection_id: str,
        metadata: MetadataInput,
        files: Sequence[FileInput],
        *,
        notify_owners: bool = False,
        id_scheme: str = "import-recid",
        alternate_id_scheme: str = "",
        no_updates: bool = False,
        all_or_none: bool = False,
        progress: ProgressCallback | None = None,
    ) -> ImportResult:
        """Import works into a collection.

        Args:
            collection_id: Target collection ID or slug.
            metadata: Metadata JSON file path, JSON string, list of record
                dicts, or a single record dict.
            files: File paths and/or ``(filename, binary_file[, mime_type])``
                tuples. At least one file is typically required by the API.
            notify_owners: Email users listed as record owners.
            id_scheme: Primary import dedupe scheme.
            alternate_id_scheme: Optional secondary dedupe scheme.
            no_updates: If True, block metadata updates on existing matches.
                Default is False.
            all_or_none: If True, stop the whole update job and roll back any
                created records if one of the record imports fails. Defaults
                to False.
            progress: Optional callback invoked with status strings (e.g.
                ``"start"``, ``"done"``). The CLI uses this for a spinner.

        Returns:
            :class:`~kcworks_import_client.results.ImportResult` for any HTTP
            response that was received (including 4xx/5xx). Callers that want
            exceptions on non-``ok`` statuses can check :attr:`ImportResult.ok`
            or call :meth:`import_works_or_raise`.

        Raises:
            ImportRequestError: Network / transport failure before a response.
            ValueError: Empty ``collection_id``.
        """
        if not collection_id:
            raise ValueError("collection_id is required")

        metadata_json = serialize_metadata(metadata)
        url = self.import_url(collection_id)

        opened_handles: list[BinaryIO] = []
        multipart_files: list[tuple[str, tuple[str, BinaryIO, str]]] = []

        try:
            for entry in files:
                filename, handle, mime_type, owns_handle = self._open_file_entry(entry)
                if owns_handle:
                    opened_handles.append(handle)
                multipart_files.append(("files", (filename, handle, mime_type)))

            form_data: dict[str, str] = {
                "metadata": metadata_json,
                "notify_record_owners": str(notify_owners).lower(),
                "id_scheme": id_scheme or "import-recid",
                "no_updates": str(no_updates).lower(),
                "all_or_none": str(all_or_none).lower(),
            }
            if alternate_id_scheme:
                form_data["alternate_id_scheme"] = alternate_id_scheme

            if progress is not None:
                progress("start")
            try:
                response = self.session.post(
                    url,
                    headers=self._auth_headers(),
                    files=multipart_files,
                    data=form_data,
                    verify=self.verify_ssl,
                )
            except requests.exceptions.RequestException as exc:
                raise ImportRequestError(f"Import request failed: {exc}") from exc
            finally:
                if progress is not None:
                    progress("done")

            return self._result_from_response(response)
        finally:
            for handle in opened_handles:
                handle.close()

    def import_works_or_raise(
        self,
        collection_id: str,
        metadata: MetadataInput,
        files: Sequence[FileInput],
        **kwargs: Any,
    ) -> ImportResult:
        """Like :meth:`import_works`, but raise :class:`ImportAPIError` if not ok.

        Args:
            collection_id: Target collection ID or slug.
            metadata: See :meth:`import_works`.
            files: See :meth:`import_works`.
            **kwargs: Forwarded to :meth:`import_works`.

        Returns:
            Successful or partial-success :class:`ImportResult`.

        Raises:
            ImportAPIError: When the HTTP status is not 201 or 207.
        """
        result = self.import_works(collection_id, metadata, files, **kwargs)
        if not result.ok:
            message = result.message or f"Import failed with HTTP {result.status_code}"
            raise ImportAPIError(
                message,
                status_code=result.status_code,
                body=result.body,
            )
        return result

    @staticmethod
    def _open_file_entry(
        entry: FileInput,
    ) -> tuple[str, BinaryIO, str, bool]:
        """Normalize a file input to ``(filename, handle, mime, owns_handle)``.

        Returns:
            Filename, binary handle, MIME type, and whether this method opened
            the handle (caller must close it).

        Raises:
            TypeError: If ``entry`` is not a path or supported tuple form.
        """
        if isinstance(entry, (str, Path)):
            path = Path(entry)
            handle = path.open("rb")
            return path.name, handle, guess_mime_type(path), True

        if isinstance(entry, tuple):
            if len(entry) == 2:
                filename, handle = entry  # type: ignore[misc]
                mime_type = guess_mime_type(filename)
                return str(filename), handle, mime_type, False
            if len(entry) == 3:
                filename, handle, mime_type = entry  # type: ignore[misc]
                return str(filename), handle, str(mime_type), False

        raise TypeError(
            "each file must be a path or (filename, BinaryIO[, mime_type]) tuple"
        )

    @staticmethod
    def _result_from_response(response: requests.Response) -> ImportResult:
        try:
            body: dict[str, Any] | str | None = response.json()
        except ValueError:
            text = response.text
            return ImportResult(
                status_code=response.status_code,
                body=text,
                message="",
            )

        if not isinstance(body, Mapping):
            return ImportResult(status_code=response.status_code, body=body)

        data = body.get("data") or []
        errors = body.get("errors") or []
        message = body.get("message") or ""
        if not isinstance(data, list):
            data = []
        if not isinstance(errors, list):
            errors = []
        return ImportResult(
            status_code=response.status_code,
            data=list(data),
            errors=list(errors),
            message=str(message),
            body=dict(body),
        )

"""Unit tests for ImportClient library API (in-memory metadata / progress)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from helpers.sample_metadata import sample_metadata_journal_article_pdf

from kcworks_import_client import ImportClient
from kcworks_import_client.client import serialize_metadata
from kcworks_import_client.exceptions import ImportAPIError, ImportRequestError


@pytest.fixture
def sample_files_dir() -> Path:
    """Path to packaged sample files.

    Returns:
        Directory containing sample upload files for tests.
    """
    path = Path(__file__).resolve().parent / "helpers" / "sample_files"
    if not path.exists():
        pytest.skip("Sample files directory not found")
    return path


def test_serialize_metadata_variants(tmp_path):
    """serialize_metadata accepts path, JSON string, list, and single dict."""
    path = tmp_path / "m.json"
    path.write_text('[{"a": 1}]', encoding="utf-8")
    assert serialize_metadata(path) == '[{"a": 1}]'
    assert serialize_metadata('[{"b": 2}]') == '[{"b": 2}]'
    assert json.loads(serialize_metadata({"metadata": {"title": "t"}})) == [
        {"metadata": {"title": "t"}}
    ]
    assert json.loads(serialize_metadata([{"x": 1}])) == [{"x": 1}]
    with pytest.raises(TypeError):
        serialize_metadata(123)  # type: ignore[arg-type]


def test_import_client_file_tuple_and_non_json_body(
    sample_files_dir, monkeypatch, requests_mock
):
    """File tuples upload; non-JSON responses populate body as text."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    # Mock the API endpoint to return a non-JSON response (502 error)
    requests_mock.post(
        "http://127.0.0.1:8000/api/import/c",
        text="not-json",
        status_code=502,
        headers={"Content-Type": "text/plain"},
    )

    # Monkeypatch the base URL to use our test server
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://127.0.0.1:8000/api/import")

    data = sample_file.read_bytes()
    client = ImportClient("k")
    result = client.import_works(
        "c",
        metadata=[{"metadata": {"title": "t"}}],
        files=[("upload.pdf", io.BytesIO(data), "application/pdf")],
    )

    assert not result.ok
    assert result.status_code == 502
    assert result.body == "not-json"
    assert result.exit_code == 1


def test_import_client_passes_all_flags(sample_files_dir, monkeypatch, requests_mock):
    """ImportClient posts all flag parameters in the multipart form data."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    # Mock the API endpoint
    requests_mock.post(
        "http://127.0.0.1:8000/api/import/my-collection",
        json={
            "status": "success",
            "data": [{"record_id": "abc", "item_index": 0}],
            "errors": [],
            "message": "ok"
        },
        status_code=201
    )

    # Monkeypatch the base URL to use our test server
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://127.0.0.1:8000/api/import")

    client = ImportClient("test-key")
    result = client.import_works(
        "my-collection",
        metadata=[sample_metadata_journal_article_pdf],
        files=[sample_file],
        notify_owners=True,
        id_scheme="import-recid",
        alternate_id_scheme="doi",
        no_updates=True,
        all_or_none=True,
    )

    assert result.ok
    assert result.status_code == 201

    # Verify the request body contained all expected flag fields
    raw = requests_mock.last_request.body
    request_body = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    assert b'name="notify_record_owners"' in request_body
    assert b"true" in request_body
    assert b'name="id_scheme"' in request_body
    assert b'import-recid' in request_body
    assert b'name="alternate_id_scheme"' in request_body
    assert b'doi' in request_body
    assert b'name="no_updates"' in request_body
    assert b"true" in request_body
    assert b'name="all_or_none"' in request_body
    assert b"true" in request_body


def test_import_works_or_raise_on_403(sample_files_dir, monkeypatch, requests_mock):
    """import_works_or_raise raises ImportAPIError for non-ok statuses."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    requests_mock.post(
        "http://kcworks.test/api/import/my-collection",
        json={"status": "error", "data": [], "errors": [], "message": "denied"},
        status_code=403,
    )
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://kcworks.test/api/import")

    client = ImportClient("test-key")
    with pytest.raises(ImportAPIError) as exc_info:
        client.import_works_or_raise(
            "my-collection",
            metadata={"metadata": {"title": "x"}},
            files=[str(sample_file)],
        )

    assert exc_info.value.status_code == 403


def test_import_client_transport_error(monkeypatch, requests_mock):
    """ImportRequestError is raised when the request transport fails."""
    import requests

    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://kcworks.test/api/import")
    requests_mock.post(
        "http://kcworks.test/api/import/c",
        exc=requests.exceptions.ConnectionError("boom"),
    )
    client = ImportClient("test-key")
    with pytest.raises(ImportRequestError):
        client.import_works(
            "c",
            metadata=[{"metadata": {"title": "t"}}],
            files=[],
        )


def test_import_client_path_metadata_file(
    sample_files_dir, tmp_path, monkeypatch, requests_mock
):
    """Metadata Path is read from disk."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    meta = tmp_path / "meta.json"
    meta.write_text(
        json.dumps([sample_metadata_journal_article_pdf]),
        encoding="utf-8",
    )

    requests_mock.post(
        "http://kcworks.test/api/import/c",
        json={"data": [], "errors": [], "message": "ok"},
        status_code=201,
    )
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://kcworks.test/api/import")
    result = ImportClient("k").import_works("c", metadata=meta, files=[sample_file])
    assert result.ok

"""Unit tests for ImportClient library API (in-memory metadata / progress)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from helpers.sample_metadata import sample_metadata_journal_article_pdf
from kcworks_import_client import ImportClient, ImportResult
from kcworks_import_client.exceptions import ImportAPIError, ImportRequestError


@pytest.fixture
def sample_files_dir() -> Path:
    """Path to packaged sample files."""
    path = Path(__file__).resolve().parent / "helpers" / "sample_files"
    if not path.exists():
        pytest.skip("Sample files directory not found")
    return path


def test_import_client_accepts_list_metadata_and_progress(sample_files_dir, monkeypatch):
    """ImportClient posts in-memory metadata and invokes the progress callback."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    captured: dict = {}
    events: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            captured["path"] = self.path
            captured["body"] = body
            payload = {
                "status": "success",
                "data": [{"record_id": "abc", "item_index": 0}],
                "errors": [],
                "message": "ok",
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "KCWORKS_IMPORT_API_URL", f"http://127.0.0.1:{port}/api/import"
    )

    try:
        client = ImportClient("test-key")
        result = client.import_works(
            "my-collection",
            metadata=[sample_metadata_journal_article_pdf],
            files=[sample_file],
            notify_owners=True,
            id_scheme="import-recid",
            progress=events.append,
        )
    finally:
        server.shutdown()

    assert isinstance(result, ImportResult)
    assert result.ok
    assert result.status_code == 201
    assert result.data[0]["record_id"] == "abc"
    assert events == ["start", "done"]
    assert captured["path"].endswith("/my-collection")
    assert b'name="notify_record_owners"' in captured["body"]
    assert b"true" in captured["body"]


def test_import_works_or_raise_on_403(sample_files_dir, monkeypatch):
    """import_works_or_raise raises ImportAPIError for non-ok statuses."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            raw = json.dumps(
                {"status": "error", "data": [], "errors": [], "message": "denied"}
            ).encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "KCWORKS_IMPORT_API_URL", f"http://127.0.0.1:{port}/api/import"
    )

    client = ImportClient("test-key")
    try:
        with pytest.raises(ImportAPIError) as exc_info:
            client.import_works_or_raise(
                "my-collection",
                metadata={"metadata": {"title": "x"}},
                files=[str(sample_file)],
            )
    finally:
        server.shutdown()

    assert exc_info.value.status_code == 403


def test_import_client_transport_error(monkeypatch):
    """ImportRequestError is raised when the server cannot be reached."""
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://127.0.0.1:1/api/import")
    client = ImportClient("test-key")
    with pytest.raises(ImportRequestError):
        client.import_works(
            "c",
            metadata=[{"metadata": {"title": "t"}}],
            files=[],
        )

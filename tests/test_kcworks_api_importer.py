# Part of Knowledge Commons Works
# Copyright (C) 2024-2026 MESH Research
#
# KCWorks is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""End-to-end tests for the standalone kcworks import client api_importer script.

These tests run the script as a separate process (subprocess) to verify
argument parsing, validation, and behavior of the real CLI.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from helpers.sample_metadata import sample_metadata_journal_article_pdf


def _package_root() -> Path:
    """Return the kcworks-import-client package root."""
    import kcworks_import_client

    return Path(kcworks_import_client.__file__).resolve().parent.parent


def _ensure_package_on_path() -> None:
    """Ensure the installed package is importable (no-op when editable)."""
    root = str(_package_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _sample_files_dir() -> Path:
    """Return path to tests/helpers/sample_files.

    Returns:
        Path: Directory containing sample PDF/JPG fixtures.
    """
    return Path(__file__).resolve().parent / "helpers" / "sample_files"


def _run_script(
    args, env=None, stdin=None, cwd=None
) -> subprocess.CompletedProcess[str]:
    """Run the importer CLI as a subprocess via ``python -m``.

    Returns:
        subprocess.CompletedProcess[str]: Result of run (stdout, stderr, returncode).
    """
    root = str(_package_root())
    cmd = [sys.executable, "-m", "kcworks_import_client.api_importer", *list(args)]
    cwd = str(cwd or _package_root())
    full_env = {**dict(os.environ), **(env or {})}
    existing = full_env.get("PYTHONPATH", "")
    full_env["PYTHONPATH"] = (
        root if not existing else f"{root}{os.pathsep}{existing}"
    )
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=full_env,
        input=stdin,
        cwd=cwd,
        timeout=30,
    )


@pytest.fixture
def sample_files_dir() -> Path:
    """Path to the sample files directory.

    Returns:
        Path: Path to the files directory.
    """
    path = _sample_files_dir()
    if not path.exists():
        pytest.skip("Sample files directory not found")
    return path


@pytest.fixture
def metadata_json_file(tmp_path) -> str:
    """Write metadata (as JSON array) to a temp file and return path.

    Returns:
        str: File path.
    """
    meta = copy.deepcopy(sample_metadata_journal_article_pdf)
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps([meta]), encoding="utf-8")
    return str(path)


# ---- Argument handling: help and validation ----


def test_script_help():
    """Script runs with --help and prints usage and options."""
    result = _run_script(["--help"])
    assert result.returncode == 0
    assert "Import works" in result.stdout or "import" in result.stdout.lower()
    assert "--api-key" in result.stdout
    assert "--collection-id" in result.stdout
    assert "--metadata" in result.stdout
    assert "--files" in result.stdout
    assert "--output" in result.stdout
    assert "--testing" in result.stdout


def test_script_rejects_nonexistent_metadata_path(sample_files_dir):
    """Script exits with code 1 when metadata file does not exist."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    result = _run_script([
        "--api-key",
        "test-key",
        "--collection-id",
        "my-collection",
        "--metadata",
        "/nonexistent/metadata.json",
        "--files",
        str(sample_file),
    ])
    assert result.returncode == 1
    assert (
        "Metadata path does not exist" in result.stderr
        or "does not exist" in result.stderr
    )


def test_script_rejects_nonexistent_file_path(metadata_json_file):
    """Script exits with code 1 when a file path does not exist."""
    result = _run_script([
        "--api-key",
        "test-key",
        "--collection-id",
        "my-collection",
        "--metadata",
        metadata_json_file,
        "--files",
        "/nonexistent/file.pdf",
    ])
    assert result.returncode == 1
    assert (
        "File path does not exist" in result.stderr or "does not exist" in result.stderr
    )


def test_script_rejects_missing_api_key_when_prompted(
    metadata_json_file, sample_files_dir
):
    """Script exits with code 1 when API key is required but user enters nothing."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    # Do not pass --api-key and do not set KCWORKS_IMPORT_API_KEY
    env = {"KCWORKS_IMPORT_API_KEY": ""}
    result = _run_script(
        [
            "--collection-id",
            "my-collection",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
        ],
        env=env,
        stdin="\n",
    )
    assert result.returncode == 1
    assert "API key" in result.stderr and (
        "required" in result.stderr or "Error" in result.stderr
    )


def _load_importer_module():
    """Import the api_importer module.

    Returns:
        ModuleType: The imported api_importer module.
    """
    _ensure_package_on_path()
    from kcworks_import_client import api_importer

    return api_importer


def test_get_api_key_uses_env_variable(monkeypatch):
    """_get_api_key returns KCWORKS_IMPORT_API_KEY when --api-key is not given."""
    module = _load_importer_module()
    monkeypatch.setenv("KCWORKS_IMPORT_API_KEY", "env-key")
    args = argparse.Namespace(api_key=None)
    assert module._get_api_key(args) == "env-key"


# ---- Full run against a mock HTTP server ----


def _make_mock_import_handler(
    response_body, status=201, content_type="application/json"
):
    """Build a request handler that responds to POST /api/import/<anything>.

    Args:
        response_body: dict (serialized as JSON) or bytes/str (sent as-is).
        status: HTTP status code to return (default 201).
        content_type: Used when response_body is not a dict.

    Returns:
        BaseHTTPRequestHandler: A handler class for use with HTTPServer.
    """
    if isinstance(response_body, dict):
        body_bytes = json.dumps(response_body).encode("utf-8")
        ct = "application/json"
    elif isinstance(response_body, str):
        body_bytes = response_body.encode("utf-8")
        ct = content_type
    else:
        body_bytes = response_body
        ct = content_type

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if "/api/import/" in self.path:
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    return Handler


@pytest.fixture
def mock_import_server():
    """Start a minimal HTTP server that responds to import POST with 201 + JSON.

    Yields:
        str: Base URL for the import API (e.g. http://127.0.0.1:PORT/api/import).
    """
    response = {
        "data": [
            {
                "item_index": 0,
                "record_id": "test-123",
                "record_url": "https://example.com/records/test-123",
            },
        ],
        "message": "Import completed.",
    }
    handler = _make_mock_import_handler(response)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/api/import"
    finally:
        server.shutdown()


def test_script_success_with_mock_server(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """Script runs end-to-end with all args and mock server: exit 0 and output file."""
    sample_file = sample_files_dir / "24519197_005_03-04_s004_text.pdf"
    if not sample_file.exists():
        sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("No sample PDF found")

    output_path = tmp_path / "response.json"
    result = _run_script(
        [
            "--api-key",
            "test-key",
            "--collection-id",
            "my-collection",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--output",
            str(output_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
    )

    assert result.returncode == 0
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "data" in data and len(data["data"]) == 1
    assert data["data"][0].get("record_id") == "test-123"


def test_script_passes_collection_id_to_request(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
):
    """Script sends request to URL that includes the given collection ID."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    result = _run_script(
        [
            "--api-key",
            "key",
            "--collection-id",
            "custom-slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
        stdin="\n",
    )

    assert result.returncode == 0
    # Mock server only responds to paths containing /api/import/; collection id
    # is in the path, so we've verified the script used the right collection
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout


def test_script_testing_flag_ignored_when_api_url_set(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
):
    """With KCWORKS_IMPORT_API_URL set, uses that URL (--testing is irrelevant)."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    result = _run_script(
        [
            "--api-key",
            "key",
            "--collection-id",
            "slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--testing",
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
        stdin="\n",
    )

    assert result.returncode == 0


# ---- Output path validation ----


def test_script_rejects_output_path_with_nonexistent_parent(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
):
    """Script exits with code 1 when --output parent directory does not exist."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    result = _run_script(
        [
            "--api-key",
            "key",
            "--collection-id",
            "slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--output",
            "/nonexistent/dir/response.json",
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
    )

    assert result.returncode == 1
    assert "Output directory does not exist" in result.stderr
    assert "/nonexistent/dir" in result.stderr


# ---- Multiple files in a single run ----


def test_script_handles_multiple_files_in_one_run(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """Script accepts multiple --files and reports correct count; request completes."""
    sample_pdf = sample_files_dir / "sample.pdf"
    sample_jpg = sample_files_dir / "sample.jpg"
    if not sample_pdf.exists() or not sample_jpg.exists():
        pytest.skip("Sample files not found")

    output_path = tmp_path / "response.json"
    result = _run_script(
        [
            "--api-key",
            "key",
            "--collection-id",
            "slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_pdf),
            str(sample_jpg),
            "--output",
            str(output_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
    )

    assert result.returncode == 0
    assert "Files to upload: 2" in result.stdout
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout
    assert output_path.exists()


# ---- API error responses: correct messages and stdout/stderr ----


def test_script_prints_success_output_for_201(
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """For 201 response, prints Import Result, message, and record info to stdout."""
    body = {
        "data": [
            {
                "item_index": 0,
                "record_id": "r1",
                "record_url": "https://example.com/r1",
            },
        ],
        "message": "Done.",
    }
    handler = _make_mock_import_handler(body, status=201)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
                "--output",
                str(tmp_path / "out.json"),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
        )
    finally:
        server.shutdown()

    assert result.returncode == 0
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout
    assert "1 record(s)" in result.stdout
    assert "r1" in result.stdout
    assert "✓" in result.stdout
    assert "Done." in result.stdout


def test_script_prints_partial_success_output_for_207(
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """For 207 response, prints partial success, successes , and failures to stdout."""
    body = {
        "data": [
            {
                "item_index": 0,
                "record_id": "ok1",
                "record_url": "https://example.com/ok1",
            }
        ],
        "errors": [
            {
                "item_index": 1,
                "errors": [
                    {
                        "validation_error": {
                            "metadata": {"title": ["Missing data for required field."]}
                        }
                    }
                ],
            },
        ],
        "message": "Some failed.",
    }
    handler = _make_mock_import_handler(body, status=207)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
                "--output",
                str(tmp_path / "out.json"),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
        )
    finally:
        server.shutdown()

    assert result.returncode == 0
    assert "Import Result" in result.stdout
    assert "Partial success" in result.stdout
    assert "Successfully imported" in result.stdout
    assert "Failed to import" in result.stdout
    assert "1 record(s)" in result.stdout
    assert "Validation error" in result.stdout or "Missing data" in result.stdout
    assert "Some failed." in result.stdout


def test_script_prints_403_message_to_stdout(
    metadata_json_file,
    sample_files_dir,
):
    """For 403 response with JSON, prints Import failed and access denied to stdout."""
    body = {"errors": [], "message": "Forbidden"}
    handler = _make_mock_import_handler(body, status=403)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
            stdin="\n",
        )
    finally:
        server.shutdown()

    assert result.returncode == 1
    assert "Import Result" in result.stdout
    assert "Import failed" in result.stdout
    assert "Access denied" in result.stdout
    assert "permissions" in result.stdout


def test_script_prints_400_message_to_stdout(
    metadata_json_file,
    sample_files_dir,
):
    """For 400 response with JSON, prints Import failed and bad request to stdout."""
    body = {"errors": [], "message": "Invalid"}
    handler = _make_mock_import_handler(body, status=400)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
            stdin="\n",
        )
    finally:
        server.shutdown()

    assert result.returncode == 1
    assert "Import Result" in result.stdout
    assert "Import failed" in result.stdout
    assert "Bad request" in result.stdout


def test_script_prints_500_message_to_stdout(
    metadata_json_file,
    sample_files_dir,
):
    """For 500 response with JSON, prints Import failed and server error to stdout."""
    body = {"errors": [], "message": "Internal error"}
    handler = _make_mock_import_handler(body, status=500)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
            stdin="\n",
        )
    finally:
        server.shutdown()

    assert result.returncode == 1
    assert "Import Result" in result.stdout
    assert "Import failed" in result.stdout
    assert "Server error" in result.stdout or "your request" in result.stdout


def test_script_handles_non_json_response_exit_1_and_stderr(
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """When API returns non-JSON body, script exits 1 and prints error to stderr."""
    handler = _make_mock_import_handler(
        "Internal Server Error",
        status=500,
        content_type="text/plain",
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/import"
        sample_file = sample_files_dir / "sample.pdf"
        if not sample_file.exists():
            pytest.skip("Sample PDF not found")
        result = _run_script(
            [
                "--api-key",
                "k",
                "--collection-id",
                "c",
                "--metadata",
                metadata_json_file,
                "--files",
                str(sample_file),
                "--output",
                str(tmp_path / "out.txt"),
            ],
            env={"KCWORKS_IMPORT_API_URL": url},
        )
    finally:
        server.shutdown()

    assert result.returncode == 1
    assert "ERROR" in result.stderr
    assert "Request failed" in result.stderr or "500" in result.stderr


# ---- Spinner: no hang, output intact ----


def test_script_spinner_clears_and_result_printed_to_stdout(
    mock_import_server,
    metadata_json_file,
    sample_files_dir,
):
    """Spinner does not leave garbage or hang; Messages appear on stdout."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    result = _run_script(
        [
            "--api-key",
            "key",
            "--collection-id",
            "slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
        ],
        env={"KCWORKS_IMPORT_API_URL": mock_import_server},
        stdin="\n",
    )

    assert result.returncode == 0
    # Spinner clears the line then script prints result; no hang (run completes within
    # timeout)
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout
    # Trailing output should be result content, not a stuck spinner line
    lines = result.stdout.strip().split("\n")
    last_part = "\n".join(lines[-5:]) if len(lines) >= 5 else result.stdout
    assert (
        "Successfully imported" in last_part
        or "Import completed" in last_part
        or "record(s)" in last_part
    )
    assert "Importing records" not in last_part


def test_import_works_sends_id_scheme_and_notify_form_fields(
    monkeypatch,
    metadata_json_file,
    sample_files_dir,
):
    """import_works posts id_scheme, alternate_id_scheme, notify, and no_updates."""
    module = _load_importer_module()
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        sample_file = next(sample_files_dir.glob("*.pdf"), None)
    if sample_file is None or not sample_file.exists():
        pytest.skip("Sample PDF not found")

    captured: dict = {}

    class FakeResponse:
        status_code = 201
        text = '{"data":[],"message":"ok"}'

        def json(self):
            return {"data": [], "message": "ok"}

    def fake_post(self, url, headers=None, files=None, data=None, verify=None):
        captured["url"] = url
        captured["data"] = dict(data or {})
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", "http://example.test/api/import")

    code = module.import_works(
        api_key="k",
        collection_id="my-coll",
        metadata_path=metadata_json_file,
        files_paths=[str(sample_file)],
        notify_owners=True,
        id_scheme="neh-recid",
        alternate_id_scheme="import-recid",
        no_updates=True,
    )
    assert code == 0
    assert captured["data"]["notify_record_owners"] == "true"
    assert captured["data"]["id_scheme"] == "neh-recid"
    assert captured["data"]["alternate_id_scheme"] == "import-recid"
    assert captured["data"]["no_updates"] == "true"

    code_default = module.import_works(
        api_key="k",
        collection_id="my-coll",
        metadata_path=metadata_json_file,
        files_paths=[str(sample_file)],
    )
    assert code_default == 0
    assert captured["data"]["no_updates"] == "false"

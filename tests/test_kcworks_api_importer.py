# Part of Knowledge Commons Works
# Copyright (C) 2024-2026 MESH Research
#
# KCWorks is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""End-to-end tests for the standalone kcworks import client api_importer script.

Help/validation tests run the CLI as a subprocess. Import API tests run
the CLI in-process with requests-mock (subprocess cannot see the mock).
"""

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers.mock_apis import DEFAULT_HOST, register_import_endpoint
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


# ---- Full run against requests-mock (in-process CLI) ----


def _run_cli(monkeypatch, capsys, args, *, env=None) -> SimpleNamespace:
    """Run ``api_importer.main`` in-process with the given argv.

    Returns:
        Namespace with ``returncode``, ``stdout``, and ``stderr``.
    """
    module = _load_importer_module()
    for key, value in (env or {}).items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["kcworks-api-importer", *list(args)])
    with pytest.raises(SystemExit) as exc:
        module.main()
    code = exc.value.code
    if code is None:
        code = 0
    captured = capsys.readouterr()
    return SimpleNamespace(returncode=code, stdout=captured.out, stderr=captured.err)


def _default_success_body():
    return {
        "data": [
            {
                "item_index": 0,
                "record_id": "test-123",
                "record_url": "https://example.com/records/test-123",
            },
        ],
        "errors": [],
        "message": "Import completed.",
    }


def test_script_success_with_mock(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """Script runs end-to-end with all args: exit 0 and report file."""
    sample_file = sample_files_dir / "24519197_005_03-04_s004_text.pdf"
    if not sample_file.exists():
        sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("No sample PDF found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="my-collection",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
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
            str(tmp_path),
            "--skip-output-prompt",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout
    reports = list(tmp_path.glob("kcworks_import_*.json"))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert "data" in data and len(data["data"]) == 1
    assert data["data"][0].get("record_id") == "test-123"


def test_script_passes_collection_id_to_request(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
):
    """Script sends request to URL that includes the given collection ID."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="custom-slug",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
        [
            "--api-key",
            "key",
            "--collection-id",
            "custom-slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--skip-output-prompt",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert requests_mock.last_request.url.endswith("/custom-slug")
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout


def test_script_testing_flag_ignored_when_api_url_set(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
):
    """With KCWORKS_IMPORT_API_URL set, uses that URL (--testing is irrelevant)."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="slug",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
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
            "--skip-output-prompt",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0


def test_script_rejects_output_path_with_nonexistent_parent(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
):
    """Script exits with code 1 when --output directory does not exist."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="slug",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
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
            "/nonexistent/dir",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 1
    assert "Report output directory does not exist" in result.stderr
    assert "/nonexistent/dir" in result.stderr


def test_script_handles_multiple_files_in_one_run(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """Script accepts multiple --files and reports correct count; request completes."""
    sample_pdf = sample_files_dir / "sample.pdf"
    sample_jpg = sample_files_dir / "sample.jpg"
    if not sample_pdf.exists() or not sample_jpg.exists():
        pytest.skip("Sample files not found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="slug",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
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
            str(tmp_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert "Files to upload: 2" in result.stdout
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout or "Import Result" in result.stdout
    assert list(tmp_path.glob("kcworks_import_*.json"))


def test_script_prints_success_output_for_201(
    monkeypatch,
    capsys,
    requests_mock,
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
    import_url = register_import_endpoint(
        requests_mock,
        collection_id="c",
        response_body=body,
        status_code=201,
    )
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    result = _run_cli(
        monkeypatch,
        capsys,
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
            str(tmp_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout
    assert "1 record(s)" in result.stdout
    assert "r1" in result.stdout
    assert "✓" in result.stdout
    assert "Done." in result.stdout


def test_script_prints_partial_success_output_for_207(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """For 207 response, prints partial success, successes, and failures to stdout."""
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
                            "metadata": {
                                "title": ["Missing data for required field."]
                            }
                        }
                    }
                ],
            },
        ],
        "message": "Some failed.",
    }
    import_url = register_import_endpoint(
        requests_mock,
        collection_id="c",
        response_body=body,
        status_code=207,
    )
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    result = _run_cli(
        monkeypatch,
        capsys,
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
            str(tmp_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert "Import Result" in result.stdout
    assert "Partial success" in result.stdout
    assert "Successfully imported" in result.stdout
    assert "Failed to import" in result.stdout
    assert "1 record(s)" in result.stdout
    assert "Validation error" in result.stdout or "Missing data" in result.stdout
    assert "Some failed." in result.stdout


@pytest.mark.parametrize(
    ("status", "stdout_needles"),
    [
        (403, ("Import failed", "Access denied", "permissions")),
        (400, ("Import failed", "Bad request")),
        (500, ("Import failed",)),
    ],
)
def test_script_prints_error_status_messages(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
    status,
    stdout_needles,
):
    """For 4xx/5xx JSON responses, prints Import failed and status-specific text."""
    import_url = register_import_endpoint(
        requests_mock,
        collection_id="c",
        response_body={"errors": [], "message": "err"},
        status_code=status,
    )
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    result = _run_cli(
        monkeypatch,
        capsys,
        [
            "--api-key",
            "k",
            "--collection-id",
            "c",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--skip-output-prompt",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 1
    assert "Import Result" in result.stdout
    for needle in stdout_needles:
        assert needle in result.stdout
    if status == 500:
        assert "Server error" in result.stdout or "your request" in result.stdout


def test_script_handles_non_json_response_exit_1_and_stderr(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
    tmp_path,
):
    """When API returns non-JSON body, script exits 1 and prints error to stderr."""
    import_url = register_import_endpoint(
        requests_mock,
        collection_id="c",
        response_body="Internal Server Error",
        status_code=500,
        content_type="text/plain",
    )
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")
    result = _run_cli(
        monkeypatch,
        capsys,
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
            str(tmp_path),
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 1
    assert "ERROR" in result.stderr
    assert "Request failed" in result.stderr or "500" in result.stderr


def test_script_spinner_clears_and_result_printed_to_stdout(
    monkeypatch,
    capsys,
    requests_mock,
    metadata_json_file,
    sample_files_dir,
):
    """Spinner does not leave garbage or hang; messages appear on stdout."""
    sample_file = sample_files_dir / "sample.pdf"
    if not sample_file.exists():
        pytest.skip("Sample PDF not found")

    import_url = register_import_endpoint(
        requests_mock,
        collection_id="slug",
        response_body=_default_success_body(),
        status_code=201,
    )
    result = _run_cli(
        monkeypatch,
        capsys,
        [
            "--api-key",
            "key",
            "--collection-id",
            "slug",
            "--metadata",
            metadata_json_file,
            "--files",
            str(sample_file),
            "--skip-output-prompt",
        ],
        env={"KCWORKS_IMPORT_API_URL": import_url},
    )

    assert result.returncode == 0
    assert "Import Result" in result.stdout
    assert "Successfully imported" in result.stdout
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
    requests_mock,
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

    import_url = f"{DEFAULT_HOST}/api/import"
    requests_mock.post(
        f"{import_url}/my-coll",
        json={"data": [], "message": "ok"},
        status_code=201,
    )
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", import_url)

    code = module.import_works(
        api_key="k",
        collection_id="my-coll",
        metadata_path=metadata_json_file,
        files_paths=[str(sample_file)],
        notify_owners=True,
        id_scheme="neh-recid",
        alternate_id_scheme="import-recid",
        no_updates=True,
        all_or_none=True,
        suppress_reports=True,
    )
    assert code == 0
    body = requests_mock.last_request.body
    if isinstance(body, str):
        body = body.encode("utf-8")
    assert b'name="notify_record_owners"' in body
    assert b'name="id_scheme"' in body
    assert b"neh-recid" in body
    assert b'name="alternate_id_scheme"' in body
    assert b"import-recid" in body
    assert b'name="no_updates"' in body
    assert b'name="all_or_none"' in body

    code_default = module.import_works(
        api_key="k",
        collection_id="my-coll",
        metadata_path=metadata_json_file,
        files_paths=[str(sample_file)],
        suppress_reports=True,
    )
    assert code_default == 0
    body_default = requests_mock.last_request.body
    if isinstance(body_default, str):
        body_default = body_default.encode("utf-8")
    assert b'name="no_updates"' in body_default
    assert b"false" in body_default


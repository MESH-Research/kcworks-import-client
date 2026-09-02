"""Interactive prompt / env happy-path coverage for CLI helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from kcworks_import_client import api_importer
from kcworks_import_client import multi_collection_importer as multi


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


def test_get_api_key_from_prompt(monkeypatch):
    """Interactive prompt supplies API key when CLI/env are empty."""
    monkeypatch.delenv("KCWORKS_IMPORT_API_KEY", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "prompted-key")
    args = argparse.Namespace(api_key=None)
    assert api_importer._get_api_key(args) == "prompted-key"


def test_get_collection_id_from_prompt_and_env(monkeypatch):
    """Collection id comes from env or interactive prompt."""
    monkeypatch.setenv("KCWORKS_IMPORT_COLLECTION_ID", "env-coll")
    args = argparse.Namespace(collection_id=None)
    assert api_importer._get_collection_id(args) == "env-coll"

    monkeypatch.delenv("KCWORKS_IMPORT_COLLECTION_ID", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "prompt-coll")
    assert api_importer._get_collection_id(args) == "prompt-coll"


def test_get_metadata_path_from_prompt(monkeypatch, tmp_path):
    """Metadata path can be prompted and validated."""
    meta = tmp_path / "m.json"
    meta.write_text("[]", encoding="utf-8")
    monkeypatch.delenv("KCWORKS_IMPORT_METADATA_PATH", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": str(meta))
    args = argparse.Namespace(metadata=None)
    assert api_importer._get_metadata_path(args) == str(meta)


def test_get_files_paths_from_env_and_prompt(monkeypatch, sample_files_dir):
    """Files paths parse from env (comma-separated) and prompt."""
    pdf = sample_files_dir / "sample.pdf"
    if not pdf.exists():
        pytest.skip("Sample PDF not found")
    monkeypatch.setenv("KCWORKS_IMPORT_FILES_PATH", f"{pdf}, {pdf}")
    args = argparse.Namespace(files=None)
    paths = api_importer._get_files_paths(args)
    assert paths == [str(pdf), str(pdf)]

    monkeypatch.delenv("KCWORKS_IMPORT_FILES_PATH", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": str(pdf))
    assert api_importer._get_files_paths(args) == [str(pdf)]


def test_get_output_path_prompt_skip_and_env(monkeypatch, tmp_path):
    """Output path: env, prompt skip (None), and prompt value."""
    out = tmp_path / "out.json"
    monkeypatch.setenv("KCWORKS_IMPORT_OUTPUT_PATH", str(out))
    args = argparse.Namespace(output=None)
    assert api_importer._get_output_path(args) == str(out)

    monkeypatch.delenv("KCWORKS_IMPORT_OUTPUT_PATH", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert api_importer._get_output_path(args) is None

    monkeypatch.setattr("builtins.input", lambda _prompt="": str(out))
    assert api_importer._get_output_path(args) == str(out)


def test_get_manifest_path_from_prompt(monkeypatch, tmp_path):
    """Manifest path can be prompted when CLI/env are empty."""
    manifest = tmp_path / "m.json"
    manifest.write_text("[]", encoding="utf-8")
    monkeypatch.delenv("KCWORKS_IMPORT_MANIFEST_PATH", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": str(manifest))
    args = argparse.Namespace(manifest=None)
    assert multi._get_manifest_path(args) == str(manifest)


def test_empty_collection_id_prompt_exits(monkeypatch):
    """Empty collection-id prompt exits with code 1."""
    monkeypatch.delenv("KCWORKS_IMPORT_COLLECTION_ID", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    args = argparse.Namespace(collection_id=None)
    with pytest.raises(SystemExit) as exc:
        api_importer._get_collection_id(args)
    assert exc.value.code == 1

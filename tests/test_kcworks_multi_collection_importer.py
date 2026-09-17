# Part of Knowledge Commons Works
# Copyright (C) 2024-2026 MESH Research
#
# KCWorks is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""End-to-end tests for the multi-collection importer client script.

Help/validation tests run as a subprocess. Full orchestration tests run
the CLI in-process with requests-mock.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers.mock_apis import register_mock_apis
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
    """Return path to tests/helpers/sample_files."""
    return Path(__file__).resolve().parent / "helpers" / "sample_files"


def _run_script(
    args, env=None, stdin=None, cwd=None
) -> subprocess.CompletedProcess[str]:
    """Run the multi-collection importer as a subprocess via ``python -m``.

    Returns:
        CompletedProcess with stdout, stderr, and returncode.
    """
    root = str(_package_root())
    cmd = [
        sys.executable,
        "-m",
        "kcworks_import_client.multi_collection_importer",
        *list(args),
    ]
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
        timeout=60,
    )


def _load_multi_module():
    """Import the multi-collection importer module.

    Returns:
        The loaded module object.
    """
    _ensure_package_on_path()
    from kcworks_import_client import multi_collection_importer

    return multi_collection_importer


@pytest.fixture
def sample_files_dir() -> Path:
    """Path to sample files.

    Returns:
        Path to the sample files directory.
    """
    path = _sample_files_dir()
    if not path.exists():
        pytest.skip("Sample files directory not found")
    return path


@pytest.fixture
def sample_pdf(sample_files_dir) -> Path:
    """A sample PDF path for import fixtures.

    Returns:
        Path to an existing sample PDF file.
    """
    for name in ("sample.pdf", "24519197_005_03-04_s004_text.pdf"):
        path = sample_files_dir / name
        if path.exists():
            return path
    pytest.skip("No sample PDF found")


@pytest.fixture
def import_bundle(tmp_path, sample_pdf) -> Path:
    """Create a small import bundle (metadata + file) under tmp_path.

    Returns:
        Directory containing metadata.json and a copy/link target for files.
    """
    meta = copy.deepcopy(sample_metadata_journal_article_pdf)
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps([meta]), encoding="utf-8")
    files_path = tmp_path / sample_pdf.name
    files_path.write_bytes(sample_pdf.read_bytes())
    return tmp_path


def test_script_help():
    """Script runs with --help and prints usage and options."""
    result = _run_script(["--help"])
    assert result.returncode == 0
    assert "--api-key" in result.stdout
    assert "--manifest" in result.stdout
    assert "--assign-parents" in result.stdout
    assert "--testing" in result.stdout


def test_script_rejects_missing_manifest(tmp_path):
    """Script exits 1 when the manifest path does not exist."""
    result = _run_script([
        "--api-key",
        "test-key",
        "--manifest",
        str(tmp_path / "missing.yaml"),
    ])
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_script_rejects_empty_api_key_prompt(import_bundle):
    """Script exits 1 when API key prompt is empty."""
    manifest = {
        "collections": [
            {
                "slug": "c1",
                "name": "Collection One",
                "metadata": "metadata.json",
                "files": list(import_bundle.glob("*.pdf"))[0].name,
            }
        ]
    }
    manifest_path = import_bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _run_script(
        ["--manifest", str(manifest_path)],
        env={"KCWORKS_IMPORT_API_KEY": ""},
        stdin="\n",
    )
    assert result.returncode == 1
    assert "API key" in result.stderr


def test_load_manifest_json_and_list_form(tmp_path):
    """_load_manifest accepts collections wrapper and bare list."""
    module = _load_multi_module()
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(
        json.dumps({
            "collections": [{"slug": "a", "name": "A"}],
        }),
        encoding="utf-8",
    )
    bare = tmp_path / "bare.json"
    bare.write_text(
        json.dumps([{"slug": "b", "name": "B"}]),
        encoding="utf-8",
    )
    assert module._load_manifest(str(wrapped))[0]["slug"] == "a"
    assert module._load_manifest(str(bare))[0]["slug"] == "b"


def test_load_manifest_rejects_missing_slug(tmp_path):
    """_load_manifest exits when an entry lacks slug."""
    module = _load_multi_module()
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"collections": [{"name": "No Slug"}]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        module._load_manifest(str(path))
    assert exc.value.code == 1


def test_topological_order_parents_before_children():
    """_topological_order places parents ahead of their children."""
    module = _load_multi_module()
    entries = [
        {"slug": "child", "name": "Child", "parent_slug": "parent"},
        {"slug": "parent", "name": "Parent"},
        {"slug": "grandchild", "name": "Grand", "parent_slug": "child"},
    ]
    ordered = module._topological_order(entries)
    slugs = [e["slug"] for e in ordered]
    assert slugs.index("parent") < slugs.index("child")
    assert slugs.index("child") < slugs.index("grandchild")


def test_get_manifest_path_uses_env(monkeypatch, tmp_path):
    """_get_manifest_path reads KCWORKS_IMPORT_MANIFEST_PATH."""
    module = _load_multi_module()
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"collections": [{"slug": "x", "name": "X"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KCWORKS_IMPORT_MANIFEST_PATH", str(manifest))
    args = argparse.Namespace(manifest=None)
    assert module._get_manifest_path(args) == str(manifest)


def _run_cli(monkeypatch, capsys, args, *, env=None) -> SimpleNamespace:
    """Run ``multi_collection_importer.cli`` in-process.

    Returns:
        Namespace with ``returncode``, ``stdout``, and ``stderr``.
    """
    module = _load_multi_module()
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        sys,
        "argv",
        ["kcworks-multi-collection-importer", *list(args)],
    )
    with pytest.raises(SystemExit) as exc:
        module.cli()
    code = exc.value.code
    if code is None:
        code = 0
    captured = capsys.readouterr()
    return SimpleNamespace(returncode=code, stdout=captured.out, stderr=captured.err)


def test_full_run_creates_collections_assigns_parents_and_imports(
    monkeypatch,
    capsys,
    requests_mock,
    import_bundle,
    sample_pdf,
):
    """End-to-end: create collections, link parent, import records."""
    apis = register_mock_apis(requests_mock)
    pdf_name = sample_pdf.name
    assert (import_bundle / pdf_name).exists() or list(import_bundle.glob("*.pdf"))

    file_name = list(import_bundle.glob("*.pdf"))[0].name
    manifest = {
        "collections": [
            {
                "slug": "parent-coll",
                "name": "Parent Collection",
                "metadata": "metadata.json",
                "files": file_name,
            },
            {
                "slug": "child-coll",
                "name": "Child Collection",
                "parent_slug": "parent-coll",
                "metadata": "metadata.json",
                "files": file_name,
            },
        ]
    }
    manifest_path = import_bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run_cli(
        monkeypatch,
        capsys,
        [
            "--api-key",
            "test-key",
            "--manifest",
            str(manifest_path),
            "--assign-parents",
            "--output",
            str(import_bundle),
        ],
        env={
            "KCWORKS_COMMUNITIES_API_URL": apis["communities_url"],
            "KCWORKS_IMPORT_API_URL": apis["import_url"],
        },
    )

    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    state = apis["state"]
    assert "parent-coll" in state["communities"]
    assert "child-coll" in state["communities"]
    assert state["communities"]["parent-coll"]["children"]["allow"] is True
    assert state["communities"]["child-coll"].get("parent", {}).get("slug") == (
        "parent-coll"
    )
    assert state["join_requests"]
    assert {item["slug"] for item in state["imports"]} == {
        "parent-coll",
        "child-coll",
    }
    assert list(import_bundle.glob("kcworks_import_parent-coll_*.json"))
    assert list(import_bundle.glob("kcworks_import_child-coll_*.json"))
    assert "Multi-collection import finished successfully" in result.stdout


def test_full_run_skips_existing_collection_and_parent_link(
    monkeypatch,
    capsys,
    requests_mock,
    import_bundle,
):
    """Re-run is idempotent for existing collections and parent links."""
    apis = register_mock_apis(requests_mock)
    file_name = list(import_bundle.glob("*.pdf"))[0].name
    apis["state"]["communities"]["parent-coll"] = {
        "id": "uuid-parent-coll",
        "slug": "parent-coll",
        "metadata": {"title": "Parent Collection"},
        "access": {},
        "children": {"allow": True},
        "revision_id": 2,
    }
    apis["state"]["communities"]["child-coll"] = {
        "id": "uuid-child-coll",
        "slug": "child-coll",
        "metadata": {"title": "Child Collection"},
        "access": {},
        "children": {"allow": False},
        "revision_id": 1,
        "parent": {"id": "uuid-parent-coll", "slug": "parent-coll"},
    }

    manifest = {
        "collections": [
            {
                "slug": "parent-coll",
                "name": "Parent Collection",
                "metadata": "metadata.json",
                "files": file_name,
            },
            {
                "slug": "child-coll",
                "name": "Child Collection",
                "parent_slug": "parent-coll",
                "metadata": "metadata.json",
                "files": file_name,
            },
        ]
    }
    manifest_path = import_bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run_cli(
        monkeypatch,
        capsys,
        [
            "--api-key",
            "test-key",
            "--manifest",
            str(manifest_path),
            "--assign-parents",
            "--suppress-reports",
        ],
        env={
            "KCWORKS_COMMUNITIES_API_URL": apis["communities_url"],
            "KCWORKS_IMPORT_API_URL": apis["import_url"],
        },
    )

    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert "already exists" in result.stdout
    assert "already linked" in result.stdout
    assert apis["state"]["join_requests"] == []


def test_entry_notify_and_id_scheme_overrides():
    """Per-entry notify/id_scheme override run-wide defaults."""
    module = _load_multi_module()
    entry = {
        "slug": "c",
        "name": "C",
        "notify_record_owners": True,
        "id_scheme": "neh-recid",
        "alternate_id_scheme": "import-recid",
    }
    assert module._entry_notify_owners(entry, default=False) is True
    assert module._entry_notify_owners({}, default=True) is True
    assert module._entry_notify_owners(
        {"notify_record_owners": "false"}, default=True
    ) is False
    assert module._entry_id_scheme(entry, default="import-recid") == "neh-recid"
    assert module._entry_id_scheme({}, default="import-recid") == "import-recid"
    assert (
        module._entry_alternate_id_scheme(entry, default="") == "import-recid"
    )
    assert module._entry_alternate_id_scheme({}, default="x") == "x"
    # Explicit empty alternate clears the default
    assert (
        module._entry_alternate_id_scheme(
            {"alternate_id_scheme": ""}, default="x"
        )
        == ""
    )
    assert module._entry_no_updates({"no_updates": True}, default=False) is True
    assert module._entry_no_updates({}, default=False) is False
    assert module._entry_no_updates({"no_updates": "false"}, default=True) is False

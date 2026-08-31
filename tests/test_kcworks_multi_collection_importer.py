# Part of Knowledge Commons Works
# Copyright (C) 2024-2026 MESH Research
#
# KCWorks is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""End-to-end tests for the multi-collection importer client script.

These tests run the script as a subprocess (and load helpers as a module)
to verify argument parsing, manifest handling, and orchestration against
a mock communities + import HTTP server.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

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


def _make_combined_handler(state: dict):
    """Build a handler for communities + import endpoints.

    Args:
        state: Mutable dict tracking created communities and import posts.
            Keys: ``communities`` (slug → community dict), ``imports`` (list).

    Returns:
        A BaseHTTPRequestHandler subclass for use with HTTPServer.
    """

    class Handler(BaseHTTPRequestHandler):
        def _read_json(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _send(self, status: int, payload: dict | list | str):
            if isinstance(payload, (dict, list)):
                body = json.dumps(payload).encode("utf-8")
                content_type = "application/json"
            else:
                body = str(payload).encode("utf-8")
                content_type = "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            # /api/communities/<slug_or_id>
            prefix = "/api/communities/"
            if path.startswith(prefix) and "/actions/" not in path:
                key = path[len(prefix) :].rstrip("/")
                for community in state["communities"].values():
                    if community["slug"] == key or community["id"] == key:
                        self._send(200, community)
                        return
                self._send(404, {"message": "Not found"})
                return
            self._send(404, {"message": "Not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path.rstrip("/") == "/api/communities":
                data = self._read_json()
                slug = data.get("slug", "unnamed")
                community = {
                    "id": f"uuid-{slug}",
                    "slug": slug,
                    "metadata": data.get("metadata", {"title": slug}),
                    "access": data.get("access", {}),
                    "children": {"allow": False},
                    "revision_id": 1,
                }
                state["communities"][slug] = community
                self._send(201, community)
                return

            if path.endswith("/actions/join-request"):
                data = self._read_json()
                child_id = data.get("community_id")
                parent_id = path.split("/")[-3]
                child = next(
                    (
                        c
                        for c in state["communities"].values()
                        if c["id"] == child_id
                    ),
                    None,
                )
                parent = next(
                    (
                        c
                        for c in state["communities"].values()
                        if c["id"] == parent_id
                    ),
                    None,
                )
                if child and parent:
                    child["parent"] = {
                        "id": parent["id"],
                        "slug": parent["slug"],
                    }
                state["join_requests"].append(data)
                self._send(
                    201,
                    {
                        "id": "req-1",
                        "status": "accepted",
                        "type": "subcommunity",
                    },
                )
                return

            if path.startswith("/api/import/"):
                # Drain multipart body without parsing
                length = int(self.headers.get("Content-Length", 0))
                if length:
                    self.rfile.read(length)
                slug = path[len("/api/import/") :].rstrip("/")
                state["imports"].append(slug)
                self._send(
                    201,
                    {
                        "data": [
                            {
                                "item_index": 0,
                                "record_id": f"rec-{slug}",
                                "record_url": f"https://example.com/{slug}",
                            }
                        ],
                        "message": "Import completed.",
                    },
                )
                return

            self._send(404, {"message": "Not found"})

        def do_PUT(self):
            path = urlparse(self.path).path
            prefix = "/api/communities/"
            if path.startswith(prefix):
                key = path[len(prefix) :].rstrip("/")
                data = self._read_json()
                for community in state["communities"].values():
                    if community["id"] == key or community["slug"] == key:
                        if "children" in data:
                            community["children"] = data["children"]
                        community["revision_id"] = (
                            community.get("revision_id", 1) + 1
                        )
                        self._send(200, community)
                        return
                self._send(404, {"message": "Not found"})
                return
            self._send(404, {"message": "Not found"})

        def log_message(self, format, *args):
            pass

    return Handler


@pytest.fixture
def mock_kcworks_apis():
    """Start a mock server exposing communities + import APIs.

    Yields:
        dict with ``communities_url``, ``import_url``, and mutable ``state``.
    """
    state = {"communities": {}, "imports": [], "join_requests": []}
    handler = _make_combined_handler(state)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield {
            "communities_url": f"http://127.0.0.1:{port}/api/communities",
            "import_url": f"http://127.0.0.1:{port}/api/import",
            "state": state,
        }
    finally:
        server.shutdown()


def test_full_run_creates_collections_assigns_parents_and_imports(
    mock_kcworks_apis,
    import_bundle,
    sample_pdf,
):
    """End-to-end: create collections, link parent, import records."""
    pdf_name = sample_pdf.name
    # Ensure file is in import_bundle (fixture copies it)
    assert (import_bundle / pdf_name).exists() or list(import_bundle.glob("*.pdf"))

    file_name = list(import_bundle.glob("*.pdf"))[0].name
    manifest = {
        "collections": [
            {
                "slug": "parent-coll",
                "name": "Parent Collection",
                "metadata": "metadata.json",
                "files": file_name,
                "output": "parent-out.json",
            },
            {
                "slug": "child-coll",
                "name": "Child Collection",
                "parent_slug": "parent-coll",
                "metadata": "metadata.json",
                "files": file_name,
                "output": "child-out.json",
            },
        ]
    }
    manifest_path = import_bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run_script(
        [
            "--api-key",
            "test-key",
            "--manifest",
            str(manifest_path),
            "--assign-parents",
        ],
        env={
            "KCWORKS_COMMUNITIES_API_URL": mock_kcworks_apis["communities_url"],
            "KCWORKS_IMPORT_API_URL": mock_kcworks_apis["import_url"],
        },
    )

    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    state = mock_kcworks_apis["state"]
    assert "parent-coll" in state["communities"]
    assert "child-coll" in state["communities"]
    assert state["communities"]["parent-coll"]["children"]["allow"] is True
    assert state["communities"]["child-coll"].get("parent", {}).get("slug") == (
        "parent-coll"
    )
    assert state["join_requests"]
    assert set(state["imports"]) == {"parent-coll", "child-coll"}
    assert (import_bundle / "parent-out.json").exists()
    assert (import_bundle / "child-out.json").exists()
    assert "Multi-collection import finished successfully" in result.stdout


def test_full_run_skips_existing_collection_and_parent_link(
    mock_kcworks_apis,
    import_bundle,
):
    """Re-run is idempotent for existing collections and parent links."""
    file_name = list(import_bundle.glob("*.pdf"))[0].name
    # Pre-seed communities as already linked
    mock_kcworks_apis["state"]["communities"]["parent-coll"] = {
        "id": "uuid-parent-coll",
        "slug": "parent-coll",
        "metadata": {"title": "Parent Collection"},
        "access": {},
        "children": {"allow": True},
        "revision_id": 2,
    }
    mock_kcworks_apis["state"]["communities"]["child-coll"] = {
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

    result = _run_script(
        [
            "--api-key",
            "test-key",
            "--manifest",
            str(manifest_path),
            "--assign-parents",
        ],
        env={
            "KCWORKS_COMMUNITIES_API_URL": mock_kcworks_apis["communities_url"],
            "KCWORKS_IMPORT_API_URL": mock_kcworks_apis["import_url"],
        },
    )

    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert "already exists" in result.stdout
    assert "already linked" in result.stdout
    assert mock_kcworks_apis["state"]["join_requests"] == []


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

"""Library tests for MultiCollectionImporter, manifests, and communities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers.mock_apis import start_mock_apis
from helpers.sample_metadata import sample_metadata_journal_article_pdf
from kcworks_import_client import MultiCollectionImporter
from kcworks_import_client.exceptions import CommunityError, ManifestError
from kcworks_import_client.multi_client import (
    coerce_bool,
    load_manifest,
    topological_order,
)


@pytest.fixture
def sample_files_dir() -> Path:
    """Path to packaged sample files."""
    path = Path(__file__).resolve().parent / "helpers" / "sample_files"
    if not path.exists():
        pytest.skip("Sample files directory not found")
    return path


@pytest.fixture
def import_bundle(tmp_path, sample_files_dir) -> Path:
    """Temp dir with metadata.json and a sample PDF."""
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps([sample_metadata_journal_article_pdf]),
        encoding="utf-8",
    )
    pdf = sample_files_dir / "sample.pdf"
    if not pdf.exists():
        pytest.skip("Sample PDF not found")
    target = tmp_path / pdf.name
    target.write_bytes(pdf.read_bytes())
    return tmp_path


def test_load_manifest_yaml(tmp_path):
    """load_manifest accepts YAML collections manifests."""
    path = tmp_path / "manifest.yaml"
    path.write_text(
        yaml.dump({
            "collections": [
                {"slug": "hist", "name": "History", "id_scheme": "neh-recid"},
            ]
        }),
        encoding="utf-8",
    )
    entries = load_manifest(path)
    assert entries[0]["slug"] == "hist"
    assert entries[0]["id_scheme"] == "neh-recid"


def test_load_manifest_extensionless_yaml(tmp_path):
    """Extensionless files fall back to YAML after JSON fails."""
    path = tmp_path / "manifest"
    path.write_text(
        "collections:\n  - slug: a\n    name: A\n",
        encoding="utf-8",
    )
    assert load_manifest(path)[0]["slug"] == "a"


def test_load_manifest_rejects_empty_and_bad_types(tmp_path):
    """load_manifest raises ManifestError for empty / invalid structures."""
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"collections": []}), encoding="utf-8")
    with pytest.raises(ManifestError, match="no collection"):
        load_manifest(empty)

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    with pytest.raises(ManifestError, match="Invalid manifest"):
        load_manifest(bad)

    not_obj = tmp_path / "not_obj.json"
    not_obj.write_text(json.dumps({"collections": ["x"]}), encoding="utf-8")
    with pytest.raises(ManifestError, match="not an object"):
        load_manifest(not_obj)


def test_load_manifest_validates_optional_field_types(tmp_path):
    """Per-entry optional fields must have expected types."""
    path = tmp_path / "bad_scheme.json"
    path.write_text(
        json.dumps({
            "collections": [
                {"slug": "a", "name": "A", "id_scheme": 123},
            ]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="id_scheme"):
        load_manifest(path)


def test_topological_order_detects_cycle():
    """Cycles in parent_slug raise ManifestError."""
    entries = [
        {"slug": "a", "name": "A", "parent_slug": "b"},
        {"slug": "b", "name": "B", "parent_slug": "a"},
    ]
    with pytest.raises(ManifestError, match="Cycle"):
        topological_order(entries)


def test_coerce_bool_variants():
    """coerce_bool accepts bools, common strings, and defaults."""
    assert coerce_bool(True) is True
    assert coerce_bool("yes") is True
    assert coerce_bool("0") is False
    assert coerce_bool(None, default=True) is True
    assert coerce_bool(2) is True


def test_multi_importer_run_manifest_yaml(
    import_bundle, sample_files_dir, monkeypatch
):
    """MultiCollectionImporter.run_manifest works with a YAML manifest."""
    server, apis = start_mock_apis()
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", apis["import_url"])
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    pdf_name = (import_bundle / "sample.pdf").name
    manifest = import_bundle / "manifest.yml"
    manifest.write_text(
        yaml.dump({
            "collections": [
                {
                    "slug": "dept",
                    "name": "Department",
                    "metadata": "metadata.json",
                    "files": pdf_name,
                    "output": "out.json",
                    "notify_record_owners": True,
                    "no_updates": "false",
                }
            ]
        }),
        encoding="utf-8",
    )
    logs: list[str] = []
    try:
        importer = MultiCollectionImporter("key", log=logs.append)
        result = importer.run_manifest(manifest, assign_parents=False)
    finally:
        server.shutdown()

    assert result.ok
    assert "dept" in result.communities
    assert "dept" in result.imports
    assert result.imports["dept"].ok
    assert (import_bundle / "out.json").exists()
    assert any("Ensuring collections" in line for line in logs)


def test_multi_importer_assign_parents_and_skip_existing(monkeypatch, import_bundle):
    """run_manifest creates parent links and skips already-linked children."""
    server, apis = start_mock_apis()
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", apis["import_url"])
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    pdf_name = "sample.pdf"
    # Pre-seed parent and child already linked
    apis["state"]["communities"]["parent"] = {
        "id": "uuid-parent",
        "slug": "parent",
        "metadata": {"title": "Parent"},
        "access": {},
        "children": {"allow": True},
        "revision_id": 1,
    }
    apis["state"]["communities"]["child"] = {
        "id": "uuid-child",
        "slug": "child",
        "metadata": {"title": "Child"},
        "access": {},
        "children": {"allow": False},
        "revision_id": 1,
        "parent": {"id": "uuid-parent", "slug": "parent"},
    }
    manifest = import_bundle / "m.json"
    manifest.write_text(
        json.dumps({
            "collections": [
                {
                    "slug": "parent",
                    "name": "Parent",
                    "metadata": "metadata.json",
                    "files": pdf_name,
                },
                {
                    "slug": "child",
                    "name": "Child",
                    "parent_slug": "parent",
                    "metadata": "metadata.json",
                    "files": pdf_name,
                },
            ]
        }),
        encoding="utf-8",
    )
    try:
        importer = MultiCollectionImporter("key")
        result = importer.run_manifest(manifest, assign_parents=True)
    finally:
        server.shutdown()

    assert result.ok
    assert apis["state"]["join_requests"] == []  # already linked → skip


def test_multi_importer_skips_entries_without_files(monkeypatch, tmp_path):
    """Entries with neither metadata nor files are skipped."""
    server, apis = start_mock_apis()
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", apis["import_url"])
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({
            "collections": [{"slug": "empty", "name": "Empty"}],
        }),
        encoding="utf-8",
    )
    try:
        result = MultiCollectionImporter("key").run_manifest(manifest)
    finally:
        server.shutdown()
    assert result.ok
    assert result.skipped == ["empty"]
    assert result.imports == {}


def test_multi_importer_missing_parent_raises(monkeypatch, import_bundle):
    """Missing parent_slug target raises ManifestError."""
    server, apis = start_mock_apis()
    monkeypatch.setenv("KCWORKS_IMPORT_API_URL", apis["import_url"])
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    manifest = import_bundle / "m.json"
    manifest.write_text(
        json.dumps({
            "collections": [
                {
                    "slug": "child",
                    "name": "Child",
                    "parent_slug": "missing-parent",
                    "metadata": "metadata.json",
                    "files": "sample.pdf",
                }
            ]
        }),
        encoding="utf-8",
    )
    try:
        with pytest.raises(ManifestError, match="Parent collection"):
            MultiCollectionImporter("key").run_manifest(
                manifest, assign_parents=True
            )
    finally:
        server.shutdown()


def test_community_create_failure_raises(monkeypatch):
    """create_community raises CommunityError on non-2xx."""
    server, apis = start_mock_apis(
        extra_state={"post_community_status": 500}
    )
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    try:
        with pytest.raises(CommunityError, match="Failed to create"):
            MultiCollectionImporter("key").create_community("x", "X")
    finally:
        server.shutdown()


def test_get_community_unexpected_status(monkeypatch):
    """get_community raises CommunityError on unexpected HTTP status."""
    server, apis = start_mock_apis(extra_state={"get_status": 503})
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    try:
        with pytest.raises(CommunityError, match="Failed to fetch"):
            MultiCollectionImporter("key").get_community("anything")
    finally:
        server.shutdown()


def test_assign_parent_conflicting_parent(monkeypatch):
    """assign_parent raises when child already has a different parent."""
    server, apis = start_mock_apis()
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    parent = {
        "id": "uuid-p",
        "slug": "p",
        "metadata": {"title": "P"},
        "access": {},
        "children": {"allow": True},
    }
    child = {
        "id": "uuid-c",
        "slug": "c",
        "metadata": {"title": "C"},
        "access": {},
        "parent": {"id": "uuid-other", "slug": "other"},
    }
    try:
        with pytest.raises(CommunityError, match="different parent"):
            MultiCollectionImporter("key").assign_parent(child, parent)
    finally:
        server.shutdown()


def test_enable_children_put_failure(monkeypatch):
    """enable_children raises CommunityError when PUT fails."""
    server, apis = start_mock_apis(extra_state={"put_status": 400})
    monkeypatch.setenv("KCWORKS_COMMUNITIES_API_URL", apis["communities_url"])
    community = {
        "id": "uuid-p",
        "slug": "p",
        "metadata": {"title": "P"},
        "access": {},
        "children": {"allow": False},
        "revision_id": 1,
    }
    apis["state"]["communities"]["p"] = community
    try:
        with pytest.raises(CommunityError, match="enable children"):
            MultiCollectionImporter("key").enable_children(community)
    finally:
        server.shutdown()


def test_normalize_files_validation(tmp_path):
    """normalize_files rejects bad shapes and missing paths."""
    with pytest.raises(ManifestError, match="Invalid 'files'"):
        MultiCollectionImporter.normalize_files({"a": 1}, tmp_path, "s")
    with pytest.raises(ManifestError, match="File not found"):
        MultiCollectionImporter.normalize_files("missing.pdf", tmp_path, "s")


def test_entry_override_helpers():
    """Per-entry override helpers respect defaults and overrides."""
    entry = {
        "notify_record_owners": "true",
        "id_scheme": "neh-recid",
        "alternate_id_scheme": "import-recid",
        "no_updates": False,
    }
    assert MultiCollectionImporter.entry_notify_owners(entry, False) is True
    assert MultiCollectionImporter.entry_id_scheme({}, "import-recid") == (
        "import-recid"
    )
    assert MultiCollectionImporter.entry_id_scheme(entry, "x") == "neh-recid"
    assert (
        MultiCollectionImporter.entry_alternate_id_scheme(entry, "")
        == "import-recid"
    )
    assert MultiCollectionImporter.entry_no_updates(entry, True) is False

#!/usr/bin/env python3
# Part of Knowledge Commons Works
#
# Copyright (C) 2023-2026, MESH Research
#
# knowledge-commons-works is free software; you can redistribute and/or
# modify it under the terms of the MIT License; see LICENSE file for more details.

"""Bulk-import records into multiple KCWorks collections from a manifest.

Command-line interface and compatibility wrappers around
:class:`~kcworks_import_client.multi_client.MultiCollectionImporter`.

For library use::

    from kcworks_import_client import MultiCollectionImporter

    importer = MultiCollectionImporter(api_key="...")
    result = importer.run_manifest("manifest.json", assign_parents=True)

See the module docstring history / KCWorks API docs for the manifest schema
and CLI flags.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

from .api_importer import _get_api_key
from .exceptions import CommunityError, ManifestError
from .multi_client import (
    MultiCollectionImporter,
    coerce_bool,
    load_manifest,
    resolve_communities_base_url,
    topological_order,
)

# Re-export for callers / tests that import from this module.
_coerce_bool = coerce_bool
_api_bases = resolve_communities_base_url
_topological_order = topological_order


def _print_error(message: str, details: str | None = None) -> None:
    """Print a formatted error message to stderr."""
    print("", file=sys.stderr)
    print("✗ ERROR", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print(f"  {message}", file=sys.stderr)
    if details:
        print(f"  Details: {details}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print("", file=sys.stderr)


def _exit_on_error(exc: Exception) -> NoReturn:
    """Print ``exc`` and exit with status 1."""
    message = str(exc)
    if ": " in message:
        head, _, tail = message.partition(": ")
        _print_error(head, tail)
    else:
        _print_error(message)
    sys.exit(1)


def _load_manifest(manifest_path: str) -> list[dict[str, Any]]:
    """Load and validate the import manifest (CLI wrapper).

    Args:
        manifest_path: Path to a JSON or YAML manifest file.

    Returns:
        List of validated collection entry dicts.
    """
    try:
        return load_manifest(manifest_path)
    except ManifestError as exc:
        _exit_on_error(exc)


def _auth_headers(api_key: str) -> dict[str, str]:
    """Build standard JSON API auth headers.

    Args:
        api_key: Bearer token.

    Returns:
        Headers dict for communities API requests.
    """
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _entry_notify_owners(entry: dict[str, Any], default: bool) -> bool:
    return MultiCollectionImporter.entry_notify_owners(entry, default)


def _entry_id_scheme(entry: dict[str, Any], default: str) -> str:
    return MultiCollectionImporter.entry_id_scheme(entry, default)


def _entry_alternate_id_scheme(entry: dict[str, Any], default: str) -> str:
    return MultiCollectionImporter.entry_alternate_id_scheme(entry, default)


def _entry_no_updates(entry: dict[str, Any], default: bool) -> bool:
    return MultiCollectionImporter.entry_no_updates(entry, default)


def _resolve_path(path_value: str, manifest_dir: Path) -> str:
    return MultiCollectionImporter.resolve_path(path_value, manifest_dir)


def _normalize_files(
    files_value: Any, manifest_dir: Path, slug: str
) -> list[str]:
    try:
        return MultiCollectionImporter.normalize_files(
            files_value, manifest_dir, slug
        )
    except ManifestError as exc:
        _exit_on_error(exc)


def _importer(api_key: str, testing: bool = False) -> MultiCollectionImporter:
    return MultiCollectionImporter(
        api_key,
        testing=testing,
        log=print,
    )


def get_community(
    api_key: str,
    slug_or_id: str,
    testing: bool = False,
) -> dict[str, Any] | None:
    """Fetch a community by slug or UUID (CLI wrapper).

    Args:
        api_key: Bearer token.
        slug_or_id: Community slug or UUID.
        testing: Use the localhost instance when True.

    Returns:
        Community payload, or ``None`` when not found.
    """
    try:
        return _importer(api_key, testing).get_community(slug_or_id)
    except CommunityError as exc:
        _exit_on_error(exc)


def create_community(
    api_key: str,
    slug: str,
    name: str,
    testing: bool = False,
) -> dict[str, Any]:
    """Create a community owned by the authenticated user (CLI wrapper).

    Args:
        api_key: Bearer token.
        slug: Community slug.
        name: Community display name.
        testing: Use the localhost instance when True.

    Returns:
        Created community payload.
    """
    try:
        return _importer(api_key, testing).create_community(slug, name)
    except CommunityError as exc:
        _exit_on_error(exc)


def ensure_community(
    api_key: str,
    slug: str,
    name: str,
    testing: bool = False,
) -> dict[str, Any]:
    """Return an existing community by slug, or create it (CLI wrapper).

    Args:
        api_key: Bearer token.
        slug: Community slug.
        name: Community display name used when creating.
        testing: Use the localhost instance when True.

    Returns:
        Existing or newly created community payload.
    """
    try:
        return _importer(api_key, testing).ensure_community(slug, name)
    except CommunityError as exc:
        _exit_on_error(exc)


def enable_children(
    api_key: str,
    community: dict[str, Any],
    testing: bool = False,
) -> dict[str, Any]:
    """Ensure ``children.allow`` is true on a parent community (CLI wrapper).

    Args:
        api_key: Bearer token.
        community: Parent community payload.
        testing: Use the localhost instance when True.

    Returns:
        Updated community payload.
    """
    try:
        return _importer(api_key, testing).enable_children(community)
    except CommunityError as exc:
        _exit_on_error(exc)


def assign_parent(
    api_key: str,
    child: dict[str, Any],
    parent: dict[str, Any],
    testing: bool = False,
) -> None:
    """Link a child community under a parent via join-request (CLI wrapper)."""
    try:
        _importer(api_key, testing).assign_parent(child, parent)
    except CommunityError as exc:
        _exit_on_error(exc)


def run_collection_creation_job(
    api_key: str,
    collection_slug: str,
    collection_name: str,
    testing: bool = False,
) -> dict[str, Any]:
    """Create a KCWorks collection via the communities API if needed.

    Args:
        api_key: Bearer token.
        collection_slug: Collection slug.
        collection_name: Collection display name.
        testing: Use the localhost instance when True.

    Returns:
        Existing or newly created community payload.
    """
    return ensure_community(
        api_key, collection_slug, collection_name, testing=testing
    )


def run_import_job(
    api_key: str,
    json_location: str,
    files_location: list[str],
    output_location: str | None,
    slug: str,
    testing: bool = False,
    notify_owners: bool = False,
    id_scheme: str = "import-recid",
    alternate_id_scheme: str = "",
    no_updates: bool = False,
) -> int:
    """Import one record batch into a single collection (CLI wrapper).

    Returns:
        Exit code from the import (0 success, 1 failure).
    """
    from .api_importer import import_works

    print(f"\n--- Importing records into {slug!r} ---")
    return import_works(
        api_key=api_key,
        collection_id=slug,
        metadata_path=json_location,
        files_paths=files_location,
        output_path=output_location,
        testing=testing,
        notify_owners=notify_owners,
        id_scheme=id_scheme,
        alternate_id_scheme=alternate_id_scheme,
        no_updates=no_updates,
    )


def main(
    api_key: str,
    manifest_path: str,
    assign_parents: bool,
    testing: bool = False,
    notify_owners: bool = False,
    id_scheme: str = "import-recid",
    alternate_id_scheme: str = "",
    no_updates: bool = False,
) -> int:
    """Run the multi-collection import from a manifest (CLI wrapper).

    Returns:
        ``0`` if all steps succeed, ``1`` if any import job fails.
    """
    # Communities via MultiCollectionImporter; record batches via
    # ``run_import_job`` → ``import_works`` so CLI spinner/printing stay identical.
    try:
        manifest_dir = Path(manifest_path).resolve().parent
        entries = _load_manifest(manifest_path)
        ordered = _topological_order(entries)

        print("")
        print("=" * 70)
        print(f"Manifest: {manifest_path}")
        print(f"Collections: {len(ordered)}")
        print(f"Assign parents: {'yes' if assign_parents else 'no'}")
        print(f"Environment: {'Testing (localhost)' if testing else 'Production'}")
        print(
            f"Notify record owners (default): "
            f"{'yes' if notify_owners else 'no'}"
        )
        print(f"Import id scheme (default): {id_scheme}")
        if alternate_id_scheme:
            print(f"Alternate id scheme (default): {alternate_id_scheme}")
        print(f"No-updates (default): {'yes' if no_updates else 'no'}")
        print("=" * 70)

        communities: dict[str, dict[str, Any]] = {}
        print("\n=== Ensuring collections exist ===")
        for entry in ordered:
            slug = entry["slug"]
            communities[slug] = run_collection_creation_job(
                api_key, slug, entry["name"], testing=testing
            )

        if assign_parents:
            print("\n=== Assigning parent/child links ===")
            for entry in ordered:
                parent_slug = entry.get("parent_slug")
                if not parent_slug:
                    continue
                child = communities[entry["slug"]]
                parent = communities.get(parent_slug)
                if parent is None:
                    parent = get_community(api_key, parent_slug, testing=testing)
                    if parent is None:
                        _print_error(
                            f"Parent collection {parent_slug!r} not found for "
                            f"child {entry['slug']!r}.",
                            "Add the parent to the manifest or create it first.",
                        )
                        sys.exit(1)
                    communities[parent_slug] = parent
                parent = enable_children(api_key, parent, testing=testing)
                communities[parent_slug] = parent
                refreshed = get_community(api_key, child["id"], testing=testing)
                if refreshed is not None:
                    child = refreshed
                    communities[entry["slug"]] = child
                assign_parent(api_key, child, parent, testing=testing)

        print("\n=== Importing records ===")
        overall_ok = True
        for entry in ordered:
            metadata = entry.get("metadata")
            files = entry.get("files")
            if not metadata and not files:
                print(
                    f"  Skipping import for {entry['slug']!r} "
                    "(no metadata/files in manifest)"
                )
                continue
            if not metadata:
                _print_error(
                    f"Entry {entry['slug']!r} has files but no metadata path."
                )
                sys.exit(1)
            if not files:
                _print_error(
                    f"Entry {entry['slug']!r} has metadata but no files path(s)."
                )
                sys.exit(1)

            metadata_path_resolved = _resolve_path(str(metadata), manifest_dir)
            if not os.path.isfile(metadata_path_resolved):
                _print_error(
                    f"Metadata file not found for {entry['slug']!r}: "
                    f"{metadata_path_resolved}"
                )
                sys.exit(1)

            files_paths = _normalize_files(files, manifest_dir, entry["slug"])
            output_path = entry.get("output")
            if output_path:
                output_path = _resolve_path(str(output_path), manifest_dir)
                out_dir = os.path.dirname(output_path)
                if out_dir and not os.path.isdir(out_dir):
                    _print_error(f"Output directory does not exist: {out_dir}")
                    sys.exit(1)

            code = run_import_job(
                api_key=api_key,
                json_location=metadata_path_resolved,
                files_location=files_paths,
                output_location=output_path,
                slug=entry["slug"],
                testing=testing,
                notify_owners=_entry_notify_owners(entry, notify_owners),
                id_scheme=_entry_id_scheme(entry, id_scheme),
                alternate_id_scheme=_entry_alternate_id_scheme(
                    entry, alternate_id_scheme
                ),
                no_updates=_entry_no_updates(entry, no_updates),
            )
            if code != 0:
                overall_ok = False
                print(f"⚠ Import for {entry['slug']!r} reported failure")

        print("")
        print("=" * 70)
        if overall_ok:
            print("✓ Multi-collection import finished successfully")
        else:
            print("⚠ Multi-collection import finished with one or more failures")
        print("=" * 70)
        return 0 if overall_ok else 1
    except (ManifestError, CommunityError) as exc:
        _exit_on_error(exc)
        return 1  # pragma: no cover


def _get_manifest_path(args: argparse.Namespace) -> str:
    """Get path to the manifest JSON or YAML file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Path to an existing manifest file.

    Exits:
        SystemExit: If the path cannot be obtained or is invalid.
    """
    if args.manifest:
        manifest_path = str(args.manifest)
    else:
        manifest_path_env = os.getenv("KCWORKS_IMPORT_MANIFEST_PATH")
        if manifest_path_env:
            manifest_path = manifest_path_env
        else:
            manifest_path = input(
                "Enter the path to the manifest JSON or YAML file: "
            ).strip()
            if not manifest_path:
                print("Error: Manifest path is required.", file=sys.stderr)
                sys.exit(1)

    if not os.path.exists(manifest_path):
        print(
            f"Error: Manifest path does not exist: {manifest_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not os.path.isfile(manifest_path):
        print(
            f"Error: Manifest path is not a file: {manifest_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    return manifest_path


def cli() -> None:
    """CLI entry point."""
    print("=" * 70)
    print("KCWorks Multi-Collection API Import")
    print("=" * 70)

    parser = argparse.ArgumentParser(
        description=(
            "Import works into multiple KCWorks collections from a manifest."
        )
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (or set KCWORKS_IMPORT_API_KEY env var)",
    )
    parser.add_argument(
        "--manifest",
        help=(
            "Path to the import manifest file "
            "(or set KCWORKS_IMPORT_MANIFEST_PATH env var)"
        ),
    )
    parser.add_argument(
        "--assign-parents",
        action="store_true",
        help=(
            "Create parent-child relationships for collections that list "
            "a parent_slug in the manifest."
        ),
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help=(
            "Use a local testing KCWorks instance instead of production."
        ),
    )
    parser.add_argument(
        "--notify-record-owners",
        action="store_true",
        help=(
            "Enable email notification of users designated as record owners "
            "(default for entries that do not set notify_record_owners)."
        ),
    )
    parser.add_argument(
        "--id-scheme",
        default="import-recid",
        help=(
            "Default import dedupe scheme (default: import-recid). "
            "Overridable per manifest entry. Must be defined in KCWorks or "
            "pre-arranged for addition."
        ),
    )
    parser.add_argument(
        "--alternate-id-scheme",
        default="",
        help=(
            "Default secondary dedupe scheme. Overridable per manifest entry. "
            "Must be defined in KCWorks or pre-arranged for addition."
        ),
    )
    parser.add_argument(
        "--no-updates",
        action="store_true",
        help=(
            "Refuse to change existing matched records when metadata differs "
            "(default for entries that do not set no_updates; skips file "
            "reconciliation in that case). Default is to allow metadata "
            "updates; files are reconciled by filename and size "
            "(see import API docs)."
        ),
    )

    args = parser.parse_args()
    api_key = _get_api_key(args)
    manifest_path = _get_manifest_path(args)
    exit_code = main(
        api_key,
        manifest_path,
        args.assign_parents,
        testing=args.testing,
        notify_owners=args.notify_record_owners,
        id_scheme=args.id_scheme,
        alternate_id_scheme=args.alternate_id_scheme,
        no_updates=args.no_updates,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()

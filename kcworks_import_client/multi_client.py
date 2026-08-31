"""Multi-collection import orchestration and communities helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from .client import ImportClient, ProgressCallback
from .exceptions import CommunityError, ManifestError
from .results import ImportResult, MultiCollectionImportResult

DEFAULT_COMMUNITY_ACCESS = {
    "visibility": "public",
    "member_policy": "closed",
    "record_policy": "closed",
    "review_policy": "closed",
}

LogCallback = Callable[[str], None]


def resolve_communities_base_url(*, testing: bool = False) -> tuple[str, bool]:
    """Resolve communities API base URL and SSL verification flag.

    Args:
        testing: When True and no env override, use localhost.

    Returns:
        ``(base_url_without_trailing_slash, verify_ssl)``.
    """
    communities_env = os.getenv("KCWORKS_COMMUNITIES_API_URL")
    if communities_env:
        return communities_env.rstrip("/"), False

    import_env = os.getenv("KCWORKS_IMPORT_API_URL")
    if import_env:
        base = import_env.rstrip("/")
        if base.endswith("/import"):
            base = base[: -len("/import")] + "/communities"
        else:
            base = base.rsplit("/", 1)[0] + "/communities"
        return base, False

    if testing:
        return "https://localhost/api/communities", False
    return "https://works.hcommons.org/api/communities", True


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Coerce a manifest/CLI-style boolean value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    if value is None:
        return default
    return bool(value)


def load_manifest(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Load and validate an import manifest.

    Args:
        manifest_path: Path to a JSON or YAML manifest file.

    Returns:
        List of collection entry dicts.

    Raises:
        ManifestError: On read/parse/validation failure.
    """
    path = Path(manifest_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Cannot read manifest: {path}") from exc

    suffix = path.suffix.lower()
    data: Any
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ManifestError(
                "YAML manifest requires PyYAML. "
                "Install with: pip install 'kcworks-import-client[yaml]' "
                "(or use a .json manifest)."
            ) from exc
        data = yaml.safe_load(text)
    elif suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"Invalid JSON manifest: {path}") from exc
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ManifestError(
                    f"Could not parse manifest as JSON: {path}. "
                    "For YAML files, install PyYAML or use a .json extension."
                ) from exc
            data = yaml.safe_load(text)

    if isinstance(data, dict) and "collections" in data:
        entries = data["collections"]
    elif isinstance(data, list):
        entries = data
    else:
        raise ManifestError(
            "Invalid manifest structure. "
            "Expected a top-level 'collections' list or a bare list of entries."
        )

    if not isinstance(entries, list) or not entries:
        raise ManifestError("Manifest contains no collection entries.")

    validated: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ManifestError(f"Manifest entry {i} is not an object.")
        slug = entry.get("slug")
        name = entry.get("name")
        if not slug or not isinstance(slug, str):
            raise ManifestError(f"Manifest entry {i} is missing a string 'slug'.")
        if not name or not isinstance(name, str):
            raise ManifestError(
                f"Manifest entry {i} ({slug!r}) is missing a string 'name'."
            )
        if "id_scheme" in entry and not isinstance(entry["id_scheme"], str):
            raise ManifestError(
                f"Manifest entry {i} ({slug!r}): 'id_scheme' must be a string."
            )
        if "alternate_id_scheme" in entry and not isinstance(
            entry["alternate_id_scheme"], str
        ):
            raise ManifestError(
                f"Manifest entry {i} ({slug!r}): "
                "'alternate_id_scheme' must be a string."
            )
        if "notify_record_owners" in entry and not isinstance(
            entry["notify_record_owners"], (bool, str)
        ):
            raise ManifestError(
                f"Manifest entry {i} ({slug!r}): "
                "'notify_record_owners' must be a boolean or string."
            )
        if "no_updates" in entry and not isinstance(entry["no_updates"], (bool, str)):
            raise ManifestError(
                f"Manifest entry {i} ({slug!r}): "
                "'no_updates' must be a boolean or string."
            )
        validated.append(entry)

    return validated


def topological_order(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order entries so parents appear before their children when possible.

    Args:
        entries: Manifest collection entries.

    Returns:
        Entries ordered with parents first when both are in the manifest.

    Raises:
        ManifestError: If a ``parent_slug`` cycle is detected.
    """
    by_slug = {e["slug"]: e for e in entries}
    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[dict[str, Any]] = []

    def visit(slug: str) -> None:
        if slug in visited:
            return
        if slug in visiting:
            raise ManifestError(
                f"Cycle detected in parent_slug chain involving {slug!r}."
            )
        visiting.add(slug)
        entry = by_slug[slug]
        parent_slug = entry.get("parent_slug")
        if parent_slug and parent_slug in by_slug:
            visit(parent_slug)
        visiting.remove(slug)
        visited.add(slug)
        ordered.append(entry)

    for entry in entries:
        visit(entry["slug"])
    return ordered


class MultiCollectionImporter:
    """Create collections (as needed), optional parent links, and import batches.

    Example::

        from kcworks_import_client import MultiCollectionImporter

        importer = MultiCollectionImporter(api_key="...")
        result = importer.run_manifest("manifest.json", assign_parents=True)
        assert result.ok
    """

    def __init__(
        self,
        api_key: str,
        *,
        testing: bool = False,
        import_client: ImportClient | None = None,
        communities_base_url: str | None = None,
        verify_ssl: bool | None = None,
        session: requests.Session | None = None,
        log: LogCallback | None = None,
    ) -> None:
        """Create a multi-collection importer.

        Args:
            api_key: Bearer token.
            testing: Use localhost when no URL env overrides are set.
            import_client: Optional preconfigured :class:`ImportClient`.
            communities_base_url: Override communities API base.
            verify_ssl: Override TLS verification for communities calls.
            session: Shared ``requests.Session`` (also used by a default
                :class:`ImportClient` when one is not supplied).
            log: Optional callback for human-readable progress lines.
        """
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.testing = testing
        self.session = session or requests.Session()
        self.log = log or (lambda _msg: None)

        if communities_base_url is not None:
            self.communities_base_url = communities_base_url.rstrip("/")
            self.verify_ssl = True if verify_ssl is None else verify_ssl
        else:
            resolved, resolved_verify = resolve_communities_base_url(testing=testing)
            self.communities_base_url = resolved
            self.verify_ssl = resolved_verify if verify_ssl is None else verify_ssl

        self.import_client = import_client or ImportClient(
            api_key,
            testing=testing,
            session=self.session,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def get_community(self, slug_or_id: str) -> dict[str, Any] | None:
        """Fetch a community by slug or UUID.

        Args:
            slug_or_id: Community slug or UUID.

        Returns:
            Community JSON dict, or ``None`` if not found (404).

        Raises:
            CommunityError: On unexpected HTTP or network errors.
        """
        url = f"{self.communities_base_url}/{slug_or_id}"
        try:
            response = self.session.get(
                url, headers=self._auth_headers(), verify=self.verify_ssl
            )
        except requests.exceptions.RequestException as exc:
            raise CommunityError(
                f"Failed to fetch community {slug_or_id!r}: {exc}"
            ) from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise CommunityError(
                f"Failed to fetch community {slug_or_id!r} "
                f"(HTTP {response.status_code}): {response.text}"
            )
        return response.json()

    def create_community(self, slug: str, name: str) -> dict[str, Any]:
        """Create a community owned by the authenticated user.

        Args:
            slug: URL slug for the new community.
            name: Human-readable title.

        Returns:
            Created community JSON dict.

        Raises:
            CommunityError: On create failure.
        """
        payload = {
            "slug": slug,
            "metadata": {"title": name},
            "access": dict(DEFAULT_COMMUNITY_ACCESS),
        }
        try:
            response = self.session.post(
                self.communities_base_url,
                headers=self._auth_headers(),
                json=payload,
                verify=self.verify_ssl,
            )
        except requests.exceptions.RequestException as exc:
            raise CommunityError(f"Failed to create community {slug!r}: {exc}") from exc

        if response.status_code not in (200, 201):
            raise CommunityError(
                f"Failed to create community {slug!r} "
                f"(HTTP {response.status_code}): {response.text}"
            )

        community = response.json()
        self.log(f"  Created collection {slug!r} (id={community.get('id')})")
        return community

    def ensure_community(self, slug: str, name: str) -> dict[str, Any]:
        """Return an existing community by slug, or create it.

        Args:
            slug: Collection slug.
            name: Collection title (used only when creating).

        Returns:
            Community JSON dict.
        """
        existing = self.get_community(slug)
        if existing is not None:
            self.log(
                f"  Collection {slug!r} already exists (id={existing.get('id')})"
            )
            return existing
        return self.create_community(slug, name)

    def enable_children(self, community: dict[str, Any]) -> dict[str, Any]:
        """Ensure ``children.allow`` is true on a parent community.

        Args:
            community: Current community JSON (from a prior GET/create).

        Returns:
            Updated community JSON (or the original if already allowed).

        Raises:
            CommunityError: On update failure.
        """
        if community.get("children", {}).get("allow"):
            return community

        slug = community.get("slug") or community.get("id")
        url = f"{self.communities_base_url}/{community['id']}"

        fresh = self.get_community(community["id"])
        if fresh is None:
            raise CommunityError(
                f"Community disappeared before enable-children: {slug!r}"
            )

        payload: dict[str, Any] = {
            "slug": fresh["slug"],
            "metadata": fresh["metadata"],
            "access": fresh["access"],
            "children": {"allow": True},
        }
        if "custom_fields" in fresh:
            payload["custom_fields"] = fresh["custom_fields"]

        headers = self._auth_headers()
        revision = fresh.get("revision_id")
        if revision is not None:
            headers["If-Match"] = str(revision)

        try:
            response = self.session.put(
                url, headers=headers, json=payload, verify=self.verify_ssl
            )
        except requests.exceptions.RequestException as exc:
            raise CommunityError(
                f"Failed to enable children on {slug!r}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise CommunityError(
                f"Failed to enable children on {slug!r} "
                f"(HTTP {response.status_code}): {response.text}"
            )

        self.log(f"  Enabled children.allow on {slug!r}")
        return response.json()

    def assign_parent(
        self,
        child: dict[str, Any],
        parent: dict[str, Any],
    ) -> None:
        """Link a child community under a parent via join-request.

        Args:
            child: Child community JSON.
            parent: Parent community JSON (must already allow children).

        Raises:
            CommunityError: On request failure or conflicting parent.
        """
        child_slug = child.get("slug") or child.get("id")
        parent_slug = parent.get("slug") or parent.get("id")

        existing_parent = child.get("parent") or {}
        existing_id = existing_parent.get("id")
        if existing_id and str(existing_id) == str(parent["id"]):
            self.log(
                f"  {child_slug!r} already linked under {parent_slug!r}; skipping"
            )
            return
        if existing_id:
            raise CommunityError(
                f"Collection {child_slug!r} already has a different parent "
                f"({existing_parent.get('slug') or existing_id}). "
                "Clear or change the parent manually before re-assigning."
            )

        url = f"{self.communities_base_url}/{parent['id']}/actions/join-request"
        payload = {"community_id": str(child["id"])}

        try:
            response = self.session.post(
                url,
                headers=self._auth_headers(),
                json=payload,
                verify=self.verify_ssl,
            )
        except requests.exceptions.RequestException as exc:
            raise CommunityError(
                f"Failed to request parent link {child_slug!r} → {parent_slug!r}: "
                f"{exc}"
            ) from exc

        if response.status_code not in (200, 201):
            raise CommunityError(
                f"Failed to link {child_slug!r} under {parent_slug!r} "
                f"(HTTP {response.status_code}): {response.text}"
            )

        result = response.json()
        status = result.get("status")
        if status == "accepted":
            self.log(f"  Linked {child_slug!r} under {parent_slug!r} (auto-accepted)")
        else:
            self.log(
                f"  Submitted join-request for {child_slug!r} → {parent_slug!r} "
                f"(status={status!r}). Accept it in the parent collection's "
                "Requests inbox if it was not auto-accepted."
            )

    @staticmethod
    def resolve_path(path_value: str, manifest_dir: Path) -> str:
        """Resolve a path relative to the manifest file's directory if needed."""
        path = Path(path_value)
        if not path.is_absolute():
            path = manifest_dir / path
        return str(path.resolve())

    @staticmethod
    def normalize_files(
        files_value: Any, manifest_dir: Path, slug: str
    ) -> list[str]:
        """Normalize and validate the files field from a manifest entry.

        Args:
            files_value: String path or list of paths from the manifest.
            manifest_dir: Directory containing the manifest.
            slug: Collection slug (for error messages).

        Returns:
            List of absolute file paths.

        Raises:
            ManifestError: If paths are missing or invalid.
        """
        if files_value is None:
            return []
        if isinstance(files_value, str):
            paths = [files_value]
        elif isinstance(files_value, list):
            paths = files_value
        else:
            raise ManifestError(
                f"Invalid 'files' for {slug!r}. "
                "Expected a string path or a list of paths."
            )

        resolved: list[str] = []
        for path in paths:
            if not isinstance(path, str):
                raise ManifestError(f"Invalid file path in entry {slug!r}: {path!r}")
            abs_path = MultiCollectionImporter.resolve_path(path, manifest_dir)
            if not os.path.isfile(abs_path):
                raise ManifestError(f"File not found for {slug!r}: {abs_path}")
            resolved.append(abs_path)
        return resolved

    @staticmethod
    def entry_notify_owners(entry: dict[str, Any], default: bool) -> bool:
        """Resolve notify flag: per-entry override, else run-wide default."""
        if "notify_record_owners" not in entry:
            return default
        return coerce_bool(entry["notify_record_owners"], default=default)

    @staticmethod
    def entry_id_scheme(entry: dict[str, Any], default: str) -> str:
        """Resolve id_scheme: per-entry override, else run-wide default."""
        value = entry.get("id_scheme")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default or "import-recid"

    @staticmethod
    def entry_alternate_id_scheme(entry: dict[str, Any], default: str) -> str:
        """Resolve alternate_id_scheme: per-entry override, else run-wide default."""
        if "alternate_id_scheme" in entry:
            value = entry.get("alternate_id_scheme")
            return value.strip() if isinstance(value, str) else ""
        return default or ""

    @staticmethod
    def entry_no_updates(entry: dict[str, Any], default: bool) -> bool:
        """Resolve no_updates: per-entry override, else run-wide default."""
        if "no_updates" not in entry:
            return default
        return coerce_bool(entry["no_updates"], default=default)

    def import_collection(
        self,
        slug: str,
        metadata_path: str,
        files_paths: list[str],
        *,
        notify_owners: bool = False,
        id_scheme: str = "import-recid",
        alternate_id_scheme: str = "",
        no_updates: bool = False,
        progress: ProgressCallback | None = None,
        output_path: str | None = None,
    ) -> ImportResult:
        """Import one record batch into a single collection.

        Args:
            slug: Target collection slug.
            metadata_path: Path to metadata JSON.
            files_paths: Paths to files / zip archive.
            notify_owners: Forwarded to the import client.
            id_scheme: Forwarded to the import client.
            alternate_id_scheme: Forwarded to the import client.
            no_updates: Forwarded to the import client.
            progress: Optional progress callback.
            output_path: Optional path to write the response JSON/text.

        Returns:
            :class:`ImportResult` from the import client.
        """
        self.log(f"\n--- Importing records into {slug!r} ---")
        result = self.import_client.import_works(
            slug,
            metadata_path,
            files_paths,
            notify_owners=notify_owners,
            id_scheme=id_scheme,
            alternate_id_scheme=alternate_id_scheme,
            no_updates=no_updates,
            progress=progress,
        )
        if output_path:
            with open(output_path, "w", encoding="utf-8") as handle:
                if isinstance(result.body, dict):
                    json.dump(result.body, handle, indent=2)
                else:
                    handle.write(result.body if result.body is not None else "")
        return result

    def run_manifest(
        self,
        manifest_path: str | Path,
        *,
        assign_parents: bool = False,
        notify_owners: bool = False,
        id_scheme: str = "import-recid",
        alternate_id_scheme: str = "",
        no_updates: bool = False,
        progress: ProgressCallback | None = None,
    ) -> MultiCollectionImportResult:
        """Run the multi-collection import from a manifest.

        Args:
            manifest_path: Path to JSON/YAML manifest.
            assign_parents: When True, create parent/child links for entries
                that list ``parent_slug``.
            notify_owners: Default notify flag for entries that do not set
                ``notify_record_owners``.
            id_scheme: Default import dedupe scheme.
            alternate_id_scheme: Default secondary scheme.
            no_updates: Default no-updates flag.
            progress: Optional progress callback for each import POST.

        Returns:
            :class:`MultiCollectionImportResult`.

        Raises:
            ManifestError: Invalid or incomplete manifest / paths.
            CommunityError: Communities API failures.
        """
        manifest_path = str(manifest_path)
        manifest_dir = Path(manifest_path).resolve().parent
        entries = load_manifest(manifest_path)
        ordered = topological_order(entries)

        self.log("")
        self.log("=" * 70)
        self.log(f"Manifest: {manifest_path}")
        self.log(f"Collections: {len(ordered)}")
        self.log(f"Assign parents: {'yes' if assign_parents else 'no'}")
        self.log(
            f"Environment: {'Testing (localhost)' if self.testing else 'Production'}"
        )
        self.log(
            f"Notify record owners (default): "
            f"{'yes' if notify_owners else 'no'}"
        )
        self.log(f"Import id scheme (default): {id_scheme}")
        if alternate_id_scheme:
            self.log(f"Alternate id scheme (default): {alternate_id_scheme}")
        self.log(f"No-updates (default): {'yes' if no_updates else 'no'}")
        self.log("=" * 70)

        outcome = MultiCollectionImportResult()
        self.log("\n=== Ensuring collections exist ===")
        for entry in ordered:
            slug = entry["slug"]
            outcome.communities[slug] = self.ensure_community(slug, entry["name"])

        if assign_parents:
            self.log("\n=== Assigning parent/child links ===")
            for entry in ordered:
                parent_slug = entry.get("parent_slug")
                if not parent_slug:
                    continue
                child = outcome.communities[entry["slug"]]
                parent = outcome.communities.get(parent_slug)
                if parent is None:
                    parent = self.get_community(parent_slug)
                    if parent is None:
                        raise ManifestError(
                            f"Parent collection {parent_slug!r} not found for "
                            f"child {entry['slug']!r}. "
                            "Add the parent to the manifest or create it first."
                        )
                    outcome.communities[parent_slug] = parent
                parent = self.enable_children(parent)
                outcome.communities[parent_slug] = parent
                refreshed = self.get_community(child["id"])
                if refreshed is not None:
                    child = refreshed
                    outcome.communities[entry["slug"]] = child
                self.assign_parent(child, parent)

        self.log("\n=== Importing records ===")
        for entry in ordered:
            metadata = entry.get("metadata")
            files = entry.get("files")
            if not metadata and not files:
                self.log(
                    f"  Skipping import for {entry['slug']!r} "
                    "(no metadata/files in manifest)"
                )
                outcome.skipped.append(entry["slug"])
                continue
            if not metadata:
                raise ManifestError(
                    f"Entry {entry['slug']!r} has files but no metadata path."
                )
            if not files:
                raise ManifestError(
                    f"Entry {entry['slug']!r} has metadata but no files path(s)."
                )

            metadata_path = self.resolve_path(str(metadata), manifest_dir)
            if not os.path.isfile(metadata_path):
                raise ManifestError(
                    f"Metadata file not found for {entry['slug']!r}: {metadata_path}"
                )

            files_paths = self.normalize_files(files, manifest_dir, entry["slug"])
            output_path = entry.get("output")
            if output_path:
                output_path = self.resolve_path(str(output_path), manifest_dir)
                out_dir = os.path.dirname(output_path)
                if out_dir and not os.path.isdir(out_dir):
                    raise ManifestError(f"Output directory does not exist: {out_dir}")

            result = self.import_collection(
                entry["slug"],
                metadata_path,
                files_paths,
                notify_owners=self.entry_notify_owners(entry, notify_owners),
                id_scheme=self.entry_id_scheme(entry, id_scheme),
                alternate_id_scheme=self.entry_alternate_id_scheme(
                    entry, alternate_id_scheme
                ),
                no_updates=self.entry_no_updates(entry, no_updates),
                progress=progress,
                output_path=output_path,
            )
            outcome.imports[entry["slug"]] = result
            if not result.ok:
                self.log(f"⚠ Import for {entry['slug']!r} reported failure")

        self.log("")
        self.log("=" * 70)
        if outcome.ok:
            self.log("✓ Multi-collection import finished successfully")
        else:
            self.log("⚠ Multi-collection import finished with one or more failures")
        self.log("=" * 70)
        return outcome

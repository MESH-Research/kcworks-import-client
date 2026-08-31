#!/usr/bin/env python3
r"""Import works to a KCWorks collection via the import API.

Command-line interface and compatibility wrappers around
:class:`~kcworks_import_client.client.ImportClient`.

For library use::

    from kcworks_import_client import ImportClient

    client = ImportClient(api_key="...")
    result = client.import_works("my-collection", metadata=[...], files=["a.pdf"])

Command-Line Arguments:
    --api-key KEY
        API key for authentication. If not provided, checks KCWORKS_IMPORT_API_KEY
        environment variable, or prompts interactively.

    --collection-id ID
        Collection ID or slug to import records into. If not provided, checks
        KCWORKS_IMPORT_COLLECTION_ID environment variable, or prompts interactively.

    --metadata PATH
        Path to the metadata JSON file. The metadata must be a JSON array of metadata
        objects, even if importing a single record. See the API documentation for
        the complete metadata schema. If not provided, checks
        KCWORKS_IMPORT_METADATA_PATH environment variable, or prompts interactively.

    --files PATH [PATH ...]
        One or more file paths to upload with the records. Multiple files can be
        specified by providing multiple arguments. If not provided, checks
        KCWORKS_IMPORT_FILES_PATH environment variable (comma or space-separated),
        or prompts interactively.

    --output PATH
        Optional path to save the API response as JSON. If not provided, checks
        KCWORKS_IMPORT_OUTPUT_PATH environment variable, or prompts interactively
        (can be skipped by pressing Enter).

    --notify-record-owners
        Enable email notification of users designated as record owners.
        (Defaults to False)

    --id-scheme SCHEME
        Identifier scheme used for import deduplication (form field
        ``id_scheme``). Default: ``import-recid``. The scheme must already be
        defined in KCWorks (``RDM_RECORDS_IDENTIFIERS_SCHEMES``), or arranged
        with the KCWorks team for addition before import.

    --alternate-id-scheme SCHEME
        Optional secondary scheme for deduplication (form field
        ``alternate_id_scheme``). Same constraint as ``--id-scheme``.

    --no-updates
        Refuse to change an existing matched record when metadata differs
        (file handling is skipped in that case). Default is to allow
        metadata updates; files are then reconciled by filename and size
        (same key+size kept; changed size or new keys uploaded; removed
        keys deleted). See the import API docs for details.

Environment Variables:
    KCWORKS_IMPORT_API_KEY
        API key for authentication (alternative to --api-key)

    KCWORKS_IMPORT_COLLECTION_ID
        Collection ID or slug (alternative to --collection-id)

    KCWORKS_IMPORT_METADATA_PATH
        Path to metadata JSON file (alternative to --metadata)

    KCWORKS_IMPORT_FILES_PATH
        File paths, comma or space-separated (alternative to --files)

    KCWORKS_IMPORT_OUTPUT_PATH
        Path to save response JSON (alternative to --output)

    KCWORKS_IMPORT_API_URL
        Override the import API base URL (e.g. http://127.0.0.1:8000/api/import).
        Used for testing. When set, SSL verification is disabled.

Usage Examples:
    # After: pip install -e site/kcworks/dependencies/kcworks-import-client
    kcworks-api-importer \\
        --api-key "your-api-key" \\
        --collection-id "my-collection" \\
        --metadata "metadata.json" \\
        --files "file1.pdf" "file2.docx" \\
        --output "response.json"

    python -m kcworks_import_client.api_importer --help

Documentation:
    https://mesh-research.github.io/knowledge-commons-works/reference/api.html

Exit Codes:
    0 - Success
    1 - Error (invalid input, file not found, API error, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from typing import Any, Optional

# Check Python version (match KCWorks project requirement)
if sys.version_info < (3, 12):  # noqa: PLR2004, SIM108
    print(
        "Error: This script requires Python 3.12 or later. "
        f"Current version: {sys.version}",
        file=sys.stderr,
    )
    sys.exit(1)

from .client import ImportClient, guess_mime_type
from .exceptions import ImportRequestError
from .results import ImportResult

# Back-compat alias used by older call sites / tests.
_get_mime_type = guess_mime_type


def _get_api_key(args: argparse.Namespace) -> str:
    """Get API key for authentication with KCWorks.

    Args:
        args: Parsed command-line arguments.

    Returns:
        API key string.

    Exits:
        SystemExit: If API key cannot be obtained from any source.
    """
    if args.api_key:
        return str(args.api_key)

    api_key = os.getenv("KCWORKS_IMPORT_API_KEY")
    if api_key:
        assert isinstance(api_key, str)
        return api_key

    api_key = input("Enter your KCWorks API key: ").strip()
    if not api_key:
        print("Error: API key is required.", file=sys.stderr)
        sys.exit(1)

    return api_key


def _get_collection_id(args: argparse.Namespace) -> str:
    """Get collection ID to which records will be imported.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Collection ID or slug string.

    Exits:
        SystemExit: If collection ID cannot be obtained from any source.
    """
    if args.collection_id:
        return str(args.collection_id)

    collection_id = os.getenv("KCWORKS_IMPORT_COLLECTION_ID")
    if collection_id:
        assert isinstance(collection_id, str)
        return collection_id

    collection_id = input("Enter the KCWorks collection ID for the import: ").strip()
    if not collection_id:
        print("Error: Collection ID is required.", file=sys.stderr)
        sys.exit(1)

    return collection_id


def _get_metadata_path(args: argparse.Namespace) -> str:
    """Get path to the metadata JSON file for the records to be imported.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Path to metadata JSON file.

    Exits:
        SystemExit: If metadata path cannot be obtained or is invalid.
    """
    if args.metadata:
        metadata_path: str = str(args.metadata)
    else:
        metadata_path_env = os.getenv("KCWORKS_IMPORT_METADATA_PATH")
        if metadata_path_env:
            metadata_path = metadata_path_env
        else:
            metadata_path = input("Enter the path to the metadata JSON file: ").strip()
            if not metadata_path:
                print("Error: Metadata path is required.", file=sys.stderr)
                sys.exit(1)

    if not os.path.exists(metadata_path):
        print(f"Error: Metadata path does not exist: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(metadata_path):
        print(f"Error: Metadata path is not a file: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    return metadata_path


def _get_files_paths(args: argparse.Namespace) -> list[str]:
    """Get paths to the files for the records to be imported.

    Args:
        args: Parsed command-line arguments.

    Returns:
        List of validated file paths.

    Exits:
        SystemExit: If file paths cannot be obtained or are invalid.
    """
    if args.files:
        files_paths = args.files
    else:
        files_path_env = os.getenv("KCWORKS_IMPORT_FILES_PATH")
        if files_path_env:
            files_paths = [p.strip() for p in files_path_env.replace(",", " ").split()]
        else:
            prompt = "Enter the path(s) to the files (space-separated): "
            files_input = input(prompt).strip()
            if not files_input:
                print("Error: At least one file path is required.", file=sys.stderr)
                sys.exit(1)
            files_paths = [p.strip() for p in files_input.split()]

    validated_paths = []
    for file_path in files_paths:
        if not os.path.exists(file_path):
            print(f"Error: File path does not exist: {file_path}", file=sys.stderr)
            sys.exit(1)

        if not os.path.isfile(file_path):
            print(f"Error: Path is not a file: {file_path}", file=sys.stderr)
            sys.exit(1)

        validated_paths.append(file_path)

    return validated_paths


def _get_output_path(args: argparse.Namespace) -> Optional[str]:  # noqa: UP007
    """Get optional path to save the response JSON.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Output file path, or None if not provided.

    Exits:
        SystemExit: If output directory does not exist.
    """
    if args.output:
        output_path: Optional[str] = str(args.output)  # noqa: UP007
    else:
        output_path_env = os.getenv("KCWORKS_IMPORT_OUTPUT_PATH")
        if output_path_env:
            output_path = output_path_env
        else:
            prompt = (
                "Enter the path to save the response JSON "
                "(optional, press Enter to skip): "
            )
            output_path = input(prompt).strip()
            if not output_path:
                return None

    if output_path:
        parent_dir = os.path.dirname(output_path)
        if parent_dir and not os.path.exists(parent_dir):
            error_msg = f"Error: Output directory does not exist: {parent_dir}"
            print(error_msg, file=sys.stderr)
            sys.exit(1)

    return output_path


def _format_response_message(response_json: dict[str, Any], status_code: int) -> str:
    """Format a human-readable message from the API response.

    Args:
        response_json: JSON response from the API as a dictionary.
        status_code: HTTP status code from the response.

    Returns:
        Formatted human-readable message string.
    """
    data = response_json.get("data", [])
    errors = response_json.get("errors", [])
    message = response_json.get("message", "")

    lines = []

    if status_code == 201:
        lines.append("")
        if data:
            lines.append(f"Successfully imported {len(data)} record(s):")
            for item in data:
                record_id = item.get("record_id", "N/A")
                record_url = item.get("record_url", "N/A")
                item_index = item.get("item_index", "N/A")
                lines.append(f"  • Record {item_index}: {record_id}")
                if record_url and record_url != "N/A":
                    lines.append(f"    URL: {record_url}")
        if message:
            lines.append("")
            lines.append(f"✓ {message}")
    elif status_code == 207:
        lines.append("⚠ Partial success - some records imported, some failed")
        lines.append("")
        if data:
            lines.append(f"Successfully imported {len(data)} record(s):")
            for item in data:
                record_id = item.get("record_id", "N/A")
                record_url = item.get("record_url", "N/A")
                item_index = item.get("item_index", "N/A")
                lines.append(f"  • Record {item_index}: {record_id}")
                if record_url and record_url != "N/A":
                    lines.append(f"    URL: {record_url}")
        if errors:
            lines.append("")
            lines.append(f"Failed to import {len(errors)} record(s):")
            for error_item in errors:
                item_index = error_item.get("item_index", "N/A")
                error_list = error_item.get("errors", [])
                lines.append(f"  • Record {item_index}:")
                for err in error_list:
                    if "field" in err and "message" in err:
                        lines.append(f"    - {err['field']}: {err['message']}")
                    elif "validation_error" in err:
                        val_err = err["validation_error"]
                        lines.append(f"    - Validation error: {val_err}")
                    elif "file upload failures" in err:
                        upload_errs = err["file upload failures"]
                        lines.append(f"    - File upload failures: {upload_errs}")
                    else:
                        lines.append(f"    - {err}")
        if message:
            lines.append("")
            lines.append(f"Message: {message}")
    elif status_code in (400, 403, 500):
        lines.append("✗ Import failed!")
        lines.append("")
        if status_code == 403:
            lines.append(
                "Error: Access denied. Your API key may not have the necessary"
            )
            lines.append("permissions for this collection.")
        elif status_code == 400:
            lines.append("Error: Bad request. The request was malformed or invalid.")
        elif status_code == 500:
            lines.append(
                "Error: Server error. The server encountered an error processing"
            )
            lines.append("your request.")

        if errors:
            lines.append("")
            lines.append(f"Failed to import {len(errors)} record(s):")
            for error_item in errors:
                item_index = error_item.get("item_index", "N/A")
                error_list = error_item.get("errors", [])
                lines.append(f"  • Record {item_index}:")
                for err in error_list:
                    if isinstance(err, dict):
                        if "field" in err and "message" in err:
                            lines.append(f"    - {err['field']}: {err['message']}")
                        elif "validation_error" in err:
                            val_err = err["validation_error"]
                            lines.append(f"    - Validation error: {val_err}")
                        elif "file upload failures" in err:
                            upload_errs = err["file upload failures"]
                            lines.append(f"    - File upload failures: {upload_errs}")
                        else:
                            lines.append(f"    - {err}")
                    else:
                        lines.append(f"    - {err}")
        if message:
            lines.append("")
            lines.append(f"Message: {message}")
    else:
        lines.append(f"Response status: {status_code}")
        if message:
            lines.append(f"Message: {message}")
        if data:
            lines.append(f"Successfully imported: {len(data)} record(s)")
        if errors:
            lines.append(f"Failed: {len(errors)} record(s)")

    return "\n".join(lines)


def _print_error(message: str, details: str | None = None) -> None:
    """Print formatted error message to stderr."""
    print("", file=sys.stderr)
    print("✗ ERROR", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print(f"  {message}", file=sys.stderr)
    if details:
        print(f"  Details: {details}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print("", file=sys.stderr)


def _cli_spinner_progress() -> tuple[Any, Any]:
    """Start a CLI spinner; return ``(progress_callback, stop_fn)``."""
    stop_spinner = threading.Event()

    def _run_spinner(
        stop: threading.Event, message: str = "Importing records..."
    ) -> None:
        chars = ["|", "/", "-", "\\"]
        i = 0
        while not stop.is_set():
            sys.stdout.write(f"\r{message} {chars[i % len(chars)]}")
            sys.stdout.flush()
            i += 1
            stop.wait(0.1)

    spinner_thread = threading.Thread(
        target=_run_spinner, args=(stop_spinner,), daemon=True
    )

    def progress(event: str) -> None:
        if event == "start":
            print(" ")
            spinner_thread.start()
        elif event == "done":
            stop_spinner.set()
            if spinner_thread.is_alive():
                spinner_thread.join()
            sys.stdout.write("\r" + " " * 30 + "\r")
            sys.stdout.flush()

    def stop() -> None:
        if not stop_spinner.is_set():
            progress("done")

    return progress, stop


def _present_import_result(
    result: ImportResult, output_path: str | None
) -> int:
    """Print a CLI result and optionally write ``output_path``.

    Returns:
        Exit code ``0`` or ``1``.
    """
    print("=" * 70)
    print("Import Result")
    print("=" * 70)

    if isinstance(result.body, dict):
        print(_format_response_message(result.body, result.status_code))
        if output_path:
            with open(output_path, "w", encoding="utf-8") as output_file:
                json.dump(result.body, output_file, indent=2)
            print(f"\nFull response saved to: {output_path}")
        return result.exit_code

    _print_error(
        f"Request failed with status {result.status_code}",
        result.body if isinstance(result.body, str) else None,
    )
    if output_path and isinstance(result.body, str):
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(result.body)
        print(f"\nResponse saved to: {output_path}")
    return 1


def import_works(
    api_key: str,
    collection_id: str,
    metadata_path: str,
    files_paths: list[str],
    output_path: Optional[str] = None,  # noqa: UP007
    testing: bool = False,
    notify_owners: bool = False,
    id_scheme: str = "import-recid",
    alternate_id_scheme: str = "",
    no_updates: bool = False,
) -> int:
    """Import works to the collection (CLI-compatible wrapper).

    Prefer :class:`~kcworks_import_client.client.ImportClient` in application
    code. This function keeps spinner/print/exit-code behavior for scripts.

    Args:
        api_key: API key for authentication.
        collection_id: Collection ID or slug to import into.
        metadata_path: Path to metadata JSON file.
        files_paths: List of file paths to upload.
        output_path: Optional path to save the response JSON.
        testing: Optional flag to use a local testing KCWorks instance
            instead of the production instance. (Defaults to False)
        notify_owners: Optional flag to enable email notification of
            users identified as record owners.
        id_scheme: Identifier scheme for import deduplication (default
            ``import-recid``). Must be a scheme already defined in KCWorks,
            or pre-arranged for addition.
        alternate_id_scheme: Optional secondary dedupe scheme.
        no_updates: When True, refuse to change an existing matched record
            if metadata differs (file handling is not reached). Default False
            (metadata updates allowed; files reconciled by filename and size).

    Returns:
        ``0`` on success (HTTP 201 or 207), ``1`` on failure.
    """
    client = ImportClient(api_key, testing=testing)
    progress, stop_spinner = _cli_spinner_progress()
    try:
        result = client.import_works(
            collection_id,
            metadata_path,
            files_paths,
            notify_owners=notify_owners,
            id_scheme=id_scheme,
            alternate_id_scheme=alternate_id_scheme,
            no_updates=no_updates,
            progress=progress,
        )
    except ImportRequestError as exc:
        stop_spinner()
        _print_error("✗ Request failed", str(exc))
        return 1
    except OSError as exc:
        stop_spinner()
        _print_error("✗ Request failed", str(exc))
        return 1
    finally:
        stop_spinner()

    return _present_import_result(result, output_path)


def _print_startup_info(
    collection_id: str,
    metadata_path: str,
    files_count: int = 0,
    testing: bool = False,
    notify_owners: bool = False,
    id_scheme: str = "import-recid",
    alternate_id_scheme: str = "",
    no_updates: bool = False,
) -> None:
    """Print startup configuration information."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append(f"Collection ID: {collection_id}")
    lines.append(f"Metadata file: {metadata_path}")
    lines.append(f"Files to upload: {files_count}")
    lines.append(f"Environment: {'Testing (localhost)' if testing else 'Production'}")
    lines.append(
        f"Notify record owners by email? {'No' if not notify_owners else 'Yes'}"
    )
    lines.append(f"Import id scheme: {id_scheme}")
    if alternate_id_scheme:
        lines.append(f"Alternate id scheme: {alternate_id_scheme}")
    lines.append(
        f"Block metadata updates on existing matches? "
        f"{'Yes' if no_updates else 'No'}"
    )
    lines.append("=" * 70)
    lines.append("")
    print("\n".join(lines))


def main() -> None:
    """Main entry point for the script.

    Parses command-line arguments, gathers required parameters, and executes
    the import operation.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("KCWorks API Import")
    lines.append("=" * 70)
    print("\n".join(lines))

    parser = argparse.ArgumentParser(description="Import works to a KCWorks collection")
    parser.add_argument(
        "--api-key",
        help="API key for authentication (or set KCWORKS_IMPORT_API_KEY env var)",
    )
    parser.add_argument(
        "--collection-id",
        help="Collection ID or slug (or set KCWORKS_IMPORT_COLLECTION_ID env var)",
    )
    parser.add_argument(
        "--metadata",
        help="Path to metadata JSON file (or set KCWORKS_IMPORT_METADATA_PATH env var)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Path(s) to file(s) to upload (can specify multiple files)",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional path to save the response JSON "
            "(or set KCWORKS_IMPORT_OUTPUT_PATH env var)"
        ),
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help=(
            "Optional flag to use a local testing KCWorks instance instead of "
            "the production instance. (Defaults to False)"
        ),
    )
    parser.add_argument(
        "--notify-record-owners",
        action="store_true",
        help=(
            "Optional flag to enable email notification of users designated as "
            "record owners. (Defaults to False)"
        ),
    )
    parser.add_argument(
        "--id-scheme",
        default="import-recid",
        help=(
            "Identifier scheme for import deduplication (default: import-recid). "
            "Must be defined in KCWorks or pre-arranged for addition."
        ),
    )
    parser.add_argument(
        "--alternate-id-scheme",
        default="",
        help=(
            "Optional secondary identifier scheme for deduplication. "
            "Must be defined in KCWorks or pre-arranged for addition."
        ),
    )
    parser.add_argument(
        "--no-updates",
        action="store_true",
        help=(
            "Refuse to change an existing matched record when metadata "
            "differs (skips file reconciliation in that case). Default is "
            "to allow metadata updates; files are reconciled by filename "
            "and size (see import API docs)."
        ),
    )

    args = parser.parse_args()

    api_key = _get_api_key(args)
    collection_id = _get_collection_id(args)
    metadata_path = _get_metadata_path(args)
    files_paths = _get_files_paths(args)
    output_path = _get_output_path(args)

    _print_startup_info(
        collection_id,
        metadata_path,
        files_count=len(files_paths),
        testing=args.testing,
        notify_owners=args.notify_record_owners,
        id_scheme=args.id_scheme,
        alternate_id_scheme=args.alternate_id_scheme,
        no_updates=args.no_updates,
    )

    exit_code = import_works(
        api_key,
        collection_id,
        metadata_path,
        files_paths,
        output_path,
        args.testing,
        args.notify_record_owners,
        id_scheme=args.id_scheme,
        alternate_id_scheme=args.alternate_id_scheme,
        no_updates=args.no_updates,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

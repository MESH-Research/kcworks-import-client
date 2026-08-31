# Single-collection CLI

(kcworks-api-importer-script)=

The `kcworks-api-importer` command (module
`kcworks_import_client.api_importer`) handles authentication, file uploads,
multipart form encoding, and human-readable success/error messages for a
**single** collection.

For embedding in applications, use {doc}`library` instead.

## Command-line arguments

| Argument | Description |
| --- | --- |
| `--api-key KEY` | API key. If omitted: `KCWORKS_IMPORT_API_KEY`, or interactive prompt. |
| `--collection-id ID` | Collection ID or slug. If omitted: `KCWORKS_IMPORT_COLLECTION_ID`, or prompt. |
| `--metadata PATH` | Path to metadata JSON (array of objects, even for one record). If omitted: `KCWORKS_IMPORT_METADATA_PATH`, or prompt. |
| `--files PATH [PATH ...]` | One or more file paths. If omitted: `KCWORKS_IMPORT_FILES_PATH` (comma/space-separated), or prompt. |
| `--output PATH` | Optional path to save the API response JSON. If omitted: `KCWORKS_IMPORT_OUTPUT_PATH`, or optional prompt. |
| `--testing` | Use a local testing instance (`https://localhost`). |
| `--notify-record-owners` | Email users listed as record owners. Default: off. |
| `--id-scheme SCHEME` | Import dedupe scheme (default: `import-recid`). Must be defined in KCWorks or pre-arranged. |
| `--alternate-id-scheme` | Optional secondary dedupe scheme. Same constraint as `--id-scheme`. |
| `--no-updates` | Refuse to change an existing matched record when **metadata** differs (skips file reconciliation in that case). Default: allow metadata updates; files follow filename+size rules on the server. |

## Environment variables

- `KCWORKS_IMPORT_API_KEY`
- `KCWORKS_IMPORT_COLLECTION_ID`
- `KCWORKS_IMPORT_METADATA_PATH`
- `KCWORKS_IMPORT_FILES_PATH`
- `KCWORKS_IMPORT_OUTPUT_PATH`
- `KCWORKS_IMPORT_API_URL` — override import API base (disables SSL verify)

## Usage examples

**Basic usage:**

```bash
kcworks-api-importer \
  --api-key "your-api-key" \
  --collection-id "my-collection" \
  --metadata "metadata.json" \
  --files "file1.pdf" "file2.docx" \
  --output "response.json"
```

**Environment variables:**

```bash
export KCWORKS_IMPORT_API_KEY="your-api-key"
export KCWORKS_IMPORT_COLLECTION_ID="my-collection"
export KCWORKS_IMPORT_METADATA_PATH="metadata.json"
export KCWORKS_IMPORT_FILES_PATH="file1.pdf file2.docx"
python -m kcworks_import_client.api_importer --output "response.json"
```

**Interactive mode:**

```bash
python -m kcworks_import_client.api_importer
```

## Response handling

- **Success (201)** — checkmark, record IDs, URLs
- **Partial success (207)** — warning plus successful and failed records
- **Failure (400, 403, 500)** — error summary and per-record details

If `--output` is set, the full response is written as JSON (or plain text if
not JSON).

## Exit codes

- `0` — Success (HTTP 201 or 207)
- `1` — Error (invalid input, missing files, API/transport failure, etc.)

## Server API details

Metadata shape, ownership fields, dedupe identifiers, and file reconciliation
when re-importing are defined by the KCWorks import HTTP API:

- [KCWorks API reference — Streamlined Import API](https://mesh-research.github.io/knowledge-commons-works/reference/api.html)

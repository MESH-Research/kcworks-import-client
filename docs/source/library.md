# Library API

Prefer the service classes for application code. The CLI-oriented
`import_works(...)` helper still exists for scripts: it prints status and
returns an exit code (`0` / `1`).

## ImportClient

```python
from kcworks_import_client import ImportClient

client = ImportClient(api_key="...")
result = client.import_works(
    "my-collection",
    metadata=[{"metadata": {"title": "Example"}}],  # path, JSON str, list, or dict
    files=["paper.pdf"],  # paths or (filename, fileobj[, mime]) tuples
    notify_owners=False,
    id_scheme="import-recid",
    alternate_id_scheme="",
    no_updates=False,
    progress=None,  # optional callable("start"|"done")
)

if result.ok:
    print(result.status_code, result.data, result.message)
else:
    print(result.status_code, result.errors)
```

### ImportClient constructor options

| Argument | Description |
| --- | --- |
| `api_key` | Bearer token (required). |
| `testing` | Use `https://localhost` when no URL env override is set. |
| `base_url` | Override import API base (no trailing slash). |
| `verify_ssl` | Override TLS verification. |
| `session` | Optional `requests.Session` for connection reuse. |

`KCWORKS_IMPORT_API_URL` (when set) overrides the base URL and disables SSL
verification — useful for local mock servers and tests.

### ImportClient results and errors

- **`ImportResult`** — `status_code`, `data`, `errors`, `message`, `body`,
  `ok` (True for HTTP 201 or 207), `exit_code`
- **`import_works_or_raise(...)`** — same as `import_works`, but raises
  `ImportAPIError` when `ok` is False
- **`ImportRequestError`** — transport / network failure before a usable
  response

## MultiCollectionImporter

```python
from kcworks_import_client import MultiCollectionImporter

importer = MultiCollectionImporter(api_key="...", log=print)
multi = importer.run_manifest(
    "manifest.json",
    assign_parents=True,
    notify_owners=False,
    id_scheme="import-recid",
    no_updates=False,
)
assert multi.ok
print(multi.communities, multi.imports, multi.skipped)
```

### MultiCollectionImporter constructor options

| Argument | Description |
| --- | --- |
| `api_key` | Bearer token (required). |
| `testing` | Localhost communities/import bases when no env override. |
| `import_client` | Optional preconfigured `ImportClient`. |
| `communities_base_url` | Override communities API base. |
| `verify_ssl` | Override TLS verification for communities calls. |
| `session` | Shared `requests.Session`. |
| `log` | Optional callback for progress lines (default: no-op). |

Environment overrides:

- `KCWORKS_IMPORT_API_URL` — import base; communities base is derived by
  replacing a trailing `/import` with `/communities`
- `KCWORKS_COMMUNITIES_API_URL` — communities base directly

### MultiCollectionImporter results and errors

- **`MultiCollectionImportResult`** — `communities`, `imports` (slug →
  `ImportResult`), `skipped`, `ok`, `exit_code`
- **`ManifestError`** — invalid or incomplete manifest / paths
- **`CommunityError`** — communities API failures

## Public exports

```python
from kcworks_import_client import (
    ImportClient,
    MultiCollectionImporter,
    ImportResult,
    MultiCollectionImportResult,
    import_works,  # CLI-compatible helper
    load_manifest,
    ImportAPIError,
    ImportRequestError,
    ManifestError,
    CommunityError,
    KCWorksImportError,
)
```

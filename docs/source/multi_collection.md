# Multi-collection CLI

(kcworks-multi-collection-importer-script)=

`kcworks-multi-collection-importer` (module
`kcworks_import_client.multi_collection_importer`) reads a JSON or YAML
**manifest**, creates any missing collections via the communities API,
optionally links parent/child collections, and then imports each batch with
the same logic as the single-collection importer.

Install with the `yaml` extra if you use YAML manifests:

```bash
pip install -e ".[yaml]"
```

For application code, prefer `MultiCollectionImporter` from {doc}`library`
(`run_manifest(...)`).

## Manifest format

YAML example:

```yaml
collections:
  - slug: my-university
    name: My University
    metadata: ./university/metadata.json
    files: ./university/files.zip
    output: ./university/response.json

  - slug: dept-history
    name: Department of History
    parent_slug: my-university
    metadata: ./history/metadata.json
    files:
      - ./history/a.pdf
      - ./history/b.pdf
    id_scheme: neh-recid
    notify_record_owners: true
```

Equivalent JSON:

```json
{
  "collections": [
    {
      "slug": "my-university",
      "name": "My University",
      "metadata": "./university/metadata.json",
      "files": "./university/files.zip",
      "output": "./university/response.json"
    },
    {
      "slug": "dept-history",
      "name": "Department of History",
      "parent_slug": "my-university",
      "metadata": "./history/metadata.json",
      "files": ["./history/a.pdf", "./history/b.pdf"],
      "id_scheme": "neh-recid",
      "notify_record_owners": true
    }
  ]
}
```

Relative paths are resolved against the manifest file's directory.

Each collection **slug** may appear only once per manifest (one create/link/import
batch). Duplicate slugs are not supported as multiple batches; later rows for
the same slug silently override earlier ones. For additional batches into the
same collection, use another manifest run or the single-collection importer.

### Optional per-entry fields

- `id_scheme` / `alternate_id_scheme` — override CLI defaults. Schemes must
  already be defined in KCWorks (`RDM_RECORDS_IDENTIFIERS_SCHEMES`), or
  arranged with the KCWorks team before import.
- `notify_record_owners` — `true`/`false`; overrides `--notify-record-owners`.
- `no_updates` — `true`/`false`; overrides `--no-updates`. Default allows
  metadata updates on existing matches (server reconciles files by filename
  and size).

## Parent / child links

With `--assign-parents`, entries that list `parent_slug` are linked under that
parent. The client:

1. Ensures the parent has `children.allow=true` (collection owners can set this
   on KCWorks).
2. Submits a subcommunity **join-request**. When the OAuth user owns both
   collections, the request is **auto-accepted**.

See the KCWorks operator guide:
[Collection hierarchy](https://mesh-research.github.io/knowledge-commons-works/admin_guide/collection_hierarchy.html).

## Command-line arguments

| Argument | Description |
| --- | --- |
| `--api-key KEY` | API key (or `KCWORKS_IMPORT_API_KEY`, or prompt). |
| `--manifest PATH` | JSON/YAML manifest (or `KCWORKS_IMPORT_MANIFEST_PATH`, or prompt). |
| `--assign-parents` | Create parent/child links for entries that list `parent_slug`. |
| `--testing` | Use local testing instance (`https://localhost`). |
| `--notify-record-owners` | Default notify flag for entries without `notify_record_owners`. |
| `--id-scheme SCHEME` | Default dedupe scheme (default: `import-recid`); overridable per entry. |
| `--alternate-id-scheme` | Default secondary scheme; overridable per entry. |
| `--no-updates` | Default block on metadata updates for existing matches; overridable per entry. |

## Environment variables

- `KCWORKS_IMPORT_API_KEY`
- `KCWORKS_IMPORT_MANIFEST_PATH`
- `KCWORKS_IMPORT_API_URL` — import base; communities base derived when set
- `KCWORKS_COMMUNITIES_API_URL` — communities base override

## Usage example

```bash
kcworks-multi-collection-importer \
  --api-key "your-api-key" \
  --manifest "import_manifest.yaml" \
  --assign-parents
```

# kcworks-import-client

Standalone Python client for importing works into [KCWorks](https://works.hcommons.org/) via the streamlined import API.

## Install

```bash
# From this package directory
uv pip install -e ".[yaml,tests]"

# Or with pip
pip install -e ".[yaml]"
```

YAML manifests for the multi-collection importer require the `yaml` extra (`PyYAML`).

## Commands

After install:

```bash
kcworks-api-importer \
  --api-key "your-api-key" \
  --collection-id "my-collection" \
  --metadata "metadata.json" \
  --files "file1.pdf" "file2.docx" \
  --output "response.json"

kcworks-multi-collection-importer \
  --api-key "your-api-key" \
  --manifest "import_manifest.yaml" \
  --assign-parents
```

Or as modules:

```bash
python -m kcworks_import_client.api_importer --help
python -m kcworks_import_client.multi_collection_importer --help
```

## Library use

```python
from kcworks_import_client import ImportClient, MultiCollectionImporter

client = ImportClient(api_key="...")
result = client.import_works(
    "my-collection",
    metadata=[{"metadata": {"title": "Example"}}],  # path, JSON str, list, or dict
    files=["file1.pdf"],  # paths or (filename, BinaryIO[, mime]) tuples
)
if result.ok:
    print(result.data)

importer = MultiCollectionImporter(api_key="...")
multi = importer.run_manifest("import_manifest.json", assign_parents=True)
assert multi.ok
```

The CLI-oriented `import_works(...)` helper remains available for scripts (prints
status and returns an exit code). Prefer `ImportClient` / `MultiCollectionImporter`
in applications.

## Documentation

Package docs (install, library API, CLIs):

```bash
pip install -e ".[docs]"
cd docs && make html
# open docs/build/index.html
```

Published site (after CI on `main`): https://mesh-research.github.io/kcworks-import-client/

Server-side import API (metadata, responses, file reconciliation):

- https://mesh-research.github.io/knowledge-commons-works/reference/api.html

## Tests

```bash
./run-tests.sh
```

The test runner installs `[tests]` extras in a local `.venv`, runs pytest, and prints
a coverage report for `kcworks_import_client` (`term-missing`).

To run pytest directly (after `uv pip install -e ".[tests]"`):

```bash
python -m pytest tests/ --cov=kcworks_import_client --cov-report=term-missing
```

## License

MIT — see `LICENSE`.

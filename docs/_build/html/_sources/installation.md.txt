# Installation

Requires **Python 3.12+** and the `requests` library.

## From this repository

```bash
pip install -e .
# or with uv:
uv pip install -e .
```

YAML manifests for the multi-collection importer need PyYAML:

```bash
pip install -e ".[yaml]"
```

For building these docs:

```bash
pip install -e ".[docs]"
```

## Console scripts

Installing the package registers:

- `kcworks-api-importer` — single-collection CLI
- `kcworks-multi-collection-importer` — manifest-driven multi-collection CLI

You can also run modules directly:

```bash
python -m kcworks_import_client.api_importer --help
python -m kcworks_import_client.multi_collection_importer --help
```

## Tests

```bash
./run-tests.sh
```

The runner installs `[tests]` into a local `.venv`, runs pytest, and prints
coverage for `kcworks_import_client`.

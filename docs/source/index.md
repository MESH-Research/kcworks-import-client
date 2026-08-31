# kcworks-import-client

Standalone Python client for importing works into
[KCWorks](https://works.hcommons.org/) via the streamlined import API.

```{toctree}
:maxdepth: 2

installation
library
cli
multi_collection
changelog
```

## What this package provides

- **`ImportClient`** — library API for single-collection imports (paths or
  in-memory metadata/files)
- **`MultiCollectionImporter`** — create collections from a manifest, optional
  parent/child links, then import each batch
- **CLI entry points** — `kcworks-api-importer` and
  `kcworks-multi-collection-importer`

Server-side import API semantics (metadata schema, ownership, file
reconciliation, HTTP responses) are documented in the
[KCWorks API reference](https://mesh-research.github.io/knowledge-commons-works/reference/api.html).

## Indices and tables

* {ref}`genindex`
* {ref}`search`

# Documentation

Sphinx documentation for **kcworks-import-client** (MyST Markdown + Furo),
aligned with the KCWorks / stats-dashboard docs toolchain.

## Building

```bash
# From the package root
pip install -e ".[docs]"
cd docs
make html
```

Output is written to `docs/build/` (HTML at the build root, matching the
parent KCWorks docs layout used by CI).

Live reload during editing:

```bash
cd docs
sphinx-autobuild source build
```

## Structure

| Path | Contents |
| --- | --- |
| `source/index.md` | Landing page and toctree |
| `source/installation.md` | Install, extras, tests |
| `source/library.md` | `ImportClient` / `MultiCollectionImporter` |
| `source/cli.md` | Single-collection CLI |
| `source/multi_collection.md` | Manifest CLI and schema |
| `source/changelog.md` | Package changelog |
| `source/conf.py` | Sphinx configuration |
| `Makefile` | `make html` |

## Deployment

GitHub Actions (`.github/workflows/documentation.yml`) builds docs on pushes
and pull requests to `main`, and deploys to the `gh-pages` branch on pushes to
`main`.

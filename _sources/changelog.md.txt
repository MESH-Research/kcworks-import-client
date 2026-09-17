# Changelog

## 0.2.0

- Add new flags --no-updates, --all-or-none, and --suppress-reports which are
  passed through to the API.
- Add separate timestamped report file output for each import job.

## 0.1.0

- Initial package layout: `ImportClient`, `MultiCollectionImporter`, CLI entry
  points `kcworks-api-importer` and `kcworks-multi-collection-importer`.
- Single- and multi-collection import against the KCWorks import and communities
  APIs.
- Manifest-driven collection creation, optional parent links, and per-entry
  overrides for `id_scheme`, `notify_record_owners`, and `no_updates`.

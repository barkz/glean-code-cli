# Test Harness

Notes on the test suite added during development of glean-code-cli. See [Running tests](../README.md#running-tests) for the user-facing instructions on how to run the tests.

All 604 tests pass. Here's what was added across the development passes:

`tests/test_commands_extended.py` (155 new tests) — covers all previously untested commands:

- `/status`, `/clear`, `/help`
- `/datasources.list` (all flag combinations), `/datasources.status`, `/indexing.rotate-token`
- `/autocomplete`, `/recommendations`, `/feedback`, `/entities.list`
- `/pins.delete`, `/collections.delete`
- `/shortcuts.list`, `/shortcuts.get`, `/shortcuts.create`, `/shortcuts.update`, `/shortcuts.delete` (full flag coverage)
- `/answers.list`, `/answers.get`, `/answers.create`, `/answers.update`, `/answers.delete` (int ID validation, arg passing)
- `/summarize` (by URL, by ID, query flag)
- `/verification.list`, `/verification.verify`, `/verification.remind` (flag passthrough, defaults)
- `/messages.get`, `/activity.report`, `/insights` (CSV export, all flags)
- `/scaffold` with `--output` flag, cancellation paths
- `_fmt_ts`, `_render_insights`, `_export_insights_csv`, `_print_datasource_status`, `Session.refresh_client`

`tests/test_client_extended.py` (31 new tests) — covers all new client methods and mock responses:

- Mock responses for all 19 new endpoints (`/unpin`, `/listshortcuts`, `/listanswers`, `/summarize`, `/insights`, etc.)
- `GleanClient` method bodies: correct paths, partial updates, optional fields, body construction

`tests/test_indexing_walk.py` (25 new tests) — covers the `--path` indexing helpers and command flow:

- `path_to_id`, `filename_to_title`, `mime_for_path` — slug, title, and extension detection
- `walk_files` — default include/exclude behaviour, `node_modules`/`.git`/`.DS_Store` filtering, `--max-bytes` skip, single-file root, missing-path errors, custom `--include` overrides
- `file_to_document` — Markdown/HTML body shape, view-URL prefix override, unsupported-extension rejection
- `/index.document --path` — synthesizes a `DocumentDefinition`, dry-run skips the API, directory-passed errors, missing-permissions errors, mutex with `--from-file`, mutex of `--public` and `--acl-from-file`
- `/index.bulk-documents --path` — folder walk produces a paged `BulkIndexDocumentsRequest`, `--include` filtering, dry-run, backward compat with `--from-file`

# Test Harness

Notes on the test suite added during development of glean-code-cli. See [Running tests](../README.md#running-tests) for the user-facing instructions on how to run the tests.

All 699 tests pass. Here's what was added across the development passes:

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

`tests/test_commands_extended.py` and `tests/test_client_extended.py` (33 new tests) — covers the Custom Metadata API surface:

- `GleanClient` methods `set_metadata_schema`, `get_metadata_schema`, `delete_metadata_schema`, `attach_metadata`, `detach_metadata` — correct HTTP methods (PUT/GET/DELETE), correct paths under `/rest/api/index`, body shape, indexing-token requirement
- `_mock_indexing_response` for `/custom-metadata/schema/{group}` (schema-shaped GET, ack-style PUT/DELETE) and `/document/{docId}/custom-metadata/{group}` (ack-style PUT/DELETE)
- `/metadata.set-schema` — required `--group`, mutual exclusion of `--from-file` and `--keys`, inline-key parsing (`name:TYPE[:skip]`), invalid-type rejection, `--dry-run` skip, no-token error, file-list-form parsing
- `/metadata.get-schema`, `/metadata.delete-schema` — required `--group`, no-token error, correct client-method invocation
- `/metadata.attach` — required `--doc-id` and `--group`, mutual exclusion of `--from-file` and `--values`, inline-value parsing, malformed-value rejection, `--dry-run` skip, no-token error
- `/metadata.detach` — required flags, no-token error, correct client-method invocation

`tests/test_mock_corpus.py` (35 new tests) — covers the fake corpus behind mock mode:

- Ranking — relevant document first, distinct top hits for distinct queries, match-all ordered by freshness, `--datasource` filtering, page padding when nothing matches, page-size cap
- Snippets and metadata — snippet drawn from the sentence matching the query, author and relative freshness on every result
- Placeholders — `{Q}` / `{Q+1}` / `{FY}` expansion, next quarter differs from current, no raw placeholders leak into results
- Cross-endpoint coherence — a `/search` result URL resolves through `/getdocuments` and `/summarize` to the same document, `/chat` citations track the question, `/getdocumentpermissions` owner is the document author, `/people` reads the roster
- Custom corpus files — `mock_corpus_path` and `GLEAN_MOCK_CORPUS` overrides (config wins), bare-array form, and `CorpusError` on a missing file, invalid JSON, a document with no title, or an empty document list

`tests/test_mcp.py` (9 new tests) — covers mock mode on the MCP server:

- `_build_client` — forces live mode whatever `mode` the config file carries (including `auto`), and switches to mock only when `GLEAN_MOCK` is set; truthy spellings (`1`, `true`, `yes`, `on`) accepted, everything else ignored
- Labelling — all four tools (`search`, `chat`, `list_agents`, `run_agent`) prefix their response with the `[MOCK MODE]` banner when serving fake data, including empty-result responses, and never in live mode
- Tool descriptions — every tool docstring names `GLEAN_MOCK`, so the warning reaches the agent before it calls anything

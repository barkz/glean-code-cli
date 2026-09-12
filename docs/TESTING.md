# Testing

## Running the tests

The test suite uses only the standard library (no mocking frameworks, no network calls).

```bash
python3 -m pytest tests/
```

Or without pytest:

```bash
python3 -m unittest discover tests/
```

On macOS, keep bytecode caches out of the working tree — Spotlight indexes stray `.pyc`
files, and they outrank the `Glean Code.app` launcher in `Cmd+Space`:

```bash
export PYTHONPYCACHEPREFIX="$HOME/.cache/python"
```

1,076 tests covering the client and every mock response, commands and dispatch, config, UI, auth, completion, help docs, the mock corpus, indexing-walk, scaffold, the installer, the MCP server, the flow mapper, the Pages site builder, and Glean Personal (text extraction, the index, the content graph, ranking explanations, local mode, and the local MCP tools).

## Development notes

Notes on the test suite added during development of glean-code-cli.

All 1,076 tests pass. Here's what was added across the development passes:

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

`tests/test_install.py` (10 new tests) — covers app-bundle ownership in the installer:

- `bundle_identifier` / `owns_bundle` — reads `CFBundleIdentifier` out of `Info.plist`; a missing bundle counts as ours (nothing to clobber), a foreign identifier and an unreadable or binary plist do not
- Refusal — `install_macos_app` exits rather than writing into a bundle it did not create, leaving that bundle's `Info.plist` byte-identical and creating no `Contents/Resources`
- Legacy cleanup — an old `Glean.app` is removed on install when we own it, and left alone when it belongs to another app
- Uninstall — removes our own bundle, and never deletes a foreign one (the regression that would have deleted a user's Glean Desktop install)
- The default `APP_DIR` is asserted **not** to be `Glean.app`

`tests/test_mcp.py` (9 new tests) — covers mock mode on the MCP server:

- `_build_client` — forces live mode whatever `mode` the config file carries (including `auto`), and switches to mock only when `GLEAN_MOCK` is set; truthy spellings (`1`, `true`, `yes`, `on`) accepted, everything else ignored
- Labelling — all four tools (`search`, `chat`, `list_agents`, `run_agent`) prefix their response with the `[MOCK MODE]` banner when serving fake data, including empty-result responses, and never in live mode
- Tool descriptions — every tool docstring names `GLEAN_MOCK`, so the warning reaches the agent before it calls anything

`tests/test_mcp_control.py` (36 new tests) — covers `/mcp` server control:

- Package diagnostics — reports the installed `mcp` version and whether it can actually run the server (v1 provides `mcp.server.fastmcp`; v2 does not)
- State file — roundtrip, unreadable-file tolerance, and clearing a stale entry when the recorded pid is dead or has been reused by another process
- `start` refusals — stdio (which needs a client on the other end), unknown transports, missing package, an incompatible v2 install named by version, and a second start while one is running
- `stop` — signals and clears state; a no-op when nothing is running
- Client config — the stdio command form and the URL form, both JSON-serialisable
- Defaults — loopback-only bind, non-stdio default transport, and tool names checked against `glean_mcp.py` itself
- Command dispatch — bare `/mcp` shows status, unknown subcommands and clients error, `--url` without a server errors, a non-numeric `--port` errors

Every test redirects the state and log paths at a temp directory, so `~/.gleancode/` is never touched.

`tests/test_flow.py` (58 new tests) — covers the flow mapper:

- Capture gating — the `flow_capture` key defaults to `mock`, so live tenant content is never recorded by accident; `on` records both modes and `off` records nothing
- Capture — chat turns, citations, and search snippets land in SQLite; a shared `chatId` is one session and a new one starts another; every row is tagged with instance and mode; a capture failure cannot break the API call
- Enrichment — document text is fetched, and comes from `/getdocuments` now that the mock returns a body
- Linking — identifier links are exact and score 1.0; two sessions with no shared wording connect through a document that mentions the other's subject in passing; link evidence is asserted to be specific rather than generic; links never cross an instance or mode partition
- Title anchoring — the scorer prefers a word from the other document's title over a rarer word that appears nowhere meaningful, which is what stops "across" and "percent" being offered as evidence
- Queries and purge — summary, collapsed, and single-session views are JSON-serialisable; purge is scoped to a partition or clears everything
- Rendering — the timeline is self-contained (no external references), well-formed HTML, badges mock data, renders connections with their evidence, and handles an empty database
- Command dispatch — bare `/flow` shows status, unknown subcommands error, and bad `--min-score` / `--limit` / `--docs` values are rejected
- Schema migration — a database written before `session_links` carried `to_doc` gains the column on open, keeps its existing rows, and can be reopened repeatedly without the migration running twice
- `/flow show` rendering — sessions hang off a vertical rail, documents are labelled with their datasource, and a connection branches off with both document titles, the shared evidence, and the session number it reaches
- Colour is decoration — with colour disabled the output contains no escape sequences and every structural glyph (`●─`, `│`, `├──◆`, `↓`, `▪`) is still present, so the shape survives being piped
- Width — no line exceeds the terminal width at 40, 58, 84, or 120 columns, with colour on and off. Measured on *visible* width, since ANSI escapes have zero display width and `len()` would pass a broken layout
- Ordering — informative links (`linked-document`) come before trivial ones (`shared-citation`) regardless of score, verified against a database built by running the same investigation twice; documents a thread returned to lead the list, and singly-cited ones keep citation order rather than being interleaved by rank
- Overflow — `--links` caps connections per session and counts the remainder, and both `--docs` and `--links` reject non-integers
- Datasource colours — known sources each get a distinct colour, lookup ignores case and padding, and an unknown source falls back to grey rather than borrowing a familiar source's colour

The module patches out the mock client's simulated 0.25s network latency; without that these 58 tests take 31 seconds instead of 2.

`tests/test_extract.py` (26 tests) — covers local text extraction:

- Registry — `INCLUDE_PATTERNS` is derived from `SUPPORTED_EXTS`, so the walker's globs cannot drift from what the extractor actually handles; an unsupported extension raises with the supported list in the message
- Normalisation — spaces and tabs collapse but paragraph breaks survive, because chunking splits on them; line endings normalise; an oversized document is truncated with a visible marker
- HTML — tags are stripped, `<script>` and `<style>` bodies are dropped rather than indexed, and `<title>` becomes the document title
- JSON — flattened to `key.path: value` lines so both halves are searchable; invalid JSON is indexed verbatim rather than discarded, since JSONL and truncated exports are still worth finding
- Office — every fixture is built with `zipfile` rather than committed as a binary, which keeps the repo text-only and documents exactly which parts of each format the extractor depends on. Word runs join within a paragraph and paragraphs stay separate; Excel reads shared strings, inline strings and sheet names; PowerPoint orders `slide2` before `slide10`, which lexicographic sorting would get wrong
- Failure modes — a file that is not a zip, malformed XML inside a valid zip, a missing `word/document.xml`, an out-of-range shared-string index, and an archive declaring more uncompressed content than the limit allows. Each raises `ExtractError` with a reason rather than crashing an index run
- Part ordering — sheet names and slide order resolve through each part's relationships, not filenames. A reordered workbook must not pair a real sheet name with another sheet's content, a moved slide must not be cited under its old number, and a workbook with no usable relationships must fall back to generic `Sheet N` labels rather than a confidently wrong name

`tests/test_personal.py` (163 tests) — covers Glean Personal:

- Schema — tables, `meta` versioning, `0600` permissions, and idempotent reopening
- FTS5 fallback — a forced-broken FTS5 schema exercises the plain-table path end to end: indexing, search and fetch all still work, and an existing database keeps the store it was built with even once FTS5 is available again, because switching would orphan every chunk
- Chunking — headings split sections, a heading with no body is still indexed, paragraphs pack up to the limit, and only an oversized paragraph falls through to sentence windowing with overlap. A single sentence longer than the limit is still cut
- Query building — bare terms become quoted prefix matches and a `"quoted span"` stays a phrase, so a stray `NEAR`, `OR`, `*` or `-x:y` in user text is data rather than FTS5 syntax
- Incremental indexing — a second run changes nothing; an edited file is re-read and its neighbours are not; a file touched but not changed is skipped on its content hash; `--reindex` forces a re-read; a deleted file leaves the index; filters persist across runs so a later bare re-index repeats them
- Skip reasons — oversized files, empty files, and a corrupt `.docx` are reported rather than crashing the run, and unsupported extensions are never matched in the first place
- Doc ids — two paths that slug to the same string are disambiguated
- Search — one row per document rather than per chunk, source filtering, limits, snippets forced to a single line (structured formats carry no sentence enders and would otherwise emit a whole multi-line chunk into an aligned layout)
- Content graph — related documents link and unrelated ones do not, evidence is stored and returned, a higher threshold yields fewer links, and re-linking replaces rather than accumulates
- Glean shapes — `/search`, `/chat`, `/autocomplete` and `/getdocuments` responses match the Client API's shapes, which is what lets every existing renderer draw them unchanged
- Local mode — routing, an explicit error for endpoints a folder of files cannot honestly answer, the Indexing API explaining itself *before* asking for a token it will never need, and an assertion that `urlopen` is never reached
- Commands — every `/personal` subcommand, bad flag values, the purge confirmation prompt in both directions, and `/mode local` on a populated and an empty index
- Graph scale — near-duplicate documents must link at full strength, and phrase pruning must be symmetric across documents. Both are regressions with a measured origin: a per-document rank cut left two real 20 KB decks that shared 1,495 phrases sharing none, scoring the strongest link in the corpus at 0.0. The symmetry test was verified to fail against the broken implementation before being kept
- `--explain` — matched and missed terms (including the porter-stemmed plural/singular case the re-derivation has to cover), passage counts as a real fraction of the document, tie grouping, score-ratio ordering, bar clamping at every ratio, sparse payloads, empty result sets, and that the default result carries **no** `explain` key so the Client API shape stays byte-compatible
- Response shapes — `/autocomplete` and `/getdocuments` are asserted against the *mock's* shape rather than a hand-written expectation, since the whole point of the local adapters is byte-compatibility with the Client API. Both originally diverged, and the original tests locked the divergence in
- Unicode — non-English content is searchable, and terms survive tokenisation intact rather than being mangled to ASCII fragments
- Fallback recall — a rare term stays reachable on a 391-chunk plain-store index even alongside a term that 130 other documents share. This needs the scan window, a prefilter covering every term, and rarity weighting all working together; each was broken independently
- Mode plumbing — indexing commands explain local mode rather than asking for a token that would not help, `--dry-run` still works with no credentials in any mode, and `/ask` falls back to the local pattern-matcher instead of advising `/login` from inside local mode

`tests/test_mcp.py` (56 tests, +17 for Glean Personal) — covers the four local MCP tools:

- Each tool's output carries the `[LOCAL INDEX]` banner, and an empty index names the command that fixes it
- The local tools never call the Glean client and are unaffected by `GLEAN_MOCK`, which governs the Glean-backed tools only — the local index has no fictional alternative to serve
- A corrupt database returns an error string rather than a traceback

The linking fixture deliberately uses five documents rather than two. With two, every shared phrase appears in every document, so IDF cannot distinguish "topically shared" from "common vocabulary" and nothing can score above the threshold — a property of IDF at that scale, not a bug worth distorting the scoring to hide.

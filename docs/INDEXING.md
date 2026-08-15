# Indexing API

Glean Code exposes 32 of the 37 documented Indexing API endpoints — read/debug, single-record writes, bulk uploads, and long-running process-all triggers. All Indexing-API commands require a separate indexing token (Client API tokens cannot reach `/api/index/v1`):

```text
/config set indexing_token <token-or-secure-ref>
```

The token can be a literal value or the secure reference `token.secure.indexing` (resolved from `$GLEAN_INDEXING_TOKEN` at request time — see [Secure tokens](SECURE_TOKENS.md)). Get a real token from your Glean admin UI (workspace settings → API tokens → Indexing).

## Read & debug

These are non-destructive lookups — start here when answering questions like "is this doc indexed?", "why can't user X see doc Y?", or "what's the upload count for datasource Z?"

| Command | Purpose |
| --- | --- |
| [`/datasources.status <name>`](COMMANDS.md#datasourcesstatus) | Full status for one datasource: visibility, counts, last 5 processing events |
| [`/datasources.config <name>`](COMMANDS.md#datasourcesconfig) | Live config: object types, ACL settings, trusted domains, icon URL |
| [`/datasources.list --with-status`](COMMANDS.md#datasourceslist) | All datasources with uploaded/indexed counts and coverage |
| [`/documents.status`](COMMANDS.md#documentsstatus) | Upload + indexing status for one document |
| [`/documents.count`](COMMANDS.md#documentscount) | Document count for a custom datasource |
| [`/users.count`](COMMANDS.md#userscount) | User count for a custom datasource |
| [`/documents.access`](COMMANDS.md#documentsaccess) | Whether a specific user has access to a specific document |
| [`/debug.document`](COMMANDS.md#debugdocument) | Per-doc debug payload (status + uploaded permissions) |
| [`/debug.documents`](COMMANDS.md#debugdocuments) | Bulk debug for many documents (`--from-file`) |
| [`/debug.user`](COMMANDS.md#debuguser) | Per-user debug payload (status + uploaded groups) |

```text
/datasources.config gdrive
/documents.access --datasource gdrive --object-type Article --id doc-1 --user alice@example.com
/debug.user gdrive alice@example.com
```

## Single-record write

Each write command takes a JSON request body via `--from-file`. Deletes use convenience flags. All accept `--version <n>` for optimistic concurrency.

| Command | Purpose |
| --- | --- |
| [`/index.document`](COMMANDS.md#indexdocument) | Index one document — supports `--path <file>` mode, see below |
| [`/index.delete-document`](COMMANDS.md#indexdelete-document) | Delete one document by id |
| [`/index.permissions`](COMMANDS.md#indexpermissions) | Update document ACL |
| [`/index.user`](COMMANDS.md#indexuser) | Index one user |
| [`/index.delete-user`](COMMANDS.md#indexdelete-user) | Delete one user |
| [`/index.group`](COMMANDS.md#indexgroup) | Index one group |
| [`/index.delete-group`](COMMANDS.md#indexdelete-group) | Delete one group |
| [`/index.membership`](COMMANDS.md#indexmembership) | Index one group membership |
| [`/index.delete-membership`](COMMANDS.md#indexdelete-membership) | Delete one group membership |

```text
/index.document --from-file ./doc.json
/index.document --path ./README.md --datasource custom1 --object-type Article --public
/index.delete-document --datasource gdrive --object-type Article --id doc-1
/index.permissions --from-file ./perms.json
```

## Indexing from local files (`--path`)

`/index.document` and `/index.bulk-documents` both accept `--path <file-or-dir>` as an alternative to `--from-file`. The CLI walks the path, builds DocumentDefinitions for you, and POSTs them. Pair with `--dry-run` to see exactly what would be sent.

| Flag | Purpose |
| --- | --- |
| `--path` | A file (single mode) or directory (bulk mode) |
| `--datasource` | Required. Datasource name applied to every walked file |
| `--object-type` | Required. e.g. `Article`, `Wiki` |
| `--public` | Make all docs world-readable. Mutually exclusive with `--acl-from-file` |
| `--acl-from-file` | JSON file with a `DocumentPermissionsDefinition` applied to every doc |
| `--include` | Comma-separated globs. Default: `*.txt,*.md,*.markdown,*.html,*.htm,*.json` |
| `--exclude` | Comma-separated globs. Default skips `.git`, `node_modules`, `__pycache__`, `.DS_Store` |
| `--max-bytes` | Skip files larger than this. Default 5 MB |
| `--id-prefix` | Prepended to the path-derived id slug (e.g. `--id-prefix proj` → `proj-team-onboarding`) |
| `--view-url-prefix` | Base URL prepended to relative paths. Defaults to `file://` per file |
| `--dry-run` | Print the assembled request body and exit without calling the API |

**Supported file types:** `.txt`, `.md`, `.markdown`, `.html`, `.htm`, `.json`. Binary formats (PDF, `.docx`, etc.) are out of scope for v1.

**Behaviour:**

- Path-derived ids: `team/onboarding.md` → `team-onboarding`. Stable across re-runs, debuggable, datasource-safe
- HTML files are sent as `htmlContent`; everything else as `textContent`
- Mock mode works for `--path` exactly like every other indexing command (token still required)
- `/index.document --path <dir>` errors and points you at `/index.bulk-documents` — single mode is single-file only
- The bulk command warns when more than 500 files are matched. v1 sends them in one POST; auto-paging across `isFirstPage`/`isLastPage` is planned for v2

```text
# Single Markdown file, public ACL, dry-run first
/index.document --path ./README.md \
                --datasource custom1 --object-type Article \
                --public --dry-run

# Walk a folder, only .md and .txt, with a fixed ACL from disk
/index.bulk-documents --path ./content/ \
                      --datasource custom1 --object-type Article \
                      --acl-from-file ./perms.json \
                      --include "*.md,*.txt" --exclude "**/draft/**"
```

## Bulk + paged uploads

Bulk endpoints use the standard upload-paging contract (`uploadId`, `isFirstPage`, `isLastPage`, optional `forceRestartUpload`). Wrap your full request body in a JSON file and pass it via `--from-file`. The documents-side commands also accept `--path` (see above).

| Command | Endpoint family |
| --- | --- |
| [`/index.documents`](COMMANDS.md#indexdocuments) | Paged document index |
| [`/index.bulk-documents`](COMMANDS.md#indexbulk-documents) | Bulk document index |
| [`/index.bulk-users`](COMMANDS.md#indexbulk-users) | Bulk user index |
| [`/index.bulk-groups`](COMMANDS.md#indexbulk-groups) | Bulk group index |
| [`/index.bulk-memberships`](COMMANDS.md#indexbulk-memberships) | Bulk group memberships |
| [`/people.bulk-employees`](COMMANDS.md#peoplebulk-employees) | Bulk employee records (org chart) |
| [`/people.bulk-teams`](COMMANDS.md#peoplebulk-teams) | Bulk team records (org chart) |
| [`/people.index-employee-list`](COMMANDS.md#peopleindex-employee-list) | Versioned employee list |
| [`/shortcuts.bulk-index`](COMMANDS.md#shortcutsbulk-index) | Bulk shortcuts via Indexing API ⚠ distinct from Client API `/shortcuts.*` |
| [`/shortcuts.upload`](COMMANDS.md#shortcutsupload) | Upload shortcuts via Indexing API |

## Process-all (long-running)

Trigger a tenant-wide reprocess after a bulk upload completes. These commands accept an optional `--datasource` filter where applicable.

| Command | Purpose |
| --- | --- |
| [`/index.process-all-documents`](COMMANDS.md#indexprocess-all-documents) | Reprocess all uploaded documents |
| [`/index.process-all-memberships`](COMMANDS.md#indexprocess-all-memberships) | Reprocess all uploaded memberships |
| [`/people.process-all-employees-teams`](COMMANDS.md#peopleprocess-all-employees-teams) | Reprocess all uploaded employees + teams |

## Token rotation

```text
/indexing.rotate-token
/config set indexing_token <new-raw-secret>
```

`/indexing.rotate-token` prints the new raw secret — store it immediately, the old one is invalidated.

## Mock mode for indexing

All 32 indexing commands work in mock mode as long as an indexing token is set in config — it can be any non-empty string (e.g. `mock_idx_token`). The CLI returns realistic shapes (datasource configs, doc/user counts, debug payloads, accept-style write responses) so you can rehearse a workflow before pointing at a live tenant.


## REST paths

See [REST_PATHS.md](REST_PATHS.md#indexing-api-paths) for the full list of Indexing API paths this client targets.

---

[← Back to README](../README.md) · [Command Reference](COMMANDS.md)

# API Incompatibility Report — glean-code-cli vs. Glean REST API

**Date:** 2026-08-15
**Scope:** every REST call made by `glean_code/client.py` — 40 Client API, 32 Indexing API, 5 Custom Metadata.

## Method

Diffed the client against Glean's published OpenAPI specifications rather than documentation prose:

- `https://gleanwork.github.io/open-api/specs/final/client_rest.yaml`
- `https://gleanwork.github.io/open-api/specs/final/indexing.yaml`

Both specs were parsed and every path, HTTP method, and required request field was compared to what the client actually sends. The notable findings were independently confirmed against the developer portal (`developers.glean.com/api/client-api/*/overview`).

## Summary

| Surface | Calls checked | Defects |
| --- | --- | --- |
| Client API | 40 | **12** |
| Indexing API | 32 | 0 (1 uncertain) |
| Custom Metadata API | 5 | 0 |

Seven defects are hard failures (404/405/400) in live mode. Five send malformed bodies. None are caught by the test suite — see [Why the tests pass](#why-the-tests-pass).

## Hard breaks — 404 / 405 / 400

| # | Command | Code sends | Spec says | Fails with | Location |
| --- | --- | --- | --- | --- | --- |
| 1 | `/docs.permissions` | `POST /getdocumentpermissions` body `{documentSpec:{id}}` | `POST /getdocpermissions` body `{documentId}` | 404 | `client.py:434` |
| 2 | `/announcements.list` | `POST /announcements/list` | **no list endpoint exists** | 404 | `client.py:449` |
| 3 | `/announcements.create` | `POST /announcements/create` | `POST /createannouncement` | 404 | `client.py:452` |
| 4 | `/announcements.delete` | `POST /announcements/delete` | `POST /deleteannouncement` | 404 | `client.py:459` |
| 5 | `/pins.create` | `POST /createpin` body `{url, query}` | `POST /pin` body `{documentId, queries[]}` | 404 | `client.py:474` |
| 6 | `/tools.list` | `POST /tools/list` | `GET /tools/list` + `toolNames` query param | 405 | `client.py:417` |
| 7 | `/tools.call` | body `{name, arguments}` | required `{name, parameters}` | 400 | `client.py:420` |

**#2 is not a rename.** Glean documents only create, update, and delete for announcements — there is no list or get endpoint. `/announcements.list` cannot be made to work as specified; it needs removing, or reimplementing on top of `/search`.

**#5 is not a rename either.** Beyond the path, the pin model is different: Glean pins a *document id* against one or more *queries*, while the client pins a *url* against a single *query*.

## Wrong request body — 400 or silently wrong results

| # | Command | Code sends | Spec requires | Location |
| --- | --- | --- | --- | --- |
| 8 | `/people.get` | `{email: "x@y.com"}` | `{emailIds: ["x@y.com"]}` | `client.py:444` |
| 9 | `/summarize` | `{documentSpec: {...}}` | `{documentSpecs: [{...}]}` — required | `client.py:552` |
| 10 | `/feedback` | `{trackingToken, category}` | `{event: <enum>, trackingTokens: [...]}` — both required | `client.py:401` |
| 11 | `/agents.run` | `{agentId, input: "str"}` | `{agent_id, input: {}}` — snake_case key, object value | `client.py:413` |
| 12 | `/agents.list` | `{query: "..."}` | `{name: "..."}` | `client.py:410` |

**#12 degrades silently.** The unknown field is ignored rather than rejected, so `/agents.list <query>` returns every agent unfiltered instead of erroring.

For **#10**, `event` is an enum (`CLICK`, `VIEW`, `UPVOTE`, `DOWNVOTE`, …) and `category` is a separate enum (`SEARCH`, `CHAT`, `ANSWERS`, …). The client currently passes its `rating` argument as `category`, which conflates the two.

## Minor

- **`/verification.list`** sends `count` in the request body; the spec defines `count` as a **query** parameter, so the limit is silently ignored.
- **`/insights`** sends `locale`, which is not a documented field. Documented fields are `overviewRequest`, `assistantRequest`, `agentsRequest`, `disablePerUserInsights`, `mcpRequest`, `mcpBreakdownRequest`. The last two are not exposed by the CLI at all.
- **`/people.index-employee-list`** → `/api/index/v1/indexemployeelist` appears in the indexing spec as an **empty path node** (`{}`) with no documented operation, though the `IndexEmployeeListRequest` schema (`{employees: [...]}`) still exists in `components`. It reads as withdrawn from the public surface. The body the client sends still matches the lingering schema, so live behavior is uncertain — verify against a real tenant before relying on it.

## Clean surfaces

- **Indexing API** — all 31 documented paths are correct, and every required field matches exactly: `datasource`+`user`, `datasource`+`groupName`, `datasource`+`objectType`+`docId`, `userEmail`, `debugDocuments`, and the `version` optimistic-concurrency field throughout.
- **Custom Metadata API** — all five paths, all HTTP methods (PUT/GET/DELETE), and the distinct `/rest/api/index` base URL are exact.
- **Client API** — `chat` (including `author`/`messageType` enum values and the `fragments` shape), `search`, `autocomplete`, `listentities`, `getdocuments`, collections, shortcuts, answers, `verify`, `addverificationreminder`, `messages`, `activity`, and the `insights` request body.

## Why the tests pass

`_mock_response` is keyed on the **same path strings** the live client posts to:

```text
client.py:722    if path == "/getdocumentpermissions":
client.py:736    if path == "/announcements/list":
client.py:752    if path == "/createpin":
```

Mock mode is self-consistent with the bug. All 699 tests pass while 12 commands would fail against a real tenant, because no test ever compares a path to the published spec.

**Consequence for any fix:** the path must change in *both* the client method and its `_mock_response` / `_mock_indexing_response` branch, or the tests will break in the opposite direction.

**Suggested guard:** a test that asserts every path string in `client.py` appears in the vendored OpenAPI spec would have caught all 12 defects and would prevent regressions. It requires checking in a copy of the two spec files, or a periodically refreshed path manifest.

## Documentation impact

`docs/REST_PATHS.md` publishes six of the incorrect paths as reference documentation:

- `/getdocumentpermissions`
- `/announcements/list`, `/announcements/create`, `/announcements/delete`
- `/createpin`
- `/tools/list` listed under POST

These need the same corrections as the code, otherwise the docs will contradict the fixed client.

## Recommended actions

**Mechanical — safe to apply now (items 1, 3–11):**

1. Rename the path in the `GleanClient` method.
2. Rename the matching branch in `_mock_response`.
3. Correct the request body key or shape.
4. Update `docs/REST_PATHS.md` and any `DOCS` entry in `help_docs.py` that names the endpoint.

**Needs a product decision first:**

- **Item 2 — `/announcements.list`.** No Glean endpoint backs it. Either remove the command (and its `DOCS` entry, mock branch, and tests), or reimplement it over `/search` filtered to announcements.
- **Item 12 — `/agents.list`.** Confirm the intended filter is agent *name*; if the goal was full-text search across agent descriptions, the API does not offer it and the flag should be documented as a name filter.

**Follow-up:**

- Verify item 15 (`/indexemployeelist`) against a live tenant, and prefer `/api/index/v1/bulkindexemployees` if it 404s.
- Consider the spec-conformance test described above.

## Uncovered endpoints

Not incompatibilities — documented endpoints the CLI does not expose, listed as roadmap input:

- **Chat management** — `listchats`, `getchat`, `deletechats`, `deleteallchats`, `uploadchatfiles`, `getchatfiles`
- **Agents CRUD** — `/agents`, `/agents/{id}`, `/agents/{id}/schemas`, `/agents/{id}/import`
- **Collection items** — `addcollectionitems`, `editcollectionitem`, `deletecollectionitem`, `getcollection`, `editcollection`
- **Pins** — `editpin`, `getpin`
- **Announcements** — `updateannouncement`
- **Search** — `getdocumentsbyfacets`, `adminsearch`, `feed`
- **Governance** — the full `/governance/*` policy, report, and findings-export suite
- **Indexing** — `adddatasource`, `betausers`, `indexemployee`, `deleteemployee`, `indexteam`, `deleteteam`, `debug/{datasource}/document/events`

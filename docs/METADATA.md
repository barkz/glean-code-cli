# Custom Metadata API

Glean's Custom Metadata API lets you attach independent structured metadata to any document already indexed in Glean — across native connectors, custom datasources, anything — without re-uploading the document. These commands hit `https://<instance>-be.glean.com/rest/api/index` (note: a different base path than the rest of the Indexing API).

The same `indexing_token` is reused; the token must carry one of:

- `custommetadata:<group_name>` — limits access to a single named group
- `custommetadata:global_scope` — manage schemas and metadata across any group

Generate the token through your standard indexing-token workflow with the appropriate scope, then point Glean Code at it via `/config set indexing_token <token-or-secure-ref>`.

## Schema management

Define which keys a metadata group accepts and what type each one holds (`TEXT`, `PICKLIST`, `TEXTLIST`, or `MULTIPICKLIST`). Schemas are versioned per group and replace the previous schema on each set.

| Command | Purpose |
| --- | --- |
| [`/metadata.set-schema`](COMMANDS.md#metadataset-schema) | Create or update a group's schema (inline `--keys` or `--from-file`) |
| [`/metadata.get-schema`](COMMANDS.md#metadataget-schema) | Fetch the current schema for a group |
| [`/metadata.delete-schema`](COMMANDS.md#metadatadelete-schema) | Delete a group's schema |

```text
/metadata.set-schema --group hr --keys department:PICKLIST,region:TEXT
/metadata.set-schema --group hr --from-file ./hr-schema.json --dry-run
/metadata.get-schema --group hr
/metadata.delete-schema --group hr
```

## Attaching metadata to documents

Attach (or replace) a set of `(key, value)` pairs on an indexed document for a given group. The PUT semantic replaces the **full** set for the `(docId, group)` pair — include every key you want preserved.

| Command | Purpose |
| --- | --- |
| [`/metadata.attach`](COMMANDS.md#metadataattach) | Attach or replace custom metadata on a document (inline `--values` or `--from-file`) |
| [`/metadata.detach`](COMMANDS.md#metadatadetach) | Remove all custom metadata for a `(document, group)` pair |

```text
/metadata.attach --doc-id ABC --group hr --values department=Engineering,region=US
/metadata.attach --doc-id ABC --group hr --from-file ./pairs.json
/metadata.detach --doc-id ABC --group hr
```

Use `--from-file` whenever any value is a `TEXTLIST` or `MULTIPICKLIST` array — `--values` is for simple `TEXT`/`PICKLIST` strings only.

## Querying

Custom metadata becomes searchable as soon as it's indexed. Use the standard search facet syntax `<groupName><keyName>:<value>` and include `CUSTOM_METADATA` in `includeFields` on `/search` to surface it in results. See the [Glean docs](https://developers.glean.com/api-info/indexing/custom-metadata/overview) for full querying details.

## Mock mode for custom metadata

All five `/metadata.*` commands work in mock mode (with any non-empty `indexing_token` configured): set/get schema, attach, and detach return realistic ack-style or schema-shaped responses so you can rehearse the flow before pointing at a live tenant.

---

## REST paths

See [REST_PATHS.md](REST_PATHS.md#custom-metadata-api-paths) for the full list of Custom Metadata paths this client targets.

---

[← Back to README](../README.md) · [Command Reference](COMMANDS.md)

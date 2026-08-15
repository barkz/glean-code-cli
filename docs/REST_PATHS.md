# Notes on the REST paths

## Client API paths

The client targets the documented Glean Client REST API at `https://<instance>-be.glean.com/rest/api/v1`. Paths used:

```text
POST /chat
POST /search
POST /autocomplete
POST /recommendations
POST /feedback
POST /agents/search
POST /agents/runs/wait
POST /agents/runs/stream
POST /tools/list
POST /tools/call
POST /getdocuments
POST /getdocumentpermissions
POST /listentities
POST /people
POST /announcements/list
POST /announcements/create
POST /announcements/delete
POST /listcollections
POST /createcollection
POST /listpins
POST /createpin
POST /unpin
POST /deletecollection
POST /listshortcuts
POST /getshortcut
POST /createshortcut
POST /updateshortcut
POST /deleteshortcut
POST /listanswers
POST /getanswer
POST /createanswer
POST /editanswer
POST /deleteanswer
POST /summarize
POST /listverifications
POST /verify
POST /addverificationreminder
POST /messages
POST /activity
POST /insights
```

## Indexing API paths

Require a separate indexing token. Base: `https://<instance>-be.glean.com/api/index/v1`.

```text
POST /api/index/v1/rotatetoken

# Read & debug
POST /api/index/v1/getdatasourceconfig
POST /api/index/v1/getdocumentstatus
POST /api/index/v1/getdocumentcount
POST /api/index/v1/getusercount
POST /api/index/v1/checkdocumentaccess
POST /api/index/v1/debug/{datasource}/status
POST /api/index/v1/debug/{datasource}/document
POST /api/index/v1/debug/{datasource}/documents
POST /api/index/v1/debug/{datasource}/user

# Single-record write
POST /api/index/v1/indexdocument
POST /api/index/v1/deletedocument
POST /api/index/v1/updatepermissions
POST /api/index/v1/indexuser
POST /api/index/v1/deleteuser
POST /api/index/v1/indexgroup
POST /api/index/v1/deletegroup
POST /api/index/v1/indexmembership
POST /api/index/v1/deletemembership

# Bulk / paged
POST /api/index/v1/indexdocuments
POST /api/index/v1/bulkindexdocuments
POST /api/index/v1/bulkindexusers
POST /api/index/v1/bulkindexgroups
POST /api/index/v1/bulkindexmemberships
POST /api/index/v1/bulkindexshortcuts
POST /api/index/v1/uploadshortcuts
POST /api/index/v1/bulkindexemployees
POST /api/index/v1/bulkindexteams
POST /api/index/v1/indexemployeelist

# Process-all (long running)
POST /api/index/v1/processalldocuments
POST /api/index/v1/processallmemberships
POST /api/index/v1/processallemployeesandteams
```

## Custom Metadata API paths

Require an indexing token scoped with `custommetadata:<group>` or `custommetadata:global_scope`. Base: `https://<instance>-be.glean.com/rest/api/index`.

```text
# Schema management
PUT    /rest/api/index/custom-metadata/schema/{groupName}
GET    /rest/api/index/custom-metadata/schema/{groupName}
DELETE /rest/api/index/custom-metadata/schema/{groupName}

# Document metadata
PUT    /rest/api/index/document/{docId}/custom-metadata/{groupName}
DELETE /rest/api/index/document/{docId}/custom-metadata/{groupName}
```

If your tenant uses a slightly different path for a given surface, change it in `glean_code/client.py`. Every method is a small wrapper around `self._post(path, body)` so the swap is a one-liner.

## JSON arguments in `/tools.call`

Wrap the JSON in single quotes so the shell parser leaves the double quotes intact:

```text
/tools.call search '{"query":"pto policy"}'
```

---

[← Back to README](../README.md) · [Command Reference](COMMANDS.md)

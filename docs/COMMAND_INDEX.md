# Command index

Every command, grouped by surface.

| Area | Commands |
| --- | --- |
| Shell | `/help` `/status` `/doctor` `/auth` `/login` `/logout` `/open` `/ask` `/config` `/mode` `/mcp` `/flow` `/history` `/clear` `/exit` |
| Chat and search | `/chat` `/search` `/autocomplete` `/recommendations` `/feedback` `/datasources.list` |
| Glean Personal | `/personal index` `/personal search` `/personal status` `/personal sources` `/personal show` `/personal related` `/personal link` `/personal purge` |
| Indexing — read & debug | `/datasources.status` `/datasources.config` `/documents.status` `/documents.count` `/users.count` `/documents.access` `/debug.document` `/debug.documents` `/debug.user` `/indexing.rotate-token` |
| Indexing — single write | `/index.document` `/index.permissions` `/index.user` `/index.group` `/index.membership` and their `/index.delete-*` partners |
| Indexing — bulk & process-all | `/index.documents` `/index.bulk-documents` `/index.bulk-users` `/index.bulk-groups` `/index.bulk-memberships` `/shortcuts.bulk-index` `/shortcuts.upload` `/index.process-all-documents` `/index.process-all-memberships` |
| Indexing — people (org chart) | `/people.bulk-employees` `/people.bulk-teams` `/people.index-employee-list` `/people.process-all-employees-teams` |
| Custom metadata | `/metadata.set-schema` `/metadata.get-schema` `/metadata.delete-schema` `/metadata.attach` `/metadata.detach` |
| Insights & activity | `/insights` `/activity.report` |
| Agents and tools | `/agents.list` `/agents.run` `/tools.list` `/tools.call` |
| Docs and people | `/docs.get` `/docs.permissions` `/entities.list` `/people.get` |
| Announcements, collections, pins | `/announcements.list` `/announcements.create` `/announcements.delete` `/collections.list` `/collections.create` `/collections.delete` `/pins.list` `/pins.create` `/pins.delete` |
| Shortcuts (Go Links) | `/shortcuts.list` `/shortcuts.get` `/shortcuts.create` `/shortcuts.update` `/shortcuts.delete` |
| Answers | `/answers.list` `/answers.get` `/answers.create` `/answers.update` `/answers.delete` |
| Verification | `/verification.list` `/verification.verify` `/verification.remind` |
| Summarize & messages | `/summarize` `/messages.get` |
| Scaffold | `/scaffold chat` `/scaffold search` `/scaffold agent` |

Bare text with no leading slash is a shortcut for `/chat`. Inside the REPL, `/help` prints this same list and `/help <command>` prints the full entry.

**Full per-command reference — usage, parameters, examples, and the REST endpoint behind each one — is in [COMMANDS.md](COMMANDS.md).**

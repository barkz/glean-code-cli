# Configuration

Where Glean Code keeps state, how it authenticates, and every key you can set.

## Files on disk

| Path | What it holds | Perms |
| --- | --- | --- |
| `~/.gleancode/config.json` | Instance, tokens or secure refs, mode, theme, all keys below | `0o600` |
| `~/.gleancode/auth.json` | OAuth tokens from browser SSO | `0o600` |
| `~/.gleancode/personal.db` | The Glean Personal local index (see [PERSONAL.md](PERSONAL.md)) | `0o600` |
| `~/.gleancode/flow.db` | Flow mapper capture (see [FLOW_MAPPER.md](FLOW_MAPPER.md)) | `0o600` |

## Authentication

Three ways to authenticate, in order of preference:

| Method | How | Notes |
| --- | --- | --- |
| Browser SSO | `/login <hostname-or-instance-id>` | OAuth 2.1 + PKCE with DCR, same SSO path as the web app. IDs map to `<id>-be.glean.com`; tokens live in `~/.gleancode/auth.json`. See [SSO_OAUTH.md](SSO_OAUTH.md) |
| Secure ref | `/login --token token.secure.client` | Config stores the reference name; the real secret resolves from `$GLEAN_CLIENT_TOKEN` at request time. See [SECURE_TOKENS.md](SECURE_TOKENS.md) |
| Literal token | `/login --token <bearer_token>` | Written to `~/.gleancode/config.json` with `0o600` perms, masked to `***1234` everywhere it displays |

The Client API and the Indexing API take **separate tokens** — a Client token cannot reach `/api/index/v1`. Set the indexing one with `/config set indexing_token <token-or-secure-ref>`. Indexing still uses a Glean-issued token even when the Client API is on SSO.

Tokens are stripped from the in-memory history buffer and masked on every display surface. See [SECURE_TOKENS.md](SECURE_TOKENS.md) for the full masking matrix.

## Config keys

| Key | Description | Values |
| --- | --- | --- |
| `instance` | Glean backend hostname or instance ID | e.g. `acme-be.glean.com` or `acme` |
| `api_token` | Client API bearer token | Glean-issued token, or a secure ref like `token.secure.client` |
| `indexing_token` | Indexing API token | Glean-issued token, or `token.secure.indexing` |
| `act_as` | Impersonate a user via `X-Glean-ActAs` | Email address |
| `base_url` | Override the computed base URL | Full URL |
| `oauth_client_id` | Static OAuth client ID, or a DCR-generated ID | Optional; DCR is used when unset |
| `oauth_client_instance` | Instance bound to a DCR-generated client ID | Managed automatically |
| `oauth_scopes` | Space-separated OAuth scopes | Optional; defaults to Client API scopes |
| `redirect_port` | Fixed localhost callback port | Optional |
| `mode` | API mode | `auto` (default), `live`, `mock` |
| `theme` | Terminal colour theme | `glean` (default), `mono`, `neon` |
| `default_page_size` | Default result count for search and entities | Integer, default `10` |
| `mock_corpus_path` | JSON file backing mock mode | Path; unset uses the built-in corpus |
| `window_title` | Terminal window/tab title | `full` (default, includes the instance host), `plain` (mode only), `off` |

Change any key with `/config set <key> <value>`.

## Modes

| Mode | Behaviour |
| --- | --- |
| `auto` | Default. Live if an instance + credentials are configured, otherwise mock |
| `live` | Always call the API |
| `mock` | Always answer from the built-in corpus — see [MOCK_CORPUS.md](MOCK_CORPUS.md) |
| `local` | Answer `/search` and `/chat` from your own indexed files — see [PERSONAL.md](PERSONAL.md) |

Switch without editing config: `/mode live|mock|auto|local`.

## Health checks

```text
/status     # mode, instance, auth state, active chat thread
/doctor     # config, URL shape, DNS, TCP, and a live auth probe
```

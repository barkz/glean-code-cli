# Browser SSO (OAuth) for Glean Code CLI

The CLI can sign in the same way as the Glean web app: **OAuth 2.1 authorization code + PKCE** against your tenant’s authorization server (RFC 8414 discovery, with OpenID-configuration fallback). No device flow, no cookie scraping.

## Usage

```text
/auth login --instance acme-be.glean.com
/auth status
/search "quarterly planning"
/auth logout
```

`/auth login` flags:

| Flag | Purpose |
| --- | --- |
| `--instance <host>` | Glean backend host (saved in config) |
| `--client-id <id>` | Static OAuth client id (optional if the tenant supports DCR) |
| `--port <n>` | Fixed localhost callback port for redirect URI allowlisting |
| `--no-browser` | Print the authorize URL instead of opening a browser |

## How it wires in

- `glean_code.client` continues to use `config.effective_api_token` for the Client API bearer header.
- After `/auth login`, `effective_api_token` returns the OAuth access token (with refresh-on-demand). If you are not OAuth-signed-in, it falls back to `api_token` / secure refs as before.
- **Indexing** still uses `effective_indexing_token` only (OAuth is not used for the Indexing API).

## Config and files

| Location | Content |
| --- | --- |
| `~/.gleancode/config.json` | `oauth_client_id`, `oauth_scopes`, `redirect_port`, optional `oauth_*_url` overrides — never the access/refresh tokens |
| `~/.gleancode/auth.json` | OAuth tokens only (0600, written atomically) |

## Scope errors (e.g. “not allowed to request scope 'AGENT'”)

OAuth clients are often restricted to a fixed set of scopes. If authorization fails with an invalid / disallowed scope:

1. **Use a smaller scope string** in config, then run `/auth login` again (you may need `/auth logout` first if a half-login left state around):

   ```text
   /config set oauth_scopes "SEARCH CHAT DOCUMENTS TOOLS ENTITIES offline_access"
   ```

2. If your **admin** confirms your client may use agents, you can add `AGENT` (space-separated):

   ```text
   /config set oauth_scopes "SEARCH CHAT AGENT DOCUMENTS TOOLS ENTITIES offline_access"
   ```

The CLI default omits `AGENT` for compatibility with typical client registrations.

## Tests

```bash
python3 -m unittest tests.test_auth
```

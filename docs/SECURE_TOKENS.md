# Secure tokens

Glean Code never has to store a literal API token on disk. Instead of pasting the real token into config, you can store a **secure reference** — a fixed name like `token.secure.client` — and Glean Code resolves it from an environment variable at the moment a request is made.

## Reference table

| Reference | Resolves from | Used for |
| --- | --- | --- |
| `token.secure.client` | `$GLEAN_CLIENT_TOKEN` | All Client API calls (chat, search, agents, insights, etc.) |
| `token.secure.indexing` | `$GLEAN_INDEXING_TOKEN` | Indexing API calls (`/datasources.status`, `/indexing.rotate-token`) |

## Example — full setup

```bash
# 1. Put the real secrets in your shell environment.
#    Use whatever secret manager you already trust:
#    direnv, 1Password CLI, Doppler, AWS Secrets Manager, plain rc file, etc.
export GLEAN_CLIENT_TOKEN="glean_xxx_real_client_token"
export GLEAN_INDEXING_TOKEN="glean_idx_real_indexing_token"
```

```text
# 2. Tell Glean Code to look the values up by reference.
/login --instance acme-be.glean.com --token token.secure.client
/config set indexing_token token.secure.indexing
```

```text
# 3. Verify
/status
/doctor
```

After this, `~/.gleancode/config.json` contains the harmless string `token.secure.client`, not the real secret:

```json
{
  "instance": "acme-be.glean.com",
  "api_token": "token.secure.client",
  "indexing_token": "token.secure.indexing"
}
```

## What gets masked, where

| Surface | Behaviour |
| --- | --- |
| `/status` | Shows `token.secure.client ($GLEAN_CLIENT_TOKEN set)` for refs, `***1234` for literal tokens, `(unset)` if neither |
| `/config list` | Same — refs verbatim, literal tokens masked to last 4 chars |
| `/doctor` | Verifies the env var actually resolves; reports `FAIL` if a ref is configured but the env var is empty |
| `/history` | Strips secret values from `--token` / `--indexing-token` flags and from `/config set <token-key> <value>` so secrets never enter the in-memory history buffer |
| `config.json` on disk | Contains only the reference name when refs are used; literal tokens are written as-is and protected with `0o600` perms |

## Mixing refs and literals

You can use either form for either token. A literal is fine if you're testing locally and don't want the env-var indirection — Glean Code masks literal tokens on display so they never echo to the screen in full. Switch back and forth at any time with `/config set api_token <new-value-or-ref>`.

## Falling back to mock mode

If a secure ref is configured but the env var is unset, Glean Code's `is_live_ready` check returns false and `/mode auto` resolves to `mock`. You'll see ranked results from the [mock corpus](MOCK_CORPUS.md) instead of an unauthenticated 401 — handy for demos.

---

[← Back to README](../README.md) · [Browser SSO (OAuth)](SSO_OAUTH.md)

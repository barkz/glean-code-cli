# Natural-language planner (`/ask` and `?`)

`/ask` lets you describe what you want in plain English. Glean's own chat assistant translates the request into a sequence of Glean Code slash commands, the CLI shows the plan, you confirm, and the commands run.

```text
?login into acme-be.glean.com with my stored token, then search for "Q2 planning" and chat about it
```

> Why "use Glean to drive Glean"? Because the user already has a Glean token, and the chat endpoint is already wired up. No new API key, no new dependency, no extra spend — and Glean Assistant is a perfectly capable LLM for the simple JSON-emitting task we ask of it.

## Two ways to invoke it

| Form | When to use |
| --- | --- |
| `?<request>` | Inside the REPL — fastest. The `?` prefix routes to the planner. |
| `/ask "<request>"` | Inside scripts, pipes, or when you want to be explicit. |

```text
?show me datasource health
/ask "rotate the indexing token and then show its status"
```

Both forms invoke the same handler.

## What happens when you run it

The CLI executes a fixed pipeline:

1. **Build the catalogue.** Every command currently registered in `HANDLERS` is dumped, with its one-line summary from `DOCS`, into a compact `name: summary` list. This is auto-derived, so it stays in sync as new commands are added.
2. **Send to Glean Chat.** The catalogue is embedded in a system-prompt template and sent — together with your natural-language request — via `s.client.chat()`. The endpoint is `POST /chat` against your live Glean instance. The CLI prints a dim `Asking Glean...` while it waits.
3. **Parse the reply.** Glean responds with chat-style JSON. The local parser pulls the first JSON array out of the reply (it tolerates ` ```json ` fences and surrounding prose), then converts each `{cmd, args}` element into a step.
4. **Validate.** Each step's `cmd` is checked against the live `HANDLERS` registry. Unknown commands are flagged `[unknown — will be skipped]` so the planner cannot trick the CLI into executing something that doesn't exist.
5. **Substitute placeholders.** Steps containing `<stored>` get the literal value of `config.api_token` swapped in just before execution. The placeholder lets the planner reference your token symbolically without the token ever being included in the prompt sent to Glean.
6. **Render the plan.** A numbered list. Destructive steps show a yellow `[confirm]` badge.
7. **Confirm if needed.** If *any* step is destructive, a single `Run all? [y/N]` prompt appears at the top. Read-only plans skip the prompt entirely.
8. **Execute.** Each valid step is dispatched through the normal `dispatch()` function — the same code path as if you had typed each command yourself.

```text
Plan:
  1. /login --instance acme-be.glean.com --token <stored>   [confirm]
  2. /search "Q2 planning"
  3. /chat "summarise the top hit"

Run all? [y/N]: y

› /login --instance acme-be.glean.com --token ***1234
✔ Logged in to acme-be.glean.com.

› /search "Q2 planning"
[results...]

› /chat "summarise the top hit"
[chat reply...]
```

## Which commands trigger a confirm

Only writes, deletes, and auth-changing commands trigger the `Run all? [y/N]` gate. Pure reads run automatically.

| Category | Confirm? | Examples |
| --- | --- | --- |
| Auth & config | ✅ Confirm | `/login`, `/logout`, `/indexing.rotate-token`, `/config set ...` |
| Writes / deletes | ✅ Confirm | `/announcements.create`, `/answers.update`, `/pins.delete`, `/shortcuts.create`, `/verification.verify`, etc. |
| Indexing single-record | ✅ Confirm | `/index.document`, `/index.delete-user`, `/index.permissions`, `/index.membership`, ... |
| Indexing bulk + process-all | ✅ Confirm | `/index.bulk-documents`, `/people.bulk-employees`, `/index.process-all-documents`, `/people.process-all-employees-teams`, ... |
| Local writes | ✅ Confirm | `/scaffold`, `/feedback` |
| Pure reads | ❌ Auto | `/search`, `/chat`, `/status`, `/help`, `/datasources.list`, `/insights`, `/documents.status`, `/debug.*`, ... |
| Config inspection | ❌ Auto | `/config list`, `/config get <key>` |

The full destructive set lives in `_NL_DESTRUCTIVE` in [glean_code/commands.py](../glean_code/commands.py). Add to it whenever new mutating commands ship.

## Mock mode behaviour

The natural-language planner works without a live Glean token. In mock mode the CLI does **not** call `/chat`; instead it pattern-matches your prompt locally against a small set of intents — login, search, chat, datasources, status — and emits a canned plan. You'll see:

```text
ℹ [mock] using canned plan; switch to live mode for the real Glean planner
```

This is enough to demo the UX (the confirm flow, the plan rendering, dispatch wiring) without burning a Glean call. Switch to live mode (`/login`) to use Glean as the actual planner.

## Token-leak avoidance

The planner never sends your real token to Glean. Two protections:

1. **Symbolic reference.** The system prompt instructs the model to emit the literal placeholder `<stored>` whenever the user references "stored token", "saved token", or similar. Substitution happens locally, after parsing.
2. **History sanitization.** When `/ask` produces a `/login --token <real-secret>` step, that step is dispatched through the normal `dispatch()` flow — which already runs `_sanitize_for_history()` to strip secrets before they enter the in-memory history buffer.

If the model ignores the instruction and emits a real token anyway, that token will appear *in the rendered plan* on your screen but is still subject to history sanitization on dispatch. Don't pipe untrusted prompts.

## What can go wrong

| Symptom | Cause | What to do |
| --- | --- | --- |
| `Could not parse a command plan from Glean's reply.` | The tenant LLM returned prose instead of JSON, or returned malformed JSON | The CLI prints the raw reply between `--- raw reply ---` markers. Re-run with a more directive prompt, or fall back to typing the slash commands yourself. |
| `[unknown — will be skipped]` | Model hallucinated a command name | The plan still runs the valid steps. Refine your prompt or open a Discussions thread if a real-but-missing alias keeps coming up. |
| `Live mode requires an api_token and instance.` | You haven't logged in | Run `/login` first, then re-run `/ask`. |
| Slow first response (1–3s) | Network round-trip to your Glean tenant | Expected. Glean Assistant is doing real LLM work. The dim `Asking Glean...` line appears while you wait. |
| Plan looks wrong | Ambiguous or under-specified prompt | The model is told to "choose the most likely sensible interpretation rather than asking back" — for ambiguous requests, prefer being more explicit. The confirm gate is your safety net. |

## How to extend it

- **Add a new command to the catalogue.** Just register it via `@register("name")` and add an entry to `DOCS`. The catalogue builder picks it up automatically.
- **Mark a new command as destructive.** Add its name to `_NL_DESTRUCTIVE` in [glean_code/commands.py](../glean_code/commands.py).
- **Tweak the system prompt.** `_PLANNER_SYSTEM_PROMPT` is a single string at the top of the planner section in `commands.py`. Iterating on it is the cheapest way to improve plan quality.
- **Replace Glean Chat with another model.** The contract is "send a string, get a string back, expect a JSON array somewhere in it." Swap `s.client.chat(...)` for any other implementation that fits.

## Limitations (v1)

- **No streaming.** The CLI waits for the full reply before parsing.
- **No multi-turn.** Each `/ask` is a fresh request — there is no follow-up `/ask` that remembers the prior plan.
- **No partial confirm.** It's all-or-nothing on the prompt. A future revision could split into per-step confirms for very large plans.
- **English-only intent matching in mock mode.** Live mode handles whatever your tenant LLM handles.

## Related

- [Slash command reference](COMMANDS.md) — every command the planner can emit
- [`/ask` Command Reference](COMMANDS.md#ask) — usage and examples
- [Glean Code REPL system prompt](../glean_code/commands.py) — `_PLANNER_SYSTEM_PROMPT` constant

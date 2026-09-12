# How to use local indexing

A task-by-task guide to indexing your own folders and searching them.

This is the **how**. For what it is, how it works internally, and why it is
scoped the way it is, see [Glean Personal](PERSONAL.md).

- [Index your first folder](#index-your-first-folder)
- [Find things](#find-things)
- [Read a document](#read-a-document)
- [Index several folders separately](#index-several-folders-separately)
- [Keep it up to date](#keep-it-up-to-date)
- [Point the whole REPL at your files](#point-the-whole-repl-at-your-files)
- [Use it from Claude Code or another agent](#use-it-from-claude-code-or-another-agent)
- [Connect related documents](#connect-related-documents)
- [Why is this result here?](#why-is-this-result-here)
- [Why is my file missing?](#why-is-my-file-missing)
- [Start over, or remove a folder](#start-over-or-remove-a-folder)
- [Try it safely first](#try-it-safely-first)
- [Cheat sheet](#cheat-sheet)

## Index your first folder

Start the REPL and point it at a folder:

```text
$ python3 -m glean_code

/personal index ~/Documents --label docs
```

```text
── indexed: docs ───────────────────────────────────────────
  folder          /Users/you/Documents
  label           docs
  files matched   412
  added           409
  chunks written  8213
  text index      fts5
  elapsed         0.7s

  skipped 3 file(s):
    archive/old.docx — not a readable Office file
```

`--label` is the name you will search by. Leave it out and the folder's own
name is used, so `~/Downloads/mcp_bp` becomes `mcp_bp`.

**Index the leaves, not the trunk.** Sources are keyed by folder path and
nothing stops them overlapping, so indexing `~/Downloads` *and*
`~/Downloads/customers` stores every file in `customers` twice and you will see
duplicate hits. Pick one level and stay there.

## Find things

```text
/personal search "salary bands"
```

Every hit shows which folder it came from, the file, and the best-matching
passage:

```text
1. Compensation policy
   docs  file:///Users/you/Documents/hr/comp.md
   Markdown  ·  hr  ·  3 days ago
   Salary bands for FY27 are under review. Band 4 tops out at 120k.
```

Narrow to one folder, or change how many results you get:

```text
/personal search "salary bands" --source docs
/personal search "salary bands" --limit 3
```

Quoting matters: a `"quoted phrase"` is matched exactly, while bare words are
matched separately and ranked together.

```text
/personal search "q3 roadmap"          → documents containing either word
/personal search '"q3 roadmap"'        → documents containing the phrase
```

## Read a document

`/personal show` takes the `id` from a search result, a path, or any
distinctive fragment of the filename or title:

```text
/personal show comp
/personal show hr/comp.md
/personal show docs-hr-comp
```

Add `--meta` for the metadata and section list without the body — useful for
getting your bearings in a long document before reading it:

```text
/personal show Glean_MCP_Blueprint --meta
```

```text
── MCP: Connecting Intelligent Agents to Enterprise Systems ──
  id        mcp-glean_mcp_blueprint
  source    mcp
  path      /Users/you/Downloads/mcp_bp/Glean_MCP_Blueprint.pptx
  size      93.3 KB  (20638 chars, 27 chunks)

  Sections
  ▸ Slide 1
  ▸ Slide 2
```

## Index several folders separately

Give each folder its own label and they stay independently searchable while
still being searched together by default:

```text
/personal index ~/Downloads/customers  --label customers
/personal index ~/Downloads/interviews --label interviews
/personal index ~/Downloads/mcp_bp     --label mcp
```

```text
/personal sources

  customers    51 docs, 1457 chunks   /Users/you/Downloads/customers
  interviews    4 docs,   26 chunks   /Users/you/Downloads/interviews
  mcp           2 docs,   41 chunks   /Users/you/Downloads/mcp_bp
```

Search across all of them, or scope to one:

```text
/personal search "architecture"                      ← all three
/personal search "architecture" --source interviews  ← just that folder
```

### Indexing only some file types

```text
/personal index ~/notes --label notes --include '*.md,*.txt'
/personal index ~/work  --label work  --exclude 'drafts,*.tmp,archive/*'
```

Both take comma-separated globs. `--exclude` adds to the built-in list, which
already skips `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`
and Office lock files (`~$*`).

Large files are skipped at 5 MB; raise or lower it with `--max-bytes`.

## Keep it up to date

Just run the same command again:

```text
/personal index ~/Documents
```

It is incremental — files are compared by content hash, so a re-run over
thousands of files only re-reads what actually changed, and files you have
deleted are dropped from the index:

```text
  added           2
  updated         1
  unchanged     406
  removed         3
```

Filters are remembered per folder, so you do not need to repeat `--include` or
`--exclude` after the first run. `--reindex` forces a full re-read if you ever
want one.

Re-running is cheap and safe. Doing it after a working session is a reasonable
habit; there is no watcher or background process.

## Point the whole REPL at your files

`/mode local` makes `/search` and `/chat` answer from your index instead of
Glean:

```text
/mode local
/search "calibration"
/chat "what did I write about calibration"
/mode auto          ← back to Glean
```

`/chat` returns the matching passages with citations. It does **not** write an
answer — there is no model in the REPL, and one is not bundled. For a generated
answer, use the MCP route below, where the agent brings its own model.

Commands that need a real tenant (`/agents.list`, the Indexing API, and so on)
will tell you so rather than failing oddly.

## Use it from Claude Code or another agent

This is where local content becomes genuinely conversational: the agent has a
model, and your index supplies the context.

One-time setup — add the MCP server to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
    }
  }
}
```

Four tools then become available, needing no token and touching no network:

| Tool | What it does |
| --- | --- |
| `local_search` | ranked passages from your indexed folders |
| `local_fetch` | one document in full |
| `local_sources` | which folders are indexed |
| `local_related` | documents connected to this one |

Then just ask in plain language — "what did I write about the Q3 roadmap?" —
and the agent searches your index and answers from it. Full setup notes,
including running the server over HTTP: [docs/MCP.md](MCP.md).

## Connect related documents

The graph is built on demand, not during indexing:

```text
/personal link
/personal related roadmap
```

```text
── related to roadmap ──────────────────────────────────────
  Offsite agenda   score 0.69
    mcp_bp/offsite.pptx  (mcp)
    shares: platform team, calibration data model, q3
```

The `shares:` line is the evidence — the phrases the two documents have in
common — so you can judge a connection rather than take it on trust.

Run `/personal link` again after indexing new material. If nothing connects,
lower the threshold with `--min-score 0.2`. On a folder of only two or three
files, expect nothing to link: there is not enough vocabulary to tell "related"
from "both in English".

## Why is this result here?

Bare words in a query are matched separately, so a document can rank because it
matched one word out of three. `--explain` shows exactly that:

```text
/personal search "descaling weekly espresso" --explain
```

```text
1. SCHEDULING
   customers  file:///…/files/SCHEDULING.md
   › Scheduling the archive  ·  2 of 4 passages matched
   › matched: weekly   missed: descaling, espresso
   › bm25 11.96  ████████
```

A PowerShell scheduling document ranked first for a query about coffee, and the
reason is right there: only `weekly` matched. Without `--explain` that looks
like a broken index.

Read the four lines as:

- **matched / missed** — usually the whole answer
- **passages matched** — `1 of 27` is a passing mention, `27 of 27` is a
  document about the subject
- **the section** — where to look inside a long file
- **bm25** — the raw score, with a bar relative to the top hit

Results within 1% are reported as tied, because the ordering between them is
arbitrary. Scores are deliberately not shown as percentages — see
[PERSONAL.md](PERSONAL.md#explaining-a-result) for why.

## Why is my file missing?

Check the `skipped` list printed by `/personal index` first — it gives a reason
per file. The usual causes:

| Cause | What to do |
| --- | --- |
| Unsupported type (PDF, `.doc`, `.pages`, images) | Not indexable — see the supported list below |
| Bigger than 5 MB | `--max-bytes 20000000` |
| Inside `.git`, `node_modules`, `.venv`, `dist`, `build` | Excluded by default; pass your own `--exclude` to override |
| An `--include` you set earlier still applies | Filters persist per folder; set `--include` again to change them |
| No extractable text (empty, or an image-only document) | Nothing to index |
| A corrupt Office file | The reason says so; the run continues |

**Supported:** `.txt` `.md` `.markdown` `.html` `.htm` `.json` `.docx` `.xlsx`
`.pptx`

**Not supported:** PDF and the legacy binary `.doc` / `.xls` / `.ppt`. Neither
can be read without adding a dependency, which would cost the "one portable
file, nothing to install" property this feature is built around.

Also worth knowing: search matches whole words and prefixes, not substrings.
Searching `calib` finds "calibration", but `libration` does not. Non-English
text works — `München`, `Zürich` and CJK content all index and search normally.

## Start over, or remove a folder

```text
/personal purge customers     ← drop one folder from the index
/personal purge               ← empty the whole index
```

Both confirm first, and **neither touches a file on disk** — only the index
entries are removed. Re-index at any time to bring a folder back.

## Try it safely first

Everything lives under `~/.gleancode`, so redirecting `HOME` gives you a
completely separate instance to experiment in:

```bash
mkdir -p /tmp/glean-try/docs
echo '# Test

Salary bands for FY27.' > /tmp/glean-try/docs/comp.md

cd /path/to/glean-code-cli
HOME=/tmp/glean-try python3 -m glean_code
```

Index, search, purge, switch modes — none of it reaches your real index or
config. Remove it with `rm -rf /tmp/glean-try`.

## Cheat sheet

```text
/personal index <folder> [--label X] [--include '*.md,*.txt'] [--exclude 'drafts']
                         [--max-bytes N] [--reindex]
/personal search "<query>" [--source <label>] [--limit <n>] [--explain]
/personal show <id|path|fragment> [--meta]
/personal sources
/personal status
/personal link [--min-score 0.3] [--top-k 10]
/personal related <id|path|fragment> [--limit <n>]
/personal purge [<label>]

/mode local | auto        switch /search and /chat between your files and Glean
/help personal            the full flag reference
```

Where things live:

| | |
| --- | --- |
| The index | `~/.gleancode/personal.db` — one file, copy it to move it |
| Config | `~/.gleancode/config.json` |
| Reference and design notes | [docs/PERSONAL.md](PERSONAL.md) |
| Command reference | [docs/COMMANDS.md](COMMANDS.md#personal) |
| Agent setup | [docs/MCP.md](MCP.md) |

Your indexed content never leaves your machine. `personal.db` holds the text of
everything you indexed, so treat it as you would the folders it came from.

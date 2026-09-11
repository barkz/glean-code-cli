# Glean Personal

> Looking for step-by-step instructions? **[How to use local indexing](LOCAL_INDEXING.md)**
> is the task-by-task guide. This page is the reference: what it is, how it works
> internally, and why it is scoped the way it is.

A portable, local content index. Point it at folders on your machine; their
contents become searchable through the same `/search` and `/chat` surfaces the
REPL already has, and through MCP tools an external agent can call.

No server. No daemon. No Docker. No network. No credentials. The entire index
is one file — `~/.gleancode/personal.db` — and copying that file is how you
move it between machines.

```bash
python3 -m glean_code
```
```text
/personal index ~/Documents --label docs
/personal search "salary bands"
/personal link
/personal related roadmap
/mode local            # /search and /chat now answer from your files
```

## Why it exists

Mock mode proves the whole command surface works offline against a fictional
corpus. Glean Personal is the same idea pointed at content that is actually
yours: a real index, built from real files, with no tenant behind it.

It is deliberately **not** a local clone of Glean's server. It reproduces the
half of Glean that a personal machine can honestly provide — retrieval and a
content graph — and leaves out the halves that only a tenant has: permissions,
connectors, org-wide reach, and a model.

## Supported file types

| Extension | How it is read |
| --- | --- |
| `.txt`, `.md`, `.markdown` | read directly |
| `.html`, `.htm` | tags stripped with `html.parser`; `<script>`/`<style>` bodies dropped; `<title>` becomes the document title |
| `.json` | flattened to `key.path: value` lines so both halves are searchable; a top-level `title`/`name`/`subject` becomes the title |
| `.docx` | `zipfile` → `word/document.xml` → `xml.etree`; runs join within a paragraph, paragraphs stay separate; `docProps/core.xml` supplies the title |
| `.xlsx` | shared strings + each worksheet, row-wise, one section per sheet using the sheet's real name |
| `.pptx` | every text run per slide, one section per slide, ordered numerically |

The Office formats are ZIP archives of XML, which is why they cost no
dependencies. **PDF and legacy binary `.doc`/`.xls`/`.ppt` are out of scope** —
neither is reachable from the stdlib, and shelling out to `pdftotext` or
`textutil` would make your index depend on what happens to be installed on that
particular machine, which defeats the portability goal. Unsupported files are
listed in the skip report with a reason rather than silently ignored.

## How it works

**Chunks, not files.** A forty-page document answers a question from one
section of itself, and an agent wants the passage rather than the file. Text is
split on headings first, then packed into ~1200-character windows at paragraph
boundaries. Only a paragraph longer than one chunk falls through to sentence
windowing, which carries ~150 characters of overlap — a cut at a blank line
cannot split the sentence that answers the question, but a cut inside a
paragraph can.

**Search is SQLite FTS5**, ranked with `bm25()` and weighted so a title hit
beats a heading hit beats a body hit. FTS5 is compiled into essentially every
SQLite the stdlib ships against. A capability probe runs at connect time, and on
an interpreter that lacks it the index falls back to a plain table plus a Python
scorer — degraded ranking rather than no search. `/personal status` says which
is in use. An existing database keeps the store it was built with; switching
would orphan every chunk.

**Chunk text lives in exactly one place** — the text store — so there is no
second copy to keep in sync.

**Re-indexing is incremental** on a SHA-256 content hash. Pointing this at a
5,000-file folder every day re-reads only what changed. A file whose mtime moved
but whose bytes did not is not re-chunked. Files that have vanished from disk, or
that a new `--include`/`--exclude` now excludes, are removed from the index.
Filters are stored per source, so a later bare `/personal index <folder>`
repeats the filters you set the first time.

**The content graph** connects documents that discuss the same things. Links
come from shared phrases — single terms and bigrams — weighted by rarity, with
a bonus when two titles share a rare word. Each link stores the phrases that
produced it, so `/personal related` can show you *why* two documents connect
rather than asserting that they do. Candidate pairs come from an inverted index
over discriminating phrases, because comparing every pair is quadratic and a
folder of several thousand files makes that untenable.

Gating is on document frequency, not IDF: a phrase in one document cannot
connect anything, and a phrase in most of them is vocabulary rather than subject
matter. IDF is corpus-size dependent — on a five-file folder a phrase shared by
two documents scores 0.6, below any fixed floor — so an IDF gate finds no links
at all in exactly the case a personal index starts from.

**Each document keeps its strongest `--top-k` neighbours** (default 10), and a
link survives if *either* endpoint ranks it, so an asymmetric relationship is not
lost and a hub document cannot monopolise the graph. This matters more than it
sounds. Measured on a real 1,350-document folder, a bare threshold produced
52,631 links — a median of 34 neighbours per document and a worst case of 292,
with 60% of them sitting within 0.05 of the threshold. Raising the threshold
enough to thin that noise also drops genuine links between short documents;
keeping each document's best few is what makes the graph navigable. The same
corpus yields 7,518 links with a median score of 0.956 instead of 0.317.

Pruning for speed is done by document frequency rather than by per-document
rank, and that choice is load-bearing rather than incidental. Ranking phrases
by IDF alone leaves every equally-rare phrase tied, and sorting a *set* breaks
ties in iteration order, which differs per document — so two near-duplicate
files keep disjoint slices of the very phrases that connect them. On two real
20 KB decks sharing 1,495 phrases, a rank-only prune left them sharing none and
scored the strongest link in the corpus at 0.0. Document frequency is a property
of the phrase, not of the document holding it, so a phrase is kept by both ends
of a pair or by neither.

## Explaining a result

Queries are ORed and ranked by bm25, so a document can rank because it matched one term of
three. `--explain` shows the evidence behind each hit:

```text
/personal search "descaling weekly espresso" --explain

1. SCHEDULING
   customers  file:///…/files/SCHEDULING.md
   › Scheduling the archive  ·  2 of 4 passages matched
   › matched: weekly   missed: descaling, espresso
   › bm25 11.96  ████████
```

Four things, in rough order of how often they explain a surprise:

- **matched / missed terms** — nearly always the answer to "why is this here?"
- **passages matched** — `1 of 27` is a passing mention; `27 of 27` is a document about it
- **the matching section** — where to look inside a long file
- **the bm25 score**, with a bar relative to the top hit

Deliberately **not** a percentage. bm25 is corpus-relative and carries no absolute meaning —
the same code scores 25.41 on one index and 3.5e-06 on another — so a figure like "98%
relevant" would claim a calibrated confidence that was never computed. Results within 1% are
reported as tied, since the ordering between them is arbitrary; a percentage would render a
real tie as "100%, 100%, 98%" and hide exactly that.

The matched-terms list is re-derived rather than reported by FTS5, which does not expose
per-term hits. FTS5 stems with porter, so the check can under-report on an irregular stem;
prefix matching is tested both ways to cover the common plural/singular case. A miss makes
the explanation incomplete, never the result wrong.

`--explain` is a `/personal search` flag only. Plain `/search` in local mode stays
byte-compatible with the Client API response shape, which is what lets one renderer draw
local and Glean hits alike.

## Local mode

`/mode local` makes the whole REPL answer from the personal index:

| Endpoint | Behaviour in local mode |
| --- | --- |
| `/search` | ranked local results, Client-API shaped |
| `/chat` | matching passages with citations, extractive |
| `/autocomplete` | completions drawn from indexed titles and headings |
| `/getdocuments` | one document with its reassembled text |
| everything else | a `GleanError` naming what local mode does cover |

Local responses use the Client API's own response shapes, so every renderer in
the REPL draws them unchanged — the same trick that lets mock mode reuse the
entire command surface. The one addition is a `localIndex` marker on the
response, which is what makes the `[LOCAL INDEX]` banner appear.

Only `auto` resolves from credentials. `local` is taken at its word, so the
index keeps answering once you configure a live token. Switch back with
`/mode auto`.

The Indexing API has no local counterpart and says so: it pushes content into a
Glean tenant, whereas `/personal index` builds a local index. Two different
things that happen to share a verb.

## Consuming it from an agent (MCP)

Four tools in [`glean_mcp.py`](../glean_mcp.py) expose the index to any
MCP client — Claude Code, Claude Desktop, Cursor:

| Tool | Purpose |
| --- | --- |
| `local_search` | ranked passages with a document id for each |
| `local_fetch` | one document in full, by id, path, or fragment |
| `local_sources` | which folders are indexed, and how much is in each |
| `local_related` | graph neighbours with the shared phrases as evidence |

These never touch the network or the Glean API, need no token, and are
unaffected by `GLEAN_MOCK` — that variable governs the Glean-backed tools only.
Setup is the same as any other tool on this server: see [docs/MCP.md](MCP.md).

## On local models

Glean Personal supplies **context, not inference**. `/chat` returns passages
verbatim and generates no prose, because this process has no model and
inventing an answer would launder a guess into whatever you do next.

That is a deliberate scope boundary rather than a missing feature. Every path to
in-process generation costs exactly what portability buys: `llama.cpp` needs a
compiled binary per platform, Ollama and LM Studio are multi-gigabyte daemons,
`onnxruntime` is a ~200 MB platform-specific wheel. A one-file index that has to
be accompanied by any of those is not portable.

The model comes from whoever is asking:

- **An MCP client** already has one. It calls `local_search`, gets passages, and
  synthesises. This is the primary path and costs nothing.
- **A human** reads the passages directly, which for "what did I write about X"
  is often the whole answer.

Embeddings are a related question with a different answer. Semantic recall would
genuinely beat BM25 on paraphrases, and vectors are *portable once computed* —
they are just floats in the `.db` and they travel with it. But you need the
embedder again for new files and for every query, so BM25 has to remain the
always-works floor, with vectors as an accelerant that degrades gracefully on a
machine where no embedder is reachable. The schema is shaped to allow that later
without a migration.

## Privacy and portability

Nothing leaves your machine. There is no network path in this feature at all —
not a hostname, not a port, not an optional telemetry call.

`personal.db` is created `0600`, like the rest of `~/.gleancode`. It contains the
**text** of everything you indexed, so treat it as you would the folder it came
from: an index of `~/Documents` is as sensitive as `~/Documents`. It carries no
permission model, because a single-user machine has nothing to model.

To move an index: copy `personal.db`. To rebuild one: `/personal index` the same
folders. Note that documents record absolute paths, so `file://` links in results
point at wherever the files lived on the machine that built the index.

`/personal purge` deletes index rows and never touches a file on disk.

## Limits

- Text only, in the formats above. No OCR, no image content, no audio.
- No permissions. Everything indexed is visible to whoever can run the CLI.
- Keyword search, not semantic. "comp plan" will not find "salary bands" unless
  the words co-occur somewhere.
- 5 MB per file by default (`--max-bytes`), and a single document's extracted
  text is capped at 4 MB.
- The graph is phrase-based. It finds documents about the same subject; it does
  not reason about them.
- Snippets pick the densest term match in a chunk, which in Markdown is
  sometimes a code fence or a table row rather than prose. The ranking is
  unaffected; only the preview line is.
- `~$*` lock files, `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`,
  `build` and friends are excluded by default. Add more with `--exclude`.

## Troubleshooting

**`/personal status` says "plain + Python scorer".** This SQLite has no FTS5.
Search still works, ranked by a Python scorer instead of bm25. To switch, install
a Python whose SQLite has FTS5 and rebuild: `/personal purge`, then re-index.
The store is chosen when the database is created and never changes under an
existing one.

**A file I expected is missing.** Check the skip list in the `index` report. The
usual causes are an unsupported extension, `--max-bytes`, a default exclude
pattern, or a file with no extractable text.

**`/personal related` finds nothing.** Run `/personal link` first — the graph is
built on demand, not during indexing. If it still finds nothing, lower
`--min-score`. On a very small folder (two or three files) IDF cannot separate
"topically shared" from "common vocabulary" and links may not clear any
threshold; that is a property of IDF at that scale, not a fault in the index.

**`/personal link` is slow on a big folder.** Expect a few seconds per thousand
documents — 1,350 documents takes about 7 seconds. It reports progress as it
goes. Raise `--min-score` or lower `--top-k` to cut the work.

**Search finds nothing for a phrase I can see in the file.** Quoted spans are
exact phrases; bare terms are ORed prefix matches. Try the bare terms. Note that
stopwords and single characters are dropped from queries.

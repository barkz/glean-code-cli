# Support

Thanks for using Glean Code. This page sets expectations for bug reports, feature
requests, and pull requests — please read it before opening an issue.

## There is no SLA

Glean Code is a personal project, maintained part time around a full-time job. Everything
below is **best-effort**: a description of what usually happens, not a commitment about what
will happen. Nothing on this page creates an obligation of any kind, and the
[MIT license](LICENSE) terms — software provided "as is", without warranty — are the actual
agreement.

In practice that means:

- Work happens in evenings and weekends, in bursts. A quiet fortnight is normal.
- **Silence is not rejection.** An issue with no reply has usually been read and queued, not
  dismissed. Bump the thread if it's been a few weeks and still matters to you.
- Some issues will be closed as "won't fix" simply for want of time. That's a scheduling
  decision, not a judgment about the report.
- Urgency in your environment doesn't transfer here. If you need a guaranteed turnaround,
  the reliable options are to fork, to send a pull request, or to vendor the parts you need —
  it's a small, dependency-free, single-package codebase, and that is deliberate.

## What gets attention first

Roughly in this order:

1. **Security issues** — credential handling, token leakage, anything that widens access.
2. **Destructive behavior** — anything that deletes, overwrites, or corrupts data outside
   this tool's own files. A bug that can damage a user's system or tenant jumps the queue.
3. **Correctness bugs against a live tenant** — a command that sends the wrong request body,
   silently drops a flag, or reports success on a failed call.
4. **Crashes and regressions** on a supported platform (macOS and Linux, Python 3.9+).
5. **Documentation that is wrong** — worse than documentation that is missing, because it
   costs someone else time.
6. **New features, new command coverage, and refactors** — genuinely nice to have, and
   genuinely last.

## Best-effort response targets

Targets, not promises. Every row can and will slip.

| Kind of report | First response | Fix or decision |
| --- | --- | --- |
| Security issue | Days | Prioritised over everything else |
| Destructive-behavior bug | Days | As soon as a fix is verified |
| Bug with a clear reproduction | A week or two | Depends on scope |
| Bug without a reproduction | May sit until someone can reproduce it | — |
| Feature request | A week or two, if only to say yes/no/not-now | No timeline; may sit indefinitely |
| Pull request | A week or two | See [Pull requests](#pull-requests) |

## Making a fix likely

A report that can be reproduced in **mock mode** is worth several that can't — mock mode
needs no credentials, no tenant, and no network, so it can be run instantly and turned into a
regression test. See [docs/MOCK_CORPUS.md](docs/MOCK_CORPUS.md).

Please include:

- **Version** — the banner line from `/status`, e.g. `Glean Code v0.1.0 · mode: mock`.
- **OS and Python version** — `python3 --version`.
- **Mode** — mock or live. If it happens in live mode only, say so explicitly.
- **The exact command** you ran and what came back.
- **For indexing commands**, the payload from `--dry-run` rather than a description of it.

**Never paste a token, an `Authorization` header, or a full `~/.gleancode/config.json`.**
Redact before posting. If a report only makes sense with real data, redact the values and
keep the shape.

## Out of scope

- **Your Glean tenant, its data, or the Glean API itself.** This is an independent client
  that calls a published API. Indexing problems, permissions questions, missing documents,
  and API errors originating server-side belong with your Glean administrator or Glean's own
  support, not here. Bugs in *how this client calls* the API are very much in scope.
- **Anything requiring credentials or a tenant I don't have.** I can reason about it, but
  I may not be able to verify a fix — expect slower, more tentative progress.

## Security issues

Please do not open a public issue for a vulnerability. Use GitHub's private vulnerability
reporting on this repository (Security → Report a vulnerability), which reaches me directly.

Security reports are the one category where I will drop other work. If you don't hear back
within a few days, assume the notification was missed and follow up.

## Pull requests

Pull requests are the fastest path from "this is broken" to "this is fixed", and they're
welcome — including from first-time contributors.

What makes review quick:

- **Tests.** The suite is stdlib-only and runs in seconds: `python3 -m unittest discover tests/`.
  A bug fix should come with a test that fails before it and passes after.
- **Green CI.** The workflow runs the suite across Python 3.9–3.13 on Linux plus macOS.
- **Docs updated in the same PR** when behavior changes. A code change that leaves the README
  describing the old behavior isn't finished.
- **One concern per PR.** A focused diff gets reviewed in an evening; a large mixed one waits
  for a free weekend.
- **No new runtime dependencies.** Zero-dependency, stdlib-only is a hard constraint of the
  project, not a preference.

Large or architectural changes are worth an issue first, so nobody spends a weekend on
something that turns out not to fit.

## Questions and ideas

For "how do I…", "should this work like…", or "would you consider…", use
[Discussions](../../discussions) rather than an issue. Same best-effort response, but it
keeps the issue tracker to actionable defects.

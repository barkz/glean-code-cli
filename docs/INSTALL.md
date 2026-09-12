# Install

Python 3.9 or newer. Standard library only — no `pip install`, no build step, no lockfile.

## Run it straight from the repo

```bash
cd glean-code-cli
python3 -m glean_code
```

## Install it on your PATH

```bash
python3 install.py
```

This builds a single-file zipapp (~84 KB, still stdlib-only) and installs it as
`glean` in `~/.local/bin`. On macOS it also creates `~/Applications/Glean Code.app`
and registers it with LaunchServices, so the REPL is launchable from Spotlight —
`Cmd+Space` → "Glean Code" → Enter opens it in a Terminal window.

| Flag | Effect |
| --- | --- |
| _(none)_ | Install the CLI and, on macOS, the Spotlight app |
| `--cli-only` | Skip the macOS app bundle |
| `--dev` | App launches from the working tree, so edits apply with no rebuild |
| `--prefix DIR` | Install the `glean` executable somewhere other than `~/.local/bin` |
| `--verify` | Report what is currently installed |
| `--uninstall` | Remove the CLI and the app bundle this installer created (config is left alone) |

Re-run `python3 install.py` after pulling changes to refresh the snapshot, or install
once with `--dev` and skip that step entirely.

**The bundle is called `Glean Code.app`, never `Glean.app`** — the latter is Glean's own
desktop client (`com.glean.desktop`). The installer reads `CFBundleIdentifier` before it
writes anything and refuses a bundle it did not create, and `--uninstall` skips one for the
same reason, so neither can damage an app it doesn't own:

```text
x ~/Applications/Glean Code.app already exists and belongs to another app
  (CFBundleIdentifier: com.glean.desktop).
  Refusing to write into it. Move or rename that bundle, or run with --cli-only.
```

If you installed before this change you have a `Glean.app` bundle that we do own; the next
`python3 install.py` removes it and replaces it with `Glean Code.app`. That's why the
Spotlight entry changes name — nothing is lost.

## Or just alias it

No install, no zipapp — a new terminal is one word away from a Glean session:

```bash
alias glean="PYTHONPATH=<YOUR_PATH>/glean-code-cli python3 -m glean_code"
```

## First run

**Sign in with Glean OAuth** using a backend hostname or instance ID:

```text
/login <hostname-or-instance-id>
/status
/search "quarterly planning"
/chat "summarise the Q2 plan"
```

For example, `/login acme` uses the instance ID `acme`. Run `/help login` for other login options. Without login, the CLI runs in **mock** mode.

Next: **[Configuration](CONFIGURATION.md)** for config keys and where files live, or the **[command index](COMMAND_INDEX.md)** for what you can run.

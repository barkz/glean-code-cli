#!/usr/bin/env python3
"""Set __version__ to 0.2.<pr>, the scheme this repo uses.

The patch component is the number of the pull request that introduces the
change, so releases are traceable straight back to a PR. Because that number
only exists once the PR is open, the bump happens inside the PR and the
`version` job in release.yml enforces it.

    python3 tools/set_version.py 40      # -> 0.2.40
    python3 tools/set_version.py          # infer from the open PR via gh
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parent.parent / "glean_code" / "__init__.py"
PATTERN = re.compile(r'^__version__ = "([^"]+)"', re.M)
SERIES = "0.2"


def current() -> str:
    m = PATTERN.search(INIT.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"could not find __version__ in {INIT}")
    return m.group(1)


def infer_pr() -> str:
    """Ask gh for the PR number of the current branch."""
    try:
        out = subprocess.run(
            ["gh", "pr", "view", "--json", "number", "-q", ".number"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        sys.exit("gh is unavailable — pass the PR number explicitly")
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit(
            "no open PR found for this branch. Open it first, then re-run:\n"
            "    python3 tools/set_version.py <pr-number>"
        )
    return out.stdout.strip()


def main(argv=None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    pr = args[0] if args else infer_pr()
    if not pr.isdigit():
        sys.exit(f"expected a PR number, got {pr!r}")

    new = f"{SERIES}.{pr}"
    was = current()
    if was == new:
        print(f"__version__ is already {new}")
        return 0

    text = INIT.read_text(encoding="utf-8")
    INIT.write_text(PATTERN.sub(f'__version__ = "{new}"', text, count=1), encoding="utf-8")
    print(f"__version__  {was} -> {new}")
    print("User-Agent strings derive from it, so nothing else needs editing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

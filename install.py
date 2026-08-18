#!/usr/bin/env python3
"""Glean Code installer.

Builds the single-file zipapp and installs it so `glean` is on your PATH. On
macOS it also creates a "Glean Code.app" bundle so the REPL is launchable from
Spotlight (Cmd+Space -> "Glean Code").

The bundle is deliberately not named Glean.app — that belongs to Glean's own
desktop client. The installer never writes into, or removes, an app bundle it
did not create.

Usage:
    python3 install.py                 Build and install (CLI + macOS app)
    python3 install.py --cli-only      Skip the macOS app bundle
    python3 install.py --dev           App launches from source, not a snapshot
    python3 install.py --prefix DIR    Install the CLI somewhere other than ~/.local/bin
    python3 install.py --verify        Report what is currently installed
    python3 install.py --uninstall     Remove everything this script installed

Stdlib only, like the rest of the project. No pip install required.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipapp
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = REPO_ROOT / "glean_code"

DEFAULT_PREFIX = Path.home() / ".local" / "bin"
CLI_NAME = "glean"

# Deliberately NOT "Glean.app": that is Glean's own desktop client
# (com.glean.desktop). Writing into a bundle we did not create would corrupt a
# signed third-party app — macOS blocks it with EPERM, and uninstall would have
# deleted it outright.
APP_DIR = Path.home() / "Applications" / "Glean Code.app"
BUNDLE_ID = "com.glean.gleancode.launcher"

# Earlier versions installed to Glean.app. Cleaned up on install/uninstall, but
# only when the bundle is one we actually created — see owns_bundle().
LEGACY_APP_DIR = Path.home() / "Applications" / "Glean.app"

# Name of the executable inside the bundle. Distinct from Glean Desktop's
# "Glean" so the two are never confused in Spotlight or Activity Monitor.
APP_EXECUTABLE = "GleanCode"

LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks"
    "/LaunchServices.framework/Support/lsregister"
)

# Excluded from the zipapp: caches, editor cruft, Spotlight markers.
STAGE_EXCLUDES = {"__pycache__", ".DS_Store", ".metadata_never_index"}

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>                 <string>Glean Code</string>
    <key>CFBundleDisplayName</key>          <string>Glean Code</string>
    <key>CFBundleIdentifier</key>           <string>{bundle_id}</string>
    <key>CFBundleExecutable</key>           <string>{executable}</string>
    <key>CFBundlePackageType</key>          <string>APPL</string>
    <key>CFBundleVersion</key>              <string>{version}</string>
    <key>CFBundleShortVersionString</key>   <string>{version}</string>
    <key>LSMinimumSystemVersion</key>       <string>10.13</string>
    <key>NSHighResolutionCapable</key>      <true/>
</dict>
</plist>
"""


# ---------------------------------------------------------------- helpers


def _ok(msg: str) -> None:
    print(f"  \033[32m+\033[0m {msg}")


def _info(msg: str) -> None:
    print(f"  \033[2m·\033[0m {msg}")


def _warn(msg: str) -> None:
    print(f"  \033[33m!\033[0m {msg}")


def _fail(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"  \033[31mx\033[0m {msg}", file=sys.stderr)
    raise SystemExit(1)


def _tilde(path: Path) -> str:
    """Render a path with ~ for the home directory, for readable output."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def is_macos() -> bool:
    return platform.system() == "Darwin"


def package_version() -> str:
    """Read __version__ out of the package without importing it."""
    init = PACKAGE_DIR / "__init__.py"
    for line in init.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


# ---------------------------------------------------------------- build


def build_zipapp(target: Path) -> Path:
    """Build a single-file executable zipapp of the package at *target*."""
    if not PACKAGE_DIR.is_dir():
        _fail(f"package not found at {PACKAGE_DIR}")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        shutil.copytree(
            PACKAGE_DIR,
            stage / PACKAGE_DIR.name,
            ignore=shutil.ignore_patterns(*STAGE_EXCLUDES),
        )
        (stage / "__main__.py").write_text(
            "from glean_code.cli import main\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n",
            encoding="utf-8",
        )
        zipapp.create_archive(
            stage,
            target=target,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
    target.chmod(0o755)
    return target


# ---------------------------------------------------------------- CLI


def install_cli(prefix: Path, pyz: Path) -> Path:
    """Copy the zipapp to *prefix* as an executable named `glean`."""
    prefix.mkdir(parents=True, exist_ok=True)
    dest = prefix / CLI_NAME
    shutil.copy2(pyz, dest)
    dest.chmod(0o755)
    return dest


def on_path(prefix: Path) -> bool:
    entries = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    return any(p == prefix for p in entries)


# ---------------------------------------------------------------- macOS app


def _launch_script(dev: bool) -> str:
    """Body of the .command the app opens in Terminal."""
    if dev:
        return (
            "#!/bin/zsh\n"
            "# Runs Glean Code from the working tree, so edits apply immediately.\n"
            f'cd "{REPO_ROOT}" || exit 1\n'
            "exec /usr/bin/env python3 -m glean_code\n"
        )
    return (
        "#!/bin/zsh\n"
        "# Runs the bundled snapshot of Glean Code.\n"
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        'exec /usr/bin/env python3 "$HERE/glean-code.pyz"\n'
    )


def bundle_identifier(app_dir: Path) -> Optional[str]:
    """Read CFBundleIdentifier out of an app bundle's Info.plist, or None."""
    plist = app_dir / "Contents" / "Info.plist"
    try:
        text = plist.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Info.plist may be binary; a text scan is enough to spot the key we set,
    # and anything unreadable is treated as "not ours", which is the safe call.
    marker = "<key>CFBundleIdentifier</key>"
    if marker not in text:
        return None
    tail = text.split(marker, 1)[1]
    start = tail.find("<string>")
    end = tail.find("</string>", start)
    if start == -1 or end == -1:
        return None
    return tail[start + len("<string>"):end].strip()


def owns_bundle(app_dir: Path) -> bool:
    """True only for an app bundle this installer created.

    A missing bundle counts as ours — there is nothing to clobber. Anything
    else (another vendor's app, an unreadable plist) does not, so we never
    write into or delete something we did not put there.
    """
    if not app_dir.exists():
        return True
    return bundle_identifier(app_dir) == BUNDLE_ID


def install_macos_app(pyz: Path, dev: bool = False) -> Path:
    """Create ~/Applications/Glean Code.app and register it with LaunchServices."""
    if not owns_bundle(APP_DIR):
        found = bundle_identifier(APP_DIR) or "unknown"
        _fail(
            f"{_tilde(APP_DIR)} already exists and belongs to another app "
            f"(CFBundleIdentifier: {found}).\n"
            f"    Refusing to write into it. Move or rename that bundle, or run "
            f"with --cli-only to skip the app."
        )

    macos_dir = APP_DIR / "Contents" / "MacOS"
    resources = APP_DIR / "Contents" / "Resources"
    for d in (macos_dir, resources):
        d.mkdir(parents=True, exist_ok=True)

    # The snapshot the launcher runs (unused in --dev, but harmless to ship).
    shutil.copy2(pyz, resources / "glean-code.pyz")
    (resources / "glean-code.pyz").chmod(0o755)

    launcher = resources / "glean-launch.command"
    launcher.write_text(_launch_script(dev), encoding="utf-8")
    launcher.chmod(0o755)

    # The bundle executable just hands the .command to Terminal, which gives
    # the REPL a real terminal window and keeps it open afterwards.
    executable = macos_dir / APP_EXECUTABLE
    executable.write_text(
        "#!/bin/zsh\n"
        '# Opens Terminal running the Glean Code REPL.\n'
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        'exec /usr/bin/open -a Terminal "$HERE/../Resources/glean-launch.command"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)

    (APP_DIR / "Contents" / "Info.plist").write_text(
        INFO_PLIST.format(bundle_id=BUNDLE_ID, version=package_version(),
                          executable=APP_EXECUTABLE),
        encoding="utf-8",
    )

    # An older release installed to Glean.app. Remove it, but only if it is
    # genuinely ours — on a machine with Glean Desktop it never is.
    if LEGACY_APP_DIR.exists() and owns_bundle(LEGACY_APP_DIR):
        shutil.rmtree(LEGACY_APP_DIR)
        _info(f"removed old {_tilde(LEGACY_APP_DIR)}")

    return APP_DIR


def register_app(app: Path) -> bool:
    """Tell LaunchServices about the bundle so Spotlight ranks it as an app."""
    if not Path(LSREGISTER).exists():
        return False
    try:
        subprocess.run([LSREGISTER, "-f", str(app)], check=True,
                       capture_output=True, timeout=30)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def spotlight_attributes(app: Path) -> dict:
    """Read back the attributes that decide Spotlight ranking."""
    wanted = ("kMDItemContentType", "kMDItemDisplayName", "kMDItemKind")
    out: dict = {}
    try:
        proc = subprocess.run(
            ["mdls", *sum((["-name", w] for w in wanted), []), str(app)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return out
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"')
    return out


def wait_for_spotlight(app: Path, timeout: float = 15.0) -> dict:
    """Poll until Spotlight has indexed the bundle as an application.

    Indexing is asynchronous and typically lands a few seconds after the
    bundle is written, so reporting immediately would show empty attributes.
    """
    deadline = time.monotonic() + timeout
    attrs: dict = {}
    while time.monotonic() < deadline:
        attrs = spotlight_attributes(app)
        if attrs.get("kMDItemContentType") == "com.apple.application-bundle":
            return attrs
        time.sleep(1.0)
    return attrs


# ---------------------------------------------------------------- actions


def do_install(args: argparse.Namespace) -> int:
    prefix = Path(args.prefix).expanduser().resolve()
    print(f"\nGlean Code {package_version()} — install\n")

    with tempfile.TemporaryDirectory() as tmp:
        pyz = build_zipapp(Path(tmp) / "glean-code.pyz")
        size_kb = pyz.stat().st_size / 1024
        _ok(f"built zipapp ({size_kb:.0f} KB, stdlib only)")

        cli = install_cli(prefix, pyz)
        _ok(f"installed CLI  {_tilde(cli)}")
        if not on_path(prefix):
            _warn(f"{_tilde(prefix)} is not on your PATH. Add to ~/.zshrc:")
            print(f'      export PATH="{_tilde(prefix)}:$PATH"')

        if args.cli_only:
            _info("skipping macOS app bundle (--cli-only)")
        elif not is_macos():
            _info(f"skipping macOS app bundle (host is {platform.system()})")
        else:
            app = install_macos_app(pyz, dev=args.dev)
            mode = "source" if args.dev else "snapshot"
            _ok(f"installed app  {_tilde(app)}  (launches from {mode})")
            if register_app(app):
                _ok("registered with LaunchServices")
            else:
                _warn("could not run lsregister; Spotlight may lag until relogin")
            _info("waiting for Spotlight to index the bundle...")
            attrs = wait_for_spotlight(app)
            for key in ("kMDItemContentType", "kMDItemDisplayName"):
                if attrs.get(key):
                    _info(f"{key} = {attrs[key]}")
            if attrs.get("kMDItemContentType") == "com.apple.application-bundle":
                _ok('Spotlight ranks it as an Application — Cmd+Space "Glean Code" wins')
            else:
                _warn("Spotlight has not indexed it yet; it should appear shortly")

    print("\nDone. Launch it with:\n")
    print(f"    {CLI_NAME}                    (terminal)")
    if is_macos() and not args.cli_only:
        print("    Cmd+Space -> \"Glean Code\" (Spotlight)")
    print()
    return 0


def do_verify(_args: argparse.Namespace) -> int:
    print(f"\nGlean Code {package_version()} — installed state\n")
    found = False

    for prefix in {DEFAULT_PREFIX, Path(_args.prefix).expanduser().resolve()}:
        cli = prefix / CLI_NAME
        if cli.exists():
            found = True
            _ok(f"CLI  {_tilde(cli)}  ({cli.stat().st_size / 1024:.0f} KB)")
            if not on_path(prefix):
                _warn(f"{_tilde(prefix)} is not on your PATH")

    if is_macos() and APP_DIR.exists() and owns_bundle(APP_DIR):
        found = True
        _ok(f"app  {_tilde(APP_DIR)}")
        attrs = spotlight_attributes(APP_DIR)
        for key, value in attrs.items():
            _info(f"{key} = {value}")
        if attrs.get("kMDItemContentType") != "com.apple.application-bundle":
            _warn("not indexed as an application — run: python3 install.py")

    if is_macos() and LEGACY_APP_DIR.exists() and owns_bundle(LEGACY_APP_DIR):
        found = True
        _warn(f"old bundle at {_tilde(LEGACY_APP_DIR)} — re-run install.py to replace it")

    if not found:
        _info("nothing installed. Run: python3 install.py")
    print()
    return 0


def do_uninstall(args: argparse.Namespace) -> int:
    print("\nGlean Code — uninstall\n")
    removed = False

    for prefix in {DEFAULT_PREFIX, Path(args.prefix).expanduser().resolve()}:
        cli = prefix / CLI_NAME
        if cli.exists():
            cli.unlink()
            _ok(f"removed {_tilde(cli)}")
            removed = True

    for app_dir in (APP_DIR, LEGACY_APP_DIR):
        if not app_dir.exists():
            continue
        if not owns_bundle(app_dir):
            found = bundle_identifier(app_dir) or "unknown"
            _info(f"leaving {_tilde(app_dir)} in place — belongs to another app ({found})")
            continue
        shutil.rmtree(app_dir)
        _ok(f"removed {_tilde(app_dir)}")
        removed = True

    legacy = Path.home() / "Applications" / "Glean.command"
    if legacy.exists():
        _info(f"leaving {_tilde(legacy)} in place (not created by this installer)")

    if not removed:
        _info("nothing to remove")
    print("\nConfig at ~/.gleancode/ was left untouched.\n")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install Glean Code as a CLI and (on macOS) a Spotlight-launchable app.",
    )
    parser.add_argument("--prefix", default=str(DEFAULT_PREFIX),
                        help=f"where to install the `{CLI_NAME}` executable "
                             f"(default: {_tilde(DEFAULT_PREFIX)})")
    parser.add_argument("--cli-only", action="store_true",
                        help="skip the macOS app bundle")
    parser.add_argument("--dev", action="store_true",
                        help="app launches from the working tree instead of a snapshot")
    parser.add_argument("--verify", action="store_true",
                        help="report what is currently installed and exit")
    parser.add_argument("--uninstall", action="store_true",
                        help="remove everything this script installed")
    args = parser.parse_args(argv)

    if args.uninstall:
        return do_uninstall(args)
    if args.verify:
        return do_verify(args)
    return do_install(args)


if __name__ == "__main__":
    raise SystemExit(main())

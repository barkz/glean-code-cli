"""Process control and diagnostics for the bundled MCP server.

`glean_mcp.py` normally speaks stdio and is spawned by the MCP client itself
(Claude Code, Claude Desktop, Cursor). That transport cannot be driven from
inside this REPL — the REPL already owns stdin and stdout — so `/mcp start`
runs the server over HTTP instead and records where it is listening.

Everything here is stdlib-only. The `mcp` package is never imported: the REPL
stays dependency-free, and the server runs in its own process.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import CONFIG_DIR

SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "glean_mcp.py"
STATE_PATH = CONFIG_DIR / "mcp.json"
LOG_PATH = CONFIG_DIR / "mcp.log"

DEFAULT_HOST = "127.0.0.1"   # loopback only: the server may hold live credentials
DEFAULT_PORT = 8787
DEFAULT_TRANSPORT = "streamable-http"
TRANSPORTS = ("stdio", "sse", "streamable-http")

# glean_mcp.py imports mcp.server.fastmcp, removed in mcp 2.0.0.
REQUIRED_MCP = "mcp[cli]>=1,<2"


# -------------------- package diagnostics --------------------

def mcp_package() -> Tuple[Optional[str], bool]:
    """Return (version, compatible) for the installed mcp package.

    Version is None when the package isn't importable at all. `compatible`
    means this interpreter can actually run the server — the v1 line provides
    mcp.server.fastmcp, v2 renamed it to MCPServer.
    """
    try:
        import mcp  # noqa: F401
    except ImportError:
        return None, False
    try:
        from importlib.metadata import version
        found = version("mcp")
    except Exception:
        found = "unknown"
    try:
        import mcp.server.fastmcp  # noqa: F401
        return found, True
    except ImportError:
        return found, False


# -------------------- state file --------------------

def read_state() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return None


def write_state(state: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def clear_state() -> None:
    try:
        STATE_PATH.unlink()
    except OSError:
        pass


# -------------------- process checks --------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # alive, owned by someone else
    except OSError:
        return False
    return True


def _pid_is_ours(pid: int) -> bool:
    """Guard against PID reuse by confirming the process is our server."""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return True   # can't check — trust the pid rather than lie about it
    if out.returncode != 0:
        return False
    return "glean_mcp" in out.stdout


def running() -> Optional[Dict[str, Any]]:
    """Return the live server's state, or None. Clears a stale state file."""
    state = read_state()
    if not state:
        return None
    pid = state.get("pid")
    if not isinstance(pid, int) or not _pid_alive(pid) or not _pid_is_ours(pid):
        clear_state()
        return None
    return state


# -------------------- lifecycle --------------------

def start(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          transport: str = DEFAULT_TRANSPORT,
          mock: bool = False) -> Dict[str, Any]:
    """Spawn the server detached and record where it landed.

    Raises RuntimeError with a user-facing message on any refusal.
    """
    if transport not in TRANSPORTS:
        raise RuntimeError(f"unknown transport '{transport}'. "
                           f"Choose one of: {', '.join(TRANSPORTS)}")
    if transport == "stdio":
        raise RuntimeError(
            "stdio can't be started from the REPL — it is the transport the MCP "
            "client spawns for itself. Use streamable-http or sse here, or wire "
            "the stdio command into your client with /mcp config."
        )
    existing = running()
    if existing:
        raise RuntimeError(f"already running on {existing.get('url')} "
                           f"(pid {existing.get('pid')}). Stop it first.")
    if not SERVER_SCRIPT.exists():
        raise RuntimeError(f"server script not found: {SERVER_SCRIPT}")

    version, compatible = mcp_package()
    if version is None:
        raise RuntimeError(f'the mcp package is not installed. pip install "{REQUIRED_MCP}"')
    if not compatible:
        raise RuntimeError(
            f"mcp {version} does not provide mcp.server.fastmcp (removed in 2.0.0). "
            f'Pin the v1 line: pip install "{REQUIRED_MCP}"'
        )

    env = dict(os.environ)
    if mock:
        env["GLEAN_MOCK"] = "1"

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "ab", buffering=0)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT),
             "--transport", transport, "--host", host, "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True, env=env,
        )
    except OSError as e:
        log.close()
        raise RuntimeError(f"could not start the server: {e}") from None

    path = "/mcp" if transport == "streamable-http" else "/sse"
    state = {
        "pid": proc.pid,
        "transport": transport,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}{path}",
        "started_at": int(time.time()),
        "mock": bool(mock),
        "log": str(LOG_PATH),
    }

    # Give it a moment to bind; a port clash dies immediately and silently.
    time.sleep(0.6)
    if proc.poll() is not None:
        clear_state()
        raise RuntimeError(
            f"the server exited immediately (code {proc.returncode}). "
            f"Port {port} may be in use — see {LOG_PATH}"
        )
    write_state(state)
    return state


def stop(timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Terminate the running server. Returns its state, or None if not running."""
    state = running()
    if not state:
        clear_state()
        return None
    pid = int(state["pid"])
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        clear_state()
        return state

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    clear_state()
    return state


def uptime(state: Dict[str, Any]) -> str:
    started = state.get("started_at")
    if not isinstance(started, int):
        return "unknown"
    secs = max(0, int(time.time()) - started)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


# -------------------- client configuration --------------------

CLIENTS = {
    "claude-code": "`.claude/settings.json` in the project, or ~/.claude/settings.json",
    "claude-desktop": "~/Library/Application Support/Claude/claude_desktop_config.json",
    "cursor": "`.cursor/mcp.json` in the project",
}


DEFAULT_SERVER_NAME = "glean"


def client_config(url: Optional[str] = None,
                  name: str = DEFAULT_SERVER_NAME) -> Dict[str, Any]:
    """The JSON block to paste into an MCP client.

    With a url, emits the URL form for a server already listening (what
    /mcp start produces). Without one, emits the stdio command form the
    client spawns for itself — the normal setup.

    `name` is the key under mcpServers. It matters: Glean's own hosted MCP
    server is a different server that would naturally be registered under
    "glean" too, and pasting over that entry silently swaps the toolset.
    """
    if url:
        entry: Dict[str, Any] = {"type": "http", "url": url}
    else:
        entry = {"command": sys.executable, "args": [str(SERVER_SCRIPT)]}
    return {"mcpServers": {name: entry}}


def tool_names() -> List[str]:
    """The tools the server exposes. Kept in sync with glean_mcp.py by test."""
    return ["search", "chat", "list_agents", "run_agent"]

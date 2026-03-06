"""
Install and init commands for blindfold-env.

``blindfold install`` — global installation (registers MCP server, deny patterns)
``blindfold init``    — per-project setup (deny patterns + .env creation)

Both commands are idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DENY_PATTERNS: List[str] = [
    "Read(.env*)",
    "Edit(.env*)",
    "Write(.env*)",
    "Bash(cat *.env*)",
    "Bash(head *.env*)",
    "Bash(tail *.env*)",
    "Bash(less *.env*)",
    "Bash(more *.env*)",
    "Bash(grep * .env*)",
    "Bash(sed * .env*)",
    "Bash(awk * .env*)",
]

_MCP_SERVER_ENTRY: Dict[str, Any] = {
    "command": "blindfold",
    "args": ["mcp-server"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_deny_patterns(path: Path) -> bool:
    """Merge blindfold deny patterns into a settings.json file.

    Creates the file (and parent directories) if it does not exist.
    Returns True if the file was modified, False if all patterns were
    already present.
    """
    data: Dict[str, Any] = {}
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        if raw.strip():
            data = json.loads(raw)

    permissions = data.setdefault("permissions", {})
    deny_list: List[str] = permissions.setdefault("deny", [])

    existing_set = set(deny_list)
    new_patterns = [p for p in _DENY_PATTERNS if p not in existing_set]

    if not new_patterns:
        return False

    deny_list.extend(new_patterns)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def _register_mcp_server(path: Path, entry: Dict[str, Any] | None = None) -> bool:
    """Register blindfold MCP server in ~/.claude.json.

    Merges the server entry under mcpServers.blindfold.
    Returns True if the file was modified, False if already registered.
    """
    if entry is None:
        entry = _MCP_SERVER_ENTRY

    data: Dict[str, Any] = {}
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        if raw.strip():
            data = json.loads(raw)

    mcp_servers = data.setdefault("mcpServers", {})

    if "blindfold" in mcp_servers:
        return False

    mcp_servers["blindfold"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.command("install")
@click.option("--remote", default=None, metavar="USER@HOST",
              help="SSH remote host (e.g. user@myserver). Registers MCP server with port forwarding.")
@click.option("--port", default=19876, show_default=True,
              help="Local port for the browser form (used with --remote).")
def install(remote: str | None, port: int) -> None:
    """Install blindfold globally (~/.claude.json + ~/.claude/settings.json)."""
    home = Path.home()
    actions: List[str] = []

    # 1. Register MCP server in ~/.claude.json
    claude_json = home / ".claude.json"
    if remote:
        mcp_entry: Dict[str, Any] = {
            "command": "ssh",
            "args": [f"-L{port}:localhost:{port}", remote, "blindfold", "mcp-server"],
        }
    else:
        mcp_entry = _MCP_SERVER_ENTRY

    if _register_mcp_server(claude_json, mcp_entry):
        if remote:
            actions.append(
                f"MCP server registered in {claude_json} (SSH: localhost:{port} → {remote})"
            )
        else:
            actions.append(f"MCP server registered in {claude_json}")
    else:
        actions.append(f"MCP server already registered in {claude_json} (skipped)")

    # 2. Merge deny patterns into ~/.claude/settings.json
    settings = home / ".claude" / "settings.json"
    if _merge_deny_patterns(settings):
        actions.append(f"Deny patterns merged into {settings}")
    else:
        actions.append(f"Deny patterns already present in {settings} (skipped)")

    # Summary
    click.echo("blindfold install complete:")
    for action in actions:
        click.echo(f"  {action}")
    click.echo()
    click.echo("Restart Claude Code to activate tools.")
    click.echo()

    if remote:
        click.echo(
            f"When blindfold_set is called, open http://localhost:{port}/<token> in your browser."
        )
        click.echo(
            "All traffic is encrypted through the SSH tunnel — the secret never touches the network."
        )
        click.echo()
        click.echo("Tip: for a native GUI dialog instead of the browser form, run:")
        click.echo("  blindfold agent  (on your local machine)")
        click.echo("and reinstall with --agent flag.")
    else:
        click.echo("Tools: blindfold_list, blindfold_get, blindfold_set, blindfold_delete, blindfold_rename")
        click.echo()
        click.echo("For Cursor: add to .cursor/mcp.json:")
        click.echo('  {"mcpServers":{"blindfold":{"command":"blindfold","args":["mcp-server"]}}}')


@click.command("init")
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize blindfold in the current project directory."""
    project_dir = Path.cwd()
    env_name = ctx.obj.get("env_name") if ctx.obj else None
    actions: List[str] = []

    # 1. Merge deny patterns into .claude/settings.json
    settings = project_dir / ".claude" / "settings.json"
    if _merge_deny_patterns(settings):
        actions.append(f"Merged deny patterns into {settings}")
    else:
        actions.append(f"Deny patterns already present in {settings} (skipped)")

    # 2. Create .env file(s) if they don't exist
    if env_name:
        env_path = project_dir / f".env.{env_name}"
    else:
        env_path = project_dir / ".env"

    if not env_path.exists():
        env_path.touch()
        actions.append(f"Created {env_path}")
    else:
        actions.append(f"{env_path} already exists (skipped)")

    # Summary
    click.echo("blindfold init complete:")
    for action in actions:
        click.echo(f"  {action}")

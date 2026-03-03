"""
Install and init commands for blindfold-env.

``blindfold install`` — global installation (writes to ~/.claude/)
``blindfold init``    — per-project setup (writes to current directory)

Both commands are idempotent: they detect the "blindfold-env" marker in
CLAUDE.md files and avoid duplicating content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import click

# ---------------------------------------------------------------------------
# Marker used to detect whether blindfold rules have already been injected.
# ---------------------------------------------------------------------------
_MARKER = "blindfold-env"

# ---------------------------------------------------------------------------
# Template content — stored as string constants to avoid path resolution
# issues between editable installs, wheels, etc.
# ---------------------------------------------------------------------------

_CLAUDE_MD_RULES = """\

## Secret Management — MANDATORY RULES (blindfold-env)
- NEVER read .env files directly (cat, head, Read tool, grep on .env, etc.)
- NEVER write to .env files directly (echo >>, Edit tool, Write tool, etc.)
- ALL .env interactions MUST go through the `blindfold` CLI tool
- When a user wants to set a secret: `blindfold set <KEY_NAME>`
- To check what keys exist: `blindfold list`
- To see a masked value: `blindfold get <KEY_NAME>`
"""

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

_SKILL_CONTENT = """\
---
name: blindfold
description: Manage .env secrets without exposing values to AI assistants
---

# blindfold — Secret Management

Use the `blindfold` CLI to manage .env files. NEVER read or write .env files directly.

## Commands
- `blindfold set <KEY>` — Set a secret (prompts user via /dev/tty)
- `blindfold set <KEY> --clipboard` — Set from clipboard
- `blindfold get <KEY>` — Show masked value
- `blindfold list` — List all key names
- `blindfold delete <KEY>` — Remove a key
- `blindfold rename <OLD> <NEW>` — Rename a key
- `blindfold copy <KEY> <NEW_KEY>` — Duplicate a value
- `blindfold import <FILE>` — Bulk import from another .env
- `blindfold --env production <command>` — Target .env.production
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append_rules_to_claude_md(path: Path) -> bool:
    """Append blindfold rules to a CLAUDE.md file.

    Creates the file if it does not exist.  Skips if the marker is already
    present.  Returns True if the file was modified, False if skipped.
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if _MARKER in existing:
            return False
    else:
        existing = ""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_CLAUDE_MD_RULES)
    return True


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


def _create_skill_file(path: Path) -> bool:
    """Create the blindfold skill file.

    Returns True if the file was created, False if it already exists.
    """
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SKILL_CONTENT, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.command("install")
def install() -> None:
    """Install blindfold rules globally (~/.claude/)."""
    home = Path.home()
    claude_dir = home / ".claude"
    actions: List[str] = []

    # 1. Append rules to ~/.claude/CLAUDE.md
    claude_md = claude_dir / "CLAUDE.md"
    if _append_rules_to_claude_md(claude_md):
        actions.append(f"Appended rules to {claude_md}")
    else:
        actions.append(f"Rules already present in {claude_md} (skipped)")

    # 2. Merge deny patterns into ~/.claude/settings.json
    settings = claude_dir / "settings.json"
    if _merge_deny_patterns(settings):
        actions.append(f"Merged deny patterns into {settings}")
    else:
        actions.append(f"Deny patterns already present in {settings} (skipped)")

    # 3. Create skill file
    skill_path = claude_dir / "skills" / "blindfold" / "SKILL.md"
    if _create_skill_file(skill_path):
        actions.append(f"Created skill file at {skill_path}")
    else:
        actions.append(f"Skill file already exists at {skill_path} (skipped)")

    # Summary
    click.echo("blindfold install complete:")
    for action in actions:
        click.echo(f"  {action}")


@click.command("init")
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize blindfold in the current project directory."""
    project_dir = Path.cwd()
    env_name = ctx.obj.get("env_name") if ctx.obj else None
    actions: List[str] = []

    # 1. Append rules to project CLAUDE.md
    claude_md = project_dir / "CLAUDE.md"
    if _append_rules_to_claude_md(claude_md):
        actions.append(f"Appended rules to {claude_md}")
    else:
        actions.append(f"Rules already present in {claude_md} (skipped)")

    # 2. Merge deny patterns into .claude/settings.json
    settings = project_dir / ".claude" / "settings.json"
    if _merge_deny_patterns(settings):
        actions.append(f"Merged deny patterns into {settings}")
    else:
        actions.append(f"Deny patterns already present in {settings} (skipped)")

    # 3. Create .env file(s) if they don't exist
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

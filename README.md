# blindfold-env

Manage `.env` secrets from the CLI — without ever printing values where an AI assistant can see them.

## What it is

AI coding assistants (Claude Code, Copilot, Cursor, etc.) can read files in your project. That includes `.env` files. `blindfold` intercepts all `.env` interactions and routes them through a CLI that reads secrets via `/dev/tty` or the system clipboard — bypassing the assistant's context entirely. When installed, it also injects rules into Claude's `CLAUDE.md` and `settings.json` so the assistant actively refuses to read or write `.env` files directly.

## Installation

```bash
pip install blindfold-env

# Install global Claude Code rules (~/.claude/)
blindfold install

# Initialize in the current project
blindfold init
```

`blindfold install` writes to `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, and creates a Claude skill file. `blindfold init` does the same in the current project directory and creates a `.env` file if one doesn't exist. Both commands are idempotent.

## Quick start

```bash
# Set a secret (prompts via /dev/tty — not visible to AI)
blindfold set DB_PASSWORD

# Set from clipboard
blindfold set API_KEY --clipboard

# Show a masked value (safe to share)
blindfold get DB_PASSWORD
# DB_PASSWORD=mySu...word

# List all key names
blindfold list
# DB_PASSWORD
# API_KEY
```

## Commands reference

| Command | Description |
|---------|-------------|
| `blindfold set <KEY>` | Set a secret value (prompts via `/dev/tty`) |
| `blindfold set <KEY> --clipboard` | Set a secret from the system clipboard |
| `blindfold get <KEY>` | Show a masked value (first 4 + `...` + last 4 chars) |
| `blindfold list` | List all key names in the `.env` file |
| `blindfold delete <KEY>` | Remove a key |
| `blindfold rename <OLD> <NEW>` | Rename a key in place |
| `blindfold copy <KEY> <NEW_KEY>` | Duplicate a key's value to a new key |
| `blindfold import <FILE>` | Bulk-import keys from another `.env` file |
| `blindfold install` | Install global Claude Code rules |
| `blindfold init` | Initialize blindfold in the current project |

All commands accept a `--env <NAME>` flag to target `.env.<NAME>` instead of `.env`:

```bash
blindfold --env production set DB_URL
blindfold --env production list
```

### import options

```bash
# Import all keys, overwriting existing ones
blindfold import staging.env

# Skip keys that already exist in the target
blindfold import staging.env --no-overwrite
```

## Claude Code integration

### `blindfold install`

Runs once after `pip install`. Modifies files in `~/.claude/`:

- **`CLAUDE.md`** — Appends mandatory rules telling the assistant to never read/write `.env` files directly and to always use `blindfold` commands instead.
- **`settings.json`** — Merges a `permissions.deny` list that blocks tool calls matching `.env*` file patterns (`Read`, `Edit`, `Write`, `Bash cat/head/tail/grep/sed/awk`).
- **`skills/blindfold/SKILL.md`** — Creates a skill file so you can invoke `/blindfold` in the Claude Code chat.

### `blindfold init`

Runs once per project. Writes the same rules to the project directory:

- **`CLAUDE.md`** — Project-level rules (supplement or replace global rules).
- **`.claude/settings.json`** — Project-level deny patterns.
- **`.env`** — Creates an empty file if one doesn't exist (or `.env.<NAME>` with `--env`).

Both commands are idempotent: they detect an existing `blindfold-env` marker and skip sections that are already configured.

## How it works

**Secret input** — `blindfold set` opens `/dev/tty` directly via `getpass`, bypassing stdout/stdin and any pipe that an AI assistant might intercept. The `--clipboard` flag reads from the OS clipboard using `pbpaste` (macOS), `powershell.exe Get-Clipboard` (Windows/WSL), `xclip`, or `xsel` (Linux).

**File I/O** — `.env` files are read and written atomically (write to a temp file, then replace). Comments and blank lines are preserved on every update. File locking prevents corruption from concurrent writes.

**Masking** — `blindfold get` never prints a full value. Values of 8 characters or fewer show as `****`. Longer values show the first 4 and last 4 characters with `...` in between.

**Rules enforcement** — The `settings.json` deny list uses Claude Code's built-in permission system to block the assistant from calling file-reading tools on `.env*` patterns, even if it tries to bypass the `CLAUDE.md` instructions.

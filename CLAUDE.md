# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands require the venv to be active:

```bash
source .venv/bin/activate
```

**Run tests:**
```bash
pytest tests/                          # all 151 tests
pytest tests/test_cli.py -v            # CLI tests only
pytest tests/test_env_file.py::TestSetValue -v  # single class
pytest tests/test_cli.py -k "mask"     # by keyword
```

**Install in editable mode (required before first use):**
```bash
pip install -e .
```

**Run the CLI:**
```bash
blindfold --help
blindfold --env production list
```

## Architecture

Four modules in `src/blindfold/`:

**`env_file.py`** — all `.env` file I/O. The core data structure is `_ParsedLine = Union[str, Tuple[str, str, str]]`: comment/blank lines are stored as plain strings; key-value lines as `(key, unquoted_value, raw_line_text)` tuples. Every write operation parses the file into this list, mutates it, and serializes back — preserving comments, blank lines, and ordering. Writes use `fcntl.flock` for exclusive locking. `set_value` updates the *first* occurrence of a duplicate key; `read_value` returns the *last*.

**`secret_input.py`** — two input paths that avoid stdout: `get_secret_from_tty` uses `getpass.getpass` (reads from `/dev/tty` directly, not stdin), and `get_secret_from_clipboard` dispatches to `pbpaste` / `powershell.exe` / `xclip` / `xsel` based on `sys.platform` and WSL detection via `/proc/version`.

**`cli.py`** — Click command group. The `--env` flag is stored in `ctx.obj["env_name"]` and passed down to all subcommands via `@click.pass_context`. Secret values are never printed; `_mask_value` shows `****` for ≤8 chars or `first4...last4` for longer values. `install` and `init` are defined in `installer.py` and registered here via `cli.add_command()`.

**`installer.py`** — idempotency is handled by checking for the string `"blindfold-env"` (the `_MARKER`) in `CLAUDE.md` files before appending, and by set-diffing existing deny patterns before merging into `settings.json`. All template content is embedded as string constants (not external files) to avoid packaging path issues.

## Testing patterns

- CLI commands: `CliRunner` + `runner.isolated_filesystem()` so relative `.env` paths resolve correctly
- `install` command: `@patch('pathlib.Path.home', return_value=tmp_path)` to redirect `~/.claude/` writes
- TTY/clipboard mocking: patch `blindfold.cli.get_secret_from_tty` or `blindfold.cli.get_secret_from_clipboard` (not the `secret_input` module directly, since they're imported by name into `cli.py`)
- Internal helpers (`_append_rules_to_claude_md`, etc.) are tested directly alongside the CLI integration tests

## Key constraints

- `fcntl` is Linux/macOS only — `env_file.py` will not work on Windows as-is
- The `--env` flag must come *before* the subcommand: `blindfold --env prod list`, not `blindfold list --env prod`
- `set_value` creates the file and any parent directories automatically; all other write operations raise `FileNotFoundError` if the file is missing

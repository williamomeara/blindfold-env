"""
CLI entry point for blindfold-env.

Provides commands for managing secrets in .env files without ever
printing secret values to stdout (where an AI assistant could read them).
"""

from __future__ import annotations

from pathlib import Path

import click

from blindfold import env_file
from blindfold.installer import init, install
from blindfold.secret_input import (
    get_secret_from_clipboard,
    get_secret_from_gui,
    get_secret_from_tty,
)


def _validate_key_name(key: str) -> None:
    """Validate a key name, converting ValueError to click.ClickException."""
    try:
        env_file.validate_key(key)
    except ValueError as exc:
        raise click.ClickException(str(exc))


def _resolve(ctx: click.Context) -> Path:
    """Resolve the .env file path from the Click context."""
    env_name = ctx.obj["env_name"]
    return env_file.resolve_path(env_name)


def _env_filename(ctx: click.Context) -> str:
    """Return the display filename (e.g. '.env' or '.env.production')."""
    env_name = ctx.obj["env_name"]
    if env_name:
        return f".env.{env_name}"
    return ".env"


def _mask_value(value: str) -> str:
    """Mask a secret value for display.

    If the value is 8 characters or fewer, returns "****".
    Otherwise returns the first 4 characters + "..." + last 4 characters.
    """
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option(
    "--env",
    "env_name",
    default=None,
    help='Environment name (e.g. "production" for .env.production). '
         "Defaults to .env.",
)
@click.pass_context
def cli(ctx: click.Context, env_name: str | None) -> None:
    """Manage .env secrets without exposing values."""
    ctx.ensure_object(dict)
    ctx.obj["env_name"] = env_name


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

@cli.command("set")
@click.argument("key")
@click.option("--clipboard", is_flag=True, help="Read the secret from the system clipboard.")
@click.option("--tty", is_flag=True, help="Read the secret interactively from the terminal (TTY).")
@click.pass_context
def set_key(ctx: click.Context, key: str, clipboard: bool, tty: bool) -> None:
    """Set a secret value for KEY."""
    _validate_key_name(key)

    if clipboard and tty:
        raise click.UsageError("--clipboard and --tty are mutually exclusive.")

    if clipboard:
        value = get_secret_from_clipboard()
    elif tty:
        value = get_secret_from_tty(f"Secret value for {key}: ")
    else:
        value = get_secret_from_gui(key, Path.cwd().name)

    path = _resolve(ctx)
    env_file.set_value(path, key, value)
    click.echo(f"Set {key} in {_env_filename(ctx)}")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@cli.command("get")
@click.argument("key")
@click.pass_context
def get_key(ctx: click.Context, key: str) -> None:
    """Show a masked version of a secret value."""
    _validate_key_name(key)
    path = _resolve(ctx)

    try:
        value = env_file.read_value(path, key)
    except FileNotFoundError:
        raise click.ClickException(f"{_env_filename(ctx)} not found")

    if value is None:
        raise click.ClickException(f"Key {key!r} not found in {_env_filename(ctx)}")

    click.echo(f"{key}={_mask_value(value)}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.pass_context
def list_keys(ctx: click.Context) -> None:
    """List all keys in the .env file."""
    path = _resolve(ctx)

    try:
        keys = env_file.read_keys(path)
    except FileNotFoundError:
        raise click.ClickException(f"{_env_filename(ctx)} not found")

    if not keys:
        click.echo("(empty)")
        return

    for key in keys:
        click.echo(key)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@cli.command("delete")
@click.argument("key")
@click.pass_context
def delete(ctx: click.Context, key: str) -> None:
    """Delete KEY from the .env file."""
    _validate_key_name(key)
    path = _resolve(ctx)

    try:
        env_file.delete_key(path, key)
    except FileNotFoundError:
        raise click.ClickException(f"{_env_filename(ctx)} not found")
    except KeyError:
        raise click.ClickException(f"Key {key!r} not found in {_env_filename(ctx)}")

    click.echo(f"Deleted {key} from {_env_filename(ctx)}")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

@cli.command("rename")
@click.argument("old")
@click.argument("new")
@click.pass_context
def rename(ctx: click.Context, old: str, new: str) -> None:
    """Rename OLD key to NEW key."""
    _validate_key_name(old)
    _validate_key_name(new)
    path = _resolve(ctx)

    try:
        env_file.rename_key(path, old, new)
    except FileNotFoundError:
        raise click.ClickException(f"{_env_filename(ctx)} not found")
    except KeyError:
        raise click.ClickException(f"Key {old!r} not found in {_env_filename(ctx)}")

    click.echo(f"Renamed {old} to {new} in {_env_filename(ctx)}")


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------

@cli.command("copy")
@click.argument("key")
@click.argument("new_key")
@click.pass_context
def copy(ctx: click.Context, key: str, new_key: str) -> None:
    """Copy KEY's value to NEW_KEY."""
    _validate_key_name(key)
    _validate_key_name(new_key)
    path = _resolve(ctx)

    try:
        env_file.copy_key(path, key, new_key)
    except FileNotFoundError:
        raise click.ClickException(f"{_env_filename(ctx)} not found")
    except KeyError:
        raise click.ClickException(f"Key {key!r} not found in {_env_filename(ctx)}")

    click.echo(f"Copied {key} to {new_key} in {_env_filename(ctx)}")


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@cli.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--no-overwrite",
    is_flag=True,
    help="Skip keys that already exist in the target file.",
)
@click.pass_context
def import_env(ctx: click.Context, file: str, no_overwrite: bool) -> None:
    """Import keys from another .env FILE."""
    source_path = Path(file)
    target_path = _resolve(ctx)

    try:
        source_keys = env_file.read_keys(source_path)
    except FileNotFoundError:
        raise click.ClickException(f"Source file {file!r} not found")

    # Read existing keys in target (if any) for --no-overwrite logic
    existing_keys: set[str] = set()
    if no_overwrite and target_path.exists():
        try:
            existing_keys = set(env_file.read_keys(target_path))
        except FileNotFoundError:
            pass

    imported = []
    skipped = []

    for key in source_keys:
        if no_overwrite and key in existing_keys:
            skipped.append(key)
            continue

        value = env_file.read_value(source_path, key)
        if value is not None:
            env_file.set_value(target_path, key, value)
            imported.append(key)

    filename = _env_filename(ctx)
    click.echo(f"Imported {len(imported)} key(s) into {filename}")
    if skipped:
        click.echo(f"Skipped {len(skipped)} existing key(s): {', '.join(skipped)}")


# ---------------------------------------------------------------------------
# mcp-server
# ---------------------------------------------------------------------------

@cli.command("mcp-server")
def mcp_server_cmd() -> None:
    """Start the blindfold MCP server (stdio transport)."""
    from blindfold.mcp_server import main
    main()


# ---------------------------------------------------------------------------
# install / init (defined in installer.py, registered here)
# ---------------------------------------------------------------------------

cli.add_command(install)
cli.add_command(init)

"""
Core .env file I/O operations for blindfold-env.

Handles parsing, reading, and writing .env files with support for:
- KEY=value pairs
- Comments (# ...) and blank lines
- Quoted values (single and double quotes)
- Multiline values (double-quoted)
- File locking for safe concurrent writes
"""

from __future__ import annotations

import fcntl
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

# Valid key pattern: starts with letter or underscore, then alphanumerics/underscores
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Matches a KEY=value line (key capture, then everything after '=')
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)")

# Internal representation of a parsed line:
#   - Comment/blank: stored as a plain string
#   - Key-value: stored as a tuple (key, unquoted_value, raw_line_text)
_ParsedLine = Union[str, Tuple[str, str, str]]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_key(key: str) -> None:
    """Validate that *key* is a legal .env variable name.

    Raises ``ValueError`` if the key does not match ``^[A-Za-z_][A-Za-z0-9_]*$``.
    """
    if not _KEY_RE.match(key):
        raise ValueError(
            f"Invalid key {key!r}: must match [A-Za-z_][A-Za-z0-9_]*"
        )


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_path(
    env_name: Optional[str] = None,
    directory: Union[str, Path] = ".",
) -> Path:
    """Return the resolved path to a .env file.

    If *env_name* is ``None`` (or empty), returns ``<directory>/.env``.
    Otherwise returns ``<directory>/.env.<env_name>``.
    """
    directory = Path(directory)
    if env_name:
        return directory / f".env.{env_name}"
    return directory / ".env"


# ---------------------------------------------------------------------------
# Parsing internals
# ---------------------------------------------------------------------------

def _unquote(raw_value: str) -> str:
    """Strip surrounding quotes from a value string and unescape if needed."""
    if len(raw_value) >= 2:
        if (raw_value[0] == '"' and raw_value[-1] == '"') or (
            raw_value[0] == "'" and raw_value[-1] == "'"
        ):
            return raw_value[1:-1]
    return raw_value


def _parse_env(text: str) -> List[_ParsedLine]:
    """Parse the full text of a .env file into a list of parsed lines.

    Each element is either:
    - A plain ``str`` for comment / blank lines (preserved as-is).
    - A ``(key, value, raw)`` tuple for key-value lines.

    Multiline values are supported when the value starts with a double
    quote and the closing quote appears on a subsequent line.  In that
    case the tuple's *raw* field contains all the original lines joined
    by ``\\n``.
    """
    lines: List[_ParsedLine] = []
    raw_lines = text.split("\n")
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        stripped = line.strip()

        # Blank or comment
        if stripped == "" or stripped.startswith("#"):
            lines.append(line)
            i += 1
            continue

        m = _KV_RE.match(stripped)
        if not m:
            # Not a valid KV line — keep as-is (comment/junk)
            lines.append(line)
            i += 1
            continue

        key = m.group(1)
        raw_val = m.group(2)

        # Check for multiline: value starts with " but doesn't end with "
        if raw_val.startswith('"') and not _is_closed_double_quote(raw_val):
            # Accumulate lines until we find the closing "
            collected = [line]
            val_parts = [raw_val]
            i += 1
            while i < len(raw_lines):
                collected.append(raw_lines[i])
                val_parts.append(raw_lines[i])
                if raw_lines[i].rstrip().endswith('"'):
                    i += 1
                    break
                i += 1
            else:
                # Reached EOF without closing quote — treat the whole thing
                # as the value anyway (best effort).
                pass
            full_raw = "\n".join(collected)
            full_val = "\n".join(val_parts)
            # Strip the surrounding double quotes from the assembled value
            full_val = full_val.strip()
            if full_val.startswith('"') and full_val.endswith('"'):
                full_val = full_val[1:-1]
            lines.append((key, full_val, full_raw))
        else:
            value = _unquote(raw_val)
            lines.append((key, value, line))
            i += 1

    return lines


def _is_closed_double_quote(raw_val: str) -> bool:
    """Return True if *raw_val* is a properly closed double-quoted string.

    ``"hello"``  -> True
    ``"hello``   -> False
    ``hello``    -> True (not quoted at all, so not *un*closed)
    """
    if not raw_val.startswith('"'):
        return True  # not double-quoted, so "closed" trivially
    # Must have at least a closing quote beyond the opening one
    return len(raw_val) >= 2 and raw_val.endswith('"')


def _format_value(key: str, value: str) -> str:
    """Format a key-value pair as a .env line string.

    If the value contains spaces, newlines, single quotes, or double
    quotes it is wrapped in double quotes (with internal double quotes
    escaped).  Otherwise the bare value is used.
    """
    needs_quoting = any(c in value for c in (' ', '\n', '\t', '"', "'", '#'))
    if needs_quoting:
        escaped = value.replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def _serialize_lines(parsed: List[_ParsedLine]) -> str:
    """Serialize a list of parsed lines back to .env file text."""
    parts: List[str] = []
    for item in parsed:
        if isinstance(item, str):
            parts.append(item)
        else:
            _key, _val, raw = item
            parts.append(raw)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _read_parsed(path: Path) -> List[_ParsedLine]:
    """Read and parse a .env file.  Raises ``FileNotFoundError`` if missing."""
    text = path.read_text(encoding="utf-8")
    # Strip a single trailing newline so we don't create a phantom blank
    # line when we split.  We'll add it back on write.
    if text.endswith("\n"):
        text = text[:-1]
    return _parse_env(text)


def _write_parsed(path: Path, parsed: List[_ParsedLine]) -> None:
    """Write parsed lines back to *path* with an exclusive file lock."""
    content = _serialize_lines(parsed)
    if not content.endswith("\n"):
        content += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(content)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Public read operations
# ---------------------------------------------------------------------------

def read_keys(path: Union[str, Path]) -> List[str]:
    """Return a list of all key names in the .env file at *path*.

    Duplicate keys are included (order preserved).
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = Path(path)
    parsed = _read_parsed(path)
    return [item[0] for item in parsed if isinstance(item, tuple)]


def read_value(path: Union[str, Path], key: str) -> Optional[str]:
    """Return the value for *key*, or ``None`` if not found.

    If the key appears more than once, the *last* occurrence wins.
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = Path(path)
    validate_key(key)
    parsed = _read_parsed(path)
    result: Optional[str] = None
    for item in parsed:
        if isinstance(item, tuple) and item[0] == key:
            result = item[1]
    return result


# ---------------------------------------------------------------------------
# Public write operations
# ---------------------------------------------------------------------------

def set_value(path: Union[str, Path], key: str, value: str) -> None:
    """Set *key* to *value* in the .env file at *path*.

    - If the key already exists, the **first** occurrence is updated
      in-place and any subsequent duplicates are left alone.
    - If the key does not exist, a new line is appended.
    - If the file does not exist, it is created.
    - File formatting (comments, blank lines, ordering) is preserved.
    """
    path = Path(path)
    validate_key(key)

    if path.exists():
        parsed = _read_parsed(path)
    else:
        parsed = []

    new_raw = _format_value(key, value)
    updated = False
    new_parsed: List[_ParsedLine] = []
    for item in parsed:
        if isinstance(item, tuple) and item[0] == key and not updated:
            new_parsed.append((key, value, new_raw))
            updated = True
        else:
            new_parsed.append(item)

    if not updated:
        new_parsed.append((key, value, new_raw))

    _write_parsed(path, new_parsed)


def delete_key(path: Union[str, Path], key: str) -> None:
    """Remove the line for *key* from the .env file.

    Raises ``KeyError`` if the key is not found.
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = Path(path)
    validate_key(key)
    parsed = _read_parsed(path)

    new_parsed: List[_ParsedLine] = []
    found = False
    for item in parsed:
        if isinstance(item, tuple) and item[0] == key:
            found = True
            # Skip this line (delete it)
        else:
            new_parsed.append(item)

    if not found:
        raise KeyError(f"Key {key!r} not found in {path}")

    _write_parsed(path, new_parsed)


def rename_key(path: Union[str, Path], old_key: str, new_key: str) -> None:
    """Rename *old_key* to *new_key*, preserving its value and position.

    Raises ``KeyError`` if *old_key* is not found.
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = Path(path)
    validate_key(old_key)
    validate_key(new_key)
    parsed = _read_parsed(path)

    found = False
    new_parsed: List[_ParsedLine] = []
    for item in parsed:
        if isinstance(item, tuple) and item[0] == old_key and not found:
            found = True
            value = item[1]
            new_raw = _format_value(new_key, value)
            new_parsed.append((new_key, value, new_raw))
        else:
            new_parsed.append(item)

    if not found:
        raise KeyError(f"Key {old_key!r} not found in {path}")

    _write_parsed(path, new_parsed)


def copy_key(path: Union[str, Path], source_key: str, new_key: str) -> None:
    """Copy the value of *source_key* to a new line with *new_key* (appended).

    Raises ``KeyError`` if *source_key* is not found.
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = Path(path)
    validate_key(source_key)
    validate_key(new_key)
    parsed = _read_parsed(path)

    # Find source value (last occurrence wins, matching read_value semantics)
    source_value: Optional[str] = None
    for item in parsed:
        if isinstance(item, tuple) and item[0] == source_key:
            source_value = item[1]

    if source_value is None:
        raise KeyError(f"Key {source_key!r} not found in {path}")

    new_raw = _format_value(new_key, source_value)
    parsed.append((new_key, source_value, new_raw))
    _write_parsed(path, parsed)

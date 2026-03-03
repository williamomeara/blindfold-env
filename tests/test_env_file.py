"""Tests for blindfold.env_file — core .env I/O operations."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from blindfold.env_file import (
    copy_key,
    delete_key,
    read_keys,
    read_value,
    rename_key,
    resolve_path,
    set_value,
    validate_key,
    _parse_env,
    _format_value,
)


# -----------------------------------------------------------------------
# validate_key
# -----------------------------------------------------------------------

class TestValidateKey:
    def test_valid_simple(self):
        validate_key("FOO")

    def test_valid_underscore_prefix(self):
        validate_key("_MY_VAR")

    def test_valid_alphanumeric(self):
        validate_key("key123_ABC")

    def test_invalid_starts_with_digit(self):
        with pytest.raises(ValueError, match="Invalid key"):
            validate_key("1BAD")

    def test_invalid_contains_dash(self):
        with pytest.raises(ValueError, match="Invalid key"):
            validate_key("MY-VAR")

    def test_invalid_contains_dot(self):
        with pytest.raises(ValueError, match="Invalid key"):
            validate_key("MY.VAR")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid key"):
            validate_key("")

    def test_invalid_space(self):
        with pytest.raises(ValueError, match="Invalid key"):
            validate_key("MY VAR")


# -----------------------------------------------------------------------
# resolve_path
# -----------------------------------------------------------------------

class TestResolvePath:
    def test_default_env(self):
        assert resolve_path() == Path(".") / ".env"

    def test_none_env(self):
        assert resolve_path(None) == Path(".") / ".env"

    def test_empty_string_env(self):
        assert resolve_path("") == Path(".") / ".env"

    def test_named_env(self):
        assert resolve_path("production") == Path(".") / ".env.production"

    def test_custom_directory(self):
        assert resolve_path("staging", "/tmp") == Path("/tmp") / ".env.staging"

    def test_default_in_custom_dir(self):
        assert resolve_path(None, "/app") == Path("/app") / ".env"


# -----------------------------------------------------------------------
# Parsing
# -----------------------------------------------------------------------

class TestParsing:
    def test_simple_kv(self):
        parsed = _parse_env("FOO=bar")
        assert len(parsed) == 1
        key, val, raw = parsed[0]
        assert key == "FOO"
        assert val == "bar"

    def test_blank_lines_and_comments(self):
        text = textwrap.dedent("""\
            # This is a comment

            FOO=bar
            # Another comment
            BAZ=qux""")
        parsed = _parse_env(text)
        assert len(parsed) == 5
        assert parsed[0] == "# This is a comment"
        assert parsed[1] == ""
        assert parsed[2][0] == "FOO"
        assert parsed[3] == "# Another comment"
        assert parsed[4][0] == "BAZ"

    def test_double_quoted_value(self):
        parsed = _parse_env('KEY="hello world"')
        assert parsed[0][1] == "hello world"

    def test_single_quoted_value(self):
        parsed = _parse_env("KEY='hello world'")
        assert parsed[0][1] == "hello world"

    def test_unquoted_value(self):
        parsed = _parse_env("KEY=noquotes")
        assert parsed[0][1] == "noquotes"

    def test_empty_value(self):
        parsed = _parse_env("KEY=")
        assert parsed[0][1] == ""

    def test_value_with_equals(self):
        parsed = _parse_env("KEY=abc=def")
        assert parsed[0][1] == "abc=def"

    def test_multiline_value(self):
        text = 'KEY="line1\nline2\nline3"'
        parsed = _parse_env(text)
        assert len(parsed) == 1
        assert parsed[0][0] == "KEY"
        assert parsed[0][1] == "line1\nline2\nline3"

    def test_duplicate_keys(self):
        text = "KEY=first\nKEY=second"
        parsed = _parse_env(text)
        assert len(parsed) == 2
        assert parsed[0][1] == "first"
        assert parsed[1][1] == "second"


# -----------------------------------------------------------------------
# _format_value
# -----------------------------------------------------------------------

class TestFormatValue:
    def test_bare_value(self):
        assert _format_value("K", "simple") == "K=simple"

    def test_value_with_space(self):
        assert _format_value("K", "has space") == 'K="has space"'

    def test_value_with_newline(self):
        assert _format_value("K", "a\nb") == 'K="a\nb"'

    def test_empty_value(self):
        assert _format_value("K", "") == "K="


# -----------------------------------------------------------------------
# read_keys
# -----------------------------------------------------------------------

class TestReadKeys:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\nB=2\nC=3\n")
        assert read_keys(f) == ["A", "B", "C"]

    def test_with_comments(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("# comment\nA=1\n\nB=2\n")
        assert read_keys(f) == ["A", "B"]

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("")
        assert read_keys(f) == []

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_keys(tmp_path / ".env")

    def test_duplicate_keys_listed(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\nA=2\n")
        assert read_keys(f) == ["A", "A"]

    def test_accepts_str_path(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("X=1\n")
        assert read_keys(str(f)) == ["X"]


# -----------------------------------------------------------------------
# read_value
# -----------------------------------------------------------------------

class TestReadValue:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("FOO=bar\n")
        assert read_value(f, "FOO") == "bar"

    def test_not_found(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("FOO=bar\n")
        assert read_value(f, "BAZ") is None

    def test_duplicate_last_wins(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("KEY=first\nKEY=second\n")
        assert read_value(f, "KEY") == "second"

    def test_quoted_value_stripped(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text('KEY="hello world"\n')
        assert read_value(f, "KEY") == "hello world"

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_value(tmp_path / ".env", "FOO")

    def test_invalid_key_raises(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("FOO=1\n")
        with pytest.raises(ValueError):
            read_value(f, "1BAD")


# -----------------------------------------------------------------------
# set_value
# -----------------------------------------------------------------------

class TestSetValue:
    def test_create_new_file(self, tmp_path: Path):
        f = tmp_path / ".env"
        set_value(f, "NEW", "value")
        assert f.read_text() == "NEW=value\n"

    def test_append_to_existing(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        set_value(f, "B", "2")
        assert read_value(f, "A") == "1"
        assert read_value(f, "B") == "2"

    def test_update_existing_preserves_order(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("# header\nA=old\nB=keep\n")
        set_value(f, "A", "new")
        content = f.read_text()
        lines = content.strip().split("\n")
        assert lines[0] == "# header"
        assert lines[1] == "A=new"
        assert lines[2] == "B=keep"

    def test_preserves_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / ".env"
        original = "# comment\n\nKEY=val\n"
        f.write_text(original)
        set_value(f, "KEY", "updated")
        content = f.read_text()
        assert content.startswith("# comment\n\n")

    def test_value_with_spaces_quoted(self, tmp_path: Path):
        f = tmp_path / ".env"
        set_value(f, "MSG", "hello world")
        assert f.read_text() == 'MSG="hello world"\n'

    def test_update_first_occurrence_of_duplicate(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("K=first\nK=second\n")
        set_value(f, "K", "updated")
        content = f.read_text().strip().split("\n")
        assert content[0] == "K=updated"
        assert content[1] == "K=second"

    def test_invalid_key_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            set_value(tmp_path / ".env", "1BAD", "val")

    def test_creates_parent_dirs(self, tmp_path: Path):
        f = tmp_path / "sub" / "dir" / ".env"
        set_value(f, "K", "v")
        assert f.exists()
        assert read_value(f, "K") == "v"


# -----------------------------------------------------------------------
# delete_key
# -----------------------------------------------------------------------

class TestDeleteKey:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\nB=2\nC=3\n")
        delete_key(f, "B")
        assert read_keys(f) == ["A", "C"]

    def test_preserves_formatting(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("# header\nA=1\n\nB=2\n")
        delete_key(f, "A")
        content = f.read_text()
        assert "# header" in content
        assert "B=2" in content

    def test_not_found_raises(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        with pytest.raises(KeyError, match="MISSING"):
            delete_key(f, "MISSING")

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            delete_key(tmp_path / ".env", "FOO")

    def test_deletes_all_occurrences(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("K=1\nK=2\n")
        delete_key(f, "K")
        assert read_keys(f) == []


# -----------------------------------------------------------------------
# rename_key
# -----------------------------------------------------------------------

class TestRenameKey:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("OLD=value\n")
        rename_key(f, "OLD", "NEW")
        assert read_value(f, "NEW") == "value"
        assert read_value(f, "OLD") is None

    def test_preserves_position(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\nOLD=2\nC=3\n")
        rename_key(f, "OLD", "NEW")
        keys = read_keys(f)
        assert keys == ["A", "NEW", "C"]

    def test_not_found_raises(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        with pytest.raises(KeyError, match="MISSING"):
            rename_key(f, "MISSING", "NEW")

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            rename_key(tmp_path / ".env", "A", "B")

    def test_invalid_old_key(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        with pytest.raises(ValueError):
            rename_key(f, "1BAD", "GOOD")

    def test_invalid_new_key(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        with pytest.raises(ValueError):
            rename_key(f, "A", "1BAD")


# -----------------------------------------------------------------------
# copy_key
# -----------------------------------------------------------------------

class TestCopyKey:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("SRC=hello\n")
        copy_key(f, "SRC", "DST")
        assert read_value(f, "DST") == "hello"
        assert read_value(f, "SRC") == "hello"

    def test_appended_at_end(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\nSRC=val\nB=2\n")
        copy_key(f, "SRC", "DST")
        keys = read_keys(f)
        assert keys[-1] == "DST"

    def test_not_found_raises(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("A=1\n")
        with pytest.raises(KeyError, match="MISSING"):
            copy_key(f, "MISSING", "NEW")

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            copy_key(tmp_path / ".env", "A", "B")


# -----------------------------------------------------------------------
# Round-trip / integration tests
# -----------------------------------------------------------------------

class TestRoundTrip:
    def test_full_workflow(self, tmp_path: Path):
        """Create, read, update, rename, copy, delete — full lifecycle."""
        f = tmp_path / ".env"

        # Create via set
        set_value(f, "DB_HOST", "localhost")
        set_value(f, "DB_PORT", "5432")
        set_value(f, "SECRET", "s3cret")

        assert read_keys(f) == ["DB_HOST", "DB_PORT", "SECRET"]
        assert read_value(f, "DB_PORT") == "5432"

        # Update
        set_value(f, "DB_PORT", "3306")
        assert read_value(f, "DB_PORT") == "3306"

        # Rename
        rename_key(f, "SECRET", "API_SECRET")
        assert read_value(f, "API_SECRET") == "s3cret"

        # Copy
        copy_key(f, "DB_HOST", "DB_HOST_BACKUP")
        assert read_value(f, "DB_HOST_BACKUP") == "localhost"

        # Delete
        delete_key(f, "DB_HOST_BACKUP")
        assert read_value(f, "DB_HOST_BACKUP") is None

        # Final state
        assert read_keys(f) == ["DB_HOST", "DB_PORT", "API_SECRET"]

    def test_multiline_roundtrip(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text('KEY="line1\nline2"\n')
        assert read_value(f, "KEY") == "line1\nline2"

    def test_preserves_complex_file(self, tmp_path: Path):
        original = textwrap.dedent("""\
            # Database config
            DB_HOST=localhost
            DB_PORT=5432

            # App secrets
            SECRET_KEY=abc123

            # Feature flags
            ENABLE_CACHE=true
        """)
        f = tmp_path / ".env"
        f.write_text(original)

        set_value(f, "DB_PORT", "3306")
        content = f.read_text()

        # Comments still present
        assert "# Database config" in content
        assert "# App secrets" in content
        assert "# Feature flags" in content

        # Updated value
        assert "DB_PORT=3306" in content

        # Other values untouched
        assert "DB_HOST=localhost" in content
        assert "SECRET_KEY=abc123" in content
        assert "ENABLE_CACHE=true" in content

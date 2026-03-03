"""Tests for blindfold.cli — Click CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from blindfold.cli import cli, _mask_value


# -----------------------------------------------------------------------
# _mask_value helper
# -----------------------------------------------------------------------

class TestMaskValue:
    def test_empty_value_masked(self):
        assert _mask_value("") == "****"

    def test_short_value_masked(self):
        assert _mask_value("abc") == "****"

    def test_exactly_8_chars_masked(self):
        assert _mask_value("12345678") == "****"

    def test_9_chars_shows_partial(self):
        # "123456789" (9) -> "1234...6789"
        assert _mask_value("123456789") == "1234...6789"

    def test_long_value_shows_partial(self):
        # "abcdefghij" (10) -> "abcd...ghij"
        assert _mask_value("abcdefghij") == "abcd...ghij"

    def test_secret_not_fully_visible(self):
        result = _mask_value("mysupersecrettoken")
        assert "mysupersecrettoken" not in result
        assert "..." in result


# -----------------------------------------------------------------------
# set
# -----------------------------------------------------------------------

class TestCliSet:
    def test_tty_path(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with patch("blindfold.cli.get_secret_from_tty", return_value="mysecret"):
                result = runner.invoke(cli, ["set", "MY_KEY"])
        assert result.exit_code == 0
        assert "Set MY_KEY" in result.output

    def test_clipboard_path(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with patch("blindfold.cli.get_secret_from_clipboard", return_value="clipval"):
                result = runner.invoke(cli, ["set", "CLIP_KEY", "--clipboard"])
        assert result.exit_code == 0
        assert "Set CLIP_KEY" in result.output

    def test_set_writes_to_env_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            with patch("blindfold.cli.get_secret_from_tty", return_value="val123"):
                runner.invoke(cli, ["set", "DB_HOST"])
            env_path = Path(td) / ".env"
            assert env_path.exists()

    def test_invalid_key_name_fails(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["set", "1INVALID"])
        assert result.exit_code != 0

    def test_env_flag_routes_to_named_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            with patch("blindfold.cli.get_secret_from_tty", return_value="prodval"):
                result = runner.invoke(cli, ["--env", "production", "set", "API_KEY"])
        assert result.exit_code == 0
        assert ".env.production" in result.output


# -----------------------------------------------------------------------
# get
# -----------------------------------------------------------------------

class TestCliGet:
    def test_masked_output(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("MY_KEY=supersecretvalue\n")
            result = runner.invoke(cli, ["get", "MY_KEY"])
        assert result.exit_code == 0
        assert "MY_KEY=" in result.output
        assert "supersecretvalue" not in result.output

    def test_short_value_fully_masked(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("TOKEN=abc\n")
            result = runner.invoke(cli, ["get", "TOKEN"])
        assert result.exit_code == 0
        assert "****" in result.output

    def test_key_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("OTHER=val\n")
            result = runner.invoke(cli, ["get", "MISSING"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_file_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["get", "MY_KEY"])
        assert result.exit_code != 0

    def test_env_flag(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env.production").write_text("DB_URL=postgres://host/db\n")
            result = runner.invoke(cli, ["--env", "production", "get", "DB_URL"])
        assert result.exit_code == 0
        assert "DB_URL=" in result.output


# -----------------------------------------------------------------------
# list
# -----------------------------------------------------------------------

class TestCliList:
    def test_keys_listed(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\nB=2\nC=3\n")
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "A" in result.output
        assert "B" in result.output
        assert "C" in result.output

    def test_empty_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("")
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "(empty)" in result.output

    def test_file_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["list"])
        assert result.exit_code != 0

    def test_env_flag(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env.staging").write_text("STAGE_KEY=1\n")
            result = runner.invoke(cli, ["--env", "staging", "list"])
        assert result.exit_code == 0
        assert "STAGE_KEY" in result.output


# -----------------------------------------------------------------------
# delete
# -----------------------------------------------------------------------

class TestCliDelete:
    def test_success(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("MY_KEY=val\n")
            result = runner.invoke(cli, ["delete", "MY_KEY"])
        assert result.exit_code == 0
        assert "Deleted MY_KEY" in result.output

    def test_key_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\n")
            result = runner.invoke(cli, ["delete", "MISSING"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_file_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["delete", "MY_KEY"])
        assert result.exit_code != 0


# -----------------------------------------------------------------------
# rename
# -----------------------------------------------------------------------

class TestCliRename:
    def test_success(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("OLD=val\n")
            result = runner.invoke(cli, ["rename", "OLD", "NEW"])
        assert result.exit_code == 0
        assert "Renamed OLD to NEW" in result.output

    def test_key_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\n")
            result = runner.invoke(cli, ["rename", "MISSING", "NEW"])
        assert result.exit_code != 0

    def test_invalid_new_name(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\n")
            result = runner.invoke(cli, ["rename", "A", "1INVALID"])
        assert result.exit_code != 0

    def test_invalid_old_name(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["rename", "1BAD", "GOOD"])
        assert result.exit_code != 0


# -----------------------------------------------------------------------
# copy
# -----------------------------------------------------------------------

class TestCliCopy:
    def test_success(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("SRC=hello\n")
            result = runner.invoke(cli, ["copy", "SRC", "DST"])
        assert result.exit_code == 0
        assert "Copied SRC to DST" in result.output

    def test_key_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\n")
            result = runner.invoke(cli, ["copy", "MISSING", "DST"])
        assert result.exit_code != 0

    def test_file_not_found(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["copy", "SRC", "DST"])
        assert result.exit_code != 0


# -----------------------------------------------------------------------
# import
# -----------------------------------------------------------------------

class TestCliImport:
    def test_basic_import(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("source.env").write_text("API_KEY=abc\nDB_URL=postgres://x\n")
            result = runner.invoke(cli, ["import", "source.env"])
        assert result.exit_code == 0
        assert "Imported 2 key(s)" in result.output

    def test_no_overwrite_skips_existing(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("API_KEY=original\n")
            Path("source.env").write_text("API_KEY=new\nNEW_KEY=val\n")
            result = runner.invoke(cli, ["import", "source.env", "--no-overwrite"])
        assert result.exit_code == 0
        assert "Imported 1 key(s)" in result.output
        assert "Skipped 1" in result.output

    def test_no_overwrite_all_existing(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("A=1\nB=2\n")
            Path("source.env").write_text("A=new_a\nB=new_b\n")
            result = runner.invoke(cli, ["import", "source.env", "--no-overwrite"])
        assert result.exit_code == 0
        assert "Imported 0 key(s)" in result.output
        assert "Skipped 2" in result.output

    def test_missing_source_file_fails(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            # click.Path(exists=True) exits with code 2 when file missing
            result = runner.invoke(cli, ["import", "nonexistent.env"])
        assert result.exit_code != 0

    def test_import_into_named_env(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("source.env").write_text("X=1\n")
            result = runner.invoke(cli, ["--env", "prod", "import", "source.env"])
        assert result.exit_code == 0
        assert ".env.prod" in result.output


# -----------------------------------------------------------------------
# --env flag across commands
# -----------------------------------------------------------------------

class TestCliEnvOption:
    def test_env_routes_to_correct_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env.staging").write_text("STAGE_KEY=val\n")
            result = runner.invoke(cli, ["--env", "staging", "list"])
        assert result.exit_code == 0
        assert "STAGE_KEY" in result.output

    def test_env_not_found_shows_env_name_in_error(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["--env", "production", "list"])
        assert result.exit_code != 0
        assert "production" in result.output

    def test_default_env_uses_dotenv(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".env").write_text("DEFAULT_KEY=1\n")
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "DEFAULT_KEY" in result.output

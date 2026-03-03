"""Tests for blindfold.installer — install and init commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from blindfold.cli import cli
from blindfold.installer import (
    _append_rules_to_claude_md,
    _merge_deny_patterns,
    _create_skill_file,
    _MARKER,
    _DENY_PATTERNS,
)


# -----------------------------------------------------------------------
# _append_rules_to_claude_md
# -----------------------------------------------------------------------

class TestAppendRulesToClaudeMd:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        result = _append_rules_to_claude_md(path)
        assert result is True
        assert path.exists()
        assert _MARKER in path.read_text()

    def test_appends_to_existing(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        path.write_text("# Existing content\n")
        result = _append_rules_to_claude_md(path)
        assert result is True
        content = path.read_text()
        assert "# Existing content" in content
        assert _MARKER in content

    def test_skips_if_marker_present(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        path.write_text(f"# Existing\n## {_MARKER}\n")
        result = _append_rules_to_claude_md(path)
        assert result is False

    def test_skips_does_not_modify_file(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        original = f"# Existing\n## {_MARKER}\nsome rules\n"
        path.write_text(original)
        _append_rules_to_claude_md(path)
        assert path.read_text() == original

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / "nested" / "CLAUDE.md"
        _append_rules_to_claude_md(path)
        assert path.exists()

    def test_no_duplicate_on_second_call(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        _append_rules_to_claude_md(path)
        _append_rules_to_claude_md(path)
        content = path.read_text()
        assert content.count(_MARKER) == 1


# -----------------------------------------------------------------------
# _merge_deny_patterns
# -----------------------------------------------------------------------

class TestMergeDenyPatterns:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "settings.json"
        result = _merge_deny_patterns(path)
        assert result is True
        assert path.exists()
        data = json.loads(path.read_text())
        deny = data["permissions"]["deny"]
        for pattern in _DENY_PATTERNS:
            assert pattern in deny

    def test_merges_into_existing_preserves_other_rules(self, tmp_path):
        path = tmp_path / "settings.json"
        existing = {"permissions": {"deny": ["SomeOtherRule"]}}
        path.write_text(json.dumps(existing))
        result = _merge_deny_patterns(path)
        assert result is True
        data = json.loads(path.read_text())
        deny = data["permissions"]["deny"]
        assert "SomeOtherRule" in deny
        for pattern in _DENY_PATTERNS:
            assert pattern in deny

    def test_no_duplicates_on_second_call(self, tmp_path):
        path = tmp_path / "settings.json"
        _merge_deny_patterns(path)
        _merge_deny_patterns(path)
        data = json.loads(path.read_text())
        deny = data["permissions"]["deny"]
        assert len(deny) == len(set(deny))

    def test_skips_if_all_present(self, tmp_path):
        path = tmp_path / "settings.json"
        existing = {"permissions": {"deny": list(_DENY_PATTERNS)}}
        path.write_text(json.dumps(existing))
        result = _merge_deny_patterns(path)
        assert result is False

    def test_partial_presence_adds_missing(self, tmp_path):
        path = tmp_path / "settings.json"
        # Add only first pattern
        existing = {"permissions": {"deny": [_DENY_PATTERNS[0]]}}
        path.write_text(json.dumps(existing))
        result = _merge_deny_patterns(path)
        assert result is True
        data = json.loads(path.read_text())
        deny = data["permissions"]["deny"]
        for pattern in _DENY_PATTERNS:
            assert pattern in deny

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / ".claude" / "settings.json"
        _merge_deny_patterns(path)
        assert path.exists()

    def test_empty_existing_file(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("")
        result = _merge_deny_patterns(path)
        assert result is True
        data = json.loads(path.read_text())
        assert "permissions" in data


# -----------------------------------------------------------------------
# _create_skill_file
# -----------------------------------------------------------------------

class TestCreateSkillFile:
    def test_creates_file_and_dirs(self, tmp_path):
        path = tmp_path / "skills" / "blindfold" / "SKILL.md"
        result = _create_skill_file(path)
        assert result is True
        assert path.exists()
        assert "blindfold" in path.read_text().lower()

    def test_skips_if_exists(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text("existing content")
        result = _create_skill_file(path)
        assert result is False
        assert path.read_text() == "existing content"

    def test_skill_content_has_commands(self, tmp_path):
        path = tmp_path / "SKILL.md"
        _create_skill_file(path)
        content = path.read_text()
        assert "blindfold set" in content
        assert "blindfold get" in content
        assert "blindfold list" in content


# -----------------------------------------------------------------------
# install command (full flow via CLI)
# -----------------------------------------------------------------------

class TestRunInstall:
    def test_full_install(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        assert "blindfold install complete" in result.output
        assert (tmp_path / ".claude" / "CLAUDE.md").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert (tmp_path / ".claude" / "skills" / "blindfold" / "SKILL.md").exists()

    def test_install_output_lists_actions(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        # Should mention three actions
        lines = [l for l in result.output.splitlines() if l.strip().startswith("Appended") or
                 l.strip().startswith("Merged") or l.strip().startswith("Created")]
        assert len(lines) == 3

    def test_idempotent(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
            result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        assert "skipped" in result.output
        # CLAUDE.md should not have duplicate markers
        claude_md = (tmp_path / ".claude" / "CLAUDE.md").read_text()
        assert claude_md.count(_MARKER) == 1

    def test_idempotent_settings_no_duplicates(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
            runner.invoke(cli, ["install"])
        settings = (tmp_path / ".claude" / "settings.json").read_text()
        data = json.loads(settings)
        deny = data["permissions"]["deny"]
        assert len(deny) == len(set(deny))

    def test_install_adds_rules_to_claude_md(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
        content = (tmp_path / ".claude" / "CLAUDE.md").read_text()
        assert "NEVER read .env files" in content


# -----------------------------------------------------------------------
# init command (full flow via CLI)
# -----------------------------------------------------------------------

class TestRunInit:
    def test_full_init(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "blindfold init complete" in result.output
            assert (Path(td) / "CLAUDE.md").exists()
            assert (Path(td) / ".claude" / "settings.json").exists()
            assert (Path(td) / ".env").exists()

    def test_env_option_creates_named_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["--env", "staging", "init"])
            assert result.exit_code == 0
            assert (Path(td) / ".env.staging").exists()
            assert not (Path(td) / ".env").exists()

    def test_skips_existing_env_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            Path(".env").write_text("EXISTING=val\n")
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "skipped" in result.output
            # Existing file should not be overwritten
            assert Path(".env").read_text() == "EXISTING=val\n"

    def test_idempotent(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "skipped" in result.output
            # No duplicate markers in CLAUDE.md
            claude_md = (Path(td) / "CLAUDE.md").read_text()
            assert claude_md.count(_MARKER) == 1

    def test_idempotent_settings_no_duplicates(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["init"])
            settings = (Path(td) / ".claude" / "settings.json").read_text()
            data = json.loads(settings)
            deny = data["permissions"]["deny"]
            assert len(deny) == len(set(deny))

    def test_init_adds_deny_patterns(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            settings = (Path(td) / ".claude" / "settings.json").read_text()
            data = json.loads(settings)
            deny = data["permissions"]["deny"]
            for pattern in _DENY_PATTERNS:
                assert pattern in deny

    def test_init_appends_to_existing_claude_md(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            Path("CLAUDE.md").write_text("# My Project\n\nExisting content.\n")
            runner.invoke(cli, ["init"])
            content = (Path(td) / "CLAUDE.md").read_text()
            assert "# My Project" in content
            assert _MARKER in content

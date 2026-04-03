"""Tests for blindfold.installer — install and init commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from blindfold.cli import cli
from blindfold.installer import (
    _merge_deny_patterns,
    _register_mcp_server,
    _DENY_PATTERNS,
    _MCP_SERVER_ENTRY,
)


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
# _register_mcp_server
# -----------------------------------------------------------------------

class TestRegisterMcpServer:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / ".claude.json"
        result = _register_mcp_server(path)
        assert result is True
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mcpServers"]["blindfold"] == _MCP_SERVER_ENTRY

    def test_merges_into_existing_preserves_other_servers(self, tmp_path):
        path = tmp_path / ".claude.json"
        existing = {"mcpServers": {"other-server": {"command": "other"}}}
        path.write_text(json.dumps(existing))
        result = _register_mcp_server(path)
        assert result is True
        data = json.loads(path.read_text())
        assert "other-server" in data["mcpServers"]
        assert data["mcpServers"]["blindfold"] == _MCP_SERVER_ENTRY

    def test_skips_if_already_registered(self, tmp_path):
        path = tmp_path / ".claude.json"
        existing = {"mcpServers": {"blindfold": _MCP_SERVER_ENTRY}}
        path.write_text(json.dumps(existing))
        result = _register_mcp_server(path)
        assert result is False

    def test_idempotent_no_duplicate(self, tmp_path):
        path = tmp_path / ".claude.json"
        _register_mcp_server(path)
        _register_mcp_server(path)
        data = json.loads(path.read_text())
        # Only one blindfold entry
        assert list(data["mcpServers"].keys()).count("blindfold") == 1

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / ".claude.json"
        _register_mcp_server(path)
        assert path.exists()

    def test_empty_existing_file(self, tmp_path):
        path = tmp_path / ".claude.json"
        path.write_text("")
        result = _register_mcp_server(path)
        assert result is True
        data = json.loads(path.read_text())
        assert "mcpServers" in data

    def test_server_entry_has_correct_command(self, tmp_path):
        path = tmp_path / ".claude.json"
        _register_mcp_server(path)
        data = json.loads(path.read_text())
        entry = data["mcpServers"]["blindfold"]
        assert entry["command"] == "blindfold"
        assert entry["args"] == ["mcp-server"]


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
        assert (tmp_path / ".claude.json").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()

    def test_install_registers_mcp_server(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
        data = json.loads((tmp_path / ".claude.json").read_text())
        assert data["mcpServers"]["blindfold"]["command"] == "blindfold"
        assert data["mcpServers"]["blindfold"]["args"] == ["mcp-server"]

    def test_install_adds_deny_patterns(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        deny = data["permissions"]["deny"]
        for pattern in _DENY_PATTERNS:
            assert pattern in deny

    def test_install_output_mentions_tools(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install"])
        assert "blindfold_list" in result.output
        assert "blindfold_set" in result.output

    def test_install_remote_registers_ssh_entry(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install", "--remote", "user@myhost"])
        assert result.exit_code == 0
        data = json.loads((tmp_path / ".claude.json").read_text())
        entry = data["mcpServers"]["blindfold"]
        assert entry["command"] == "ssh"
        assert "user@myhost" in entry["args"]
        assert "blindfold" in entry["args"]
        assert "mcp-server" in entry["args"]

    def test_install_remote_default_port_in_args(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install", "--remote", "user@myhost"])
        data = json.loads((tmp_path / ".claude.json").read_text())
        args = data["mcpServers"]["blindfold"]["args"]
        assert any("19876" in a for a in args)

    def test_install_remote_custom_port(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install", "--remote", "user@myhost", "--port", "9000"])
        data = json.loads((tmp_path / ".claude.json").read_text())
        args = data["mcpServers"]["blindfold"]["args"]
        assert any("9000" in a for a in args)

    def test_install_remote_output_mentions_ssh(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install", "--remote", "user@myhost"])
        assert "SSH" in result.output or "ssh" in result.output.lower()
        assert "user@myhost" in result.output

    def test_install_remote_output_mentions_tunnel(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install", "--remote", "user@myhost"])
        assert "tunnel" in result.output.lower() or "localhost:" in result.output

    def test_install_no_remote_still_works(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        data = json.loads((tmp_path / ".claude.json").read_text())
        entry = data["mcpServers"]["blindfold"]
        assert entry["command"] == "blindfold"
        assert entry["args"] == ["mcp-server"]

    def test_idempotent(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
            result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        assert "skipped" in result.output

    def test_idempotent_settings_no_duplicates(self, tmp_path):
        runner = CliRunner()
        with patch("pathlib.Path.home", return_value=tmp_path):
            runner.invoke(cli, ["install"])
            runner.invoke(cli, ["install"])
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        deny = data["permissions"]["deny"]
        assert len(deny) == len(set(deny))


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
            assert Path(".env").read_text() == "EXISTING=val\n"

    def test_idempotent(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "skipped" in result.output

    def test_idempotent_settings_no_duplicates(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["init"])
            data = json.loads((Path(td) / ".claude" / "settings.json").read_text())
            deny = data["permissions"]["deny"]
            assert len(deny) == len(set(deny))

    def test_init_adds_deny_patterns(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            data = json.loads((Path(td) / ".claude" / "settings.json").read_text())
            deny = data["permissions"]["deny"]
            for pattern in _DENY_PATTERNS:
                assert pattern in deny

    def test_init_does_not_write_claude_md(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init"])
            assert not (Path(td) / "CLAUDE.md").exists()

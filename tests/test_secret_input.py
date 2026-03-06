"""Tests for blindfold.secret_input — secret input methods."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, mock_open
import subprocess

import click
import pytest

from blindfold.secret_input import (
    get_secret_from_tty,
    get_secret_from_clipboard,
    get_secret_from_gui,
    _is_wsl,
    _run_clipboard_cmd,
)


# -----------------------------------------------------------------------
# get_secret_from_gui
# -----------------------------------------------------------------------

class TestGetSecretFromGUI:
    # tkinter is tried first; patch it to succeed or fail as needed.

    def test_tkinter_used_by_default(self):
        with patch("blindfold.secret_input._gui_tkinter", return_value="guival") as mock_tk:
            result = get_secret_from_gui("API_KEY", "my-project")
        assert result == "guival"
        mock_tk.assert_called_once_with("API_KEY", "my-project")

    def test_tkinter_cancel_raises_abort(self):
        with patch("blindfold.secret_input._gui_tkinter", side_effect=click.Abort()):
            with pytest.raises(click.Abort):
                get_secret_from_gui("API_KEY", "my-project")

    # When tkinter is unavailable, fall back to osascript (macOS) or zenity (Linux).

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_macos_osascript_fallback(self, mock_run, mock_sys, mock_tk):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=0, stdout="mysecret\n", stderr="")
        result = get_secret_from_gui("API_KEY", "my-project")
        assert result == "mysecret"
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "API_KEY" in args[2]
        assert "my-project" in args[2]
        assert "Secret value for" in args[2]
        assert "Save" in args[2]

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_macos_osascript_cancel_raises_abort(self, mock_run, mock_sys, mock_tk):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="User cancelled.")
        with pytest.raises(click.Abort):
            get_secret_from_gui("API_KEY", "my-project")

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_macos_osascript_empty_value_allowed(self, mock_run, mock_sys, mock_tk):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=0, stdout="\n", stderr="")
        result = get_secret_from_gui("API_KEY", "my-project")
        assert result == ""

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_linux_zenity_fallback(self, mock_run, mock_sys, mock_which, mock_tk):
        mock_sys.platform = "linux"
        mock_run.return_value = MagicMock(returncode=0, stdout="zenitsecret\n", stderr="")
        result = get_secret_from_gui("DB_URL", "proj")
        assert result == "zenitsecret"
        args = mock_run.call_args[0][0]
        assert args[0] == "zenity"
        assert "--entry" in args
        assert "--hide-text" in args
        assert any("Set Secret" in a for a in args)
        assert any("Secret value for" in a for a in args)

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_linux_zenity_cancel_raises_abort(self, mock_run, mock_sys, mock_which, mock_tk):
        mock_sys.platform = "linux"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with pytest.raises(click.Abort):
            get_secret_from_gui("DB_URL", "proj")

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.shutil.which", return_value=None)
    @patch("blindfold.secret_input.sys")
    def test_no_gui_available_raises_runtime_error(self, mock_sys, mock_which, mock_tk):
        mock_sys.platform = "linux"
        with pytest.raises(RuntimeError, match="No GUI dialog available"):
            get_secret_from_gui("KEY", "proj")

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.sys")
    @patch(
        "blindfold.secret_input.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=120),
    )
    def test_macos_osascript_timeout_raises_abort(self, mock_run, mock_sys, mock_tk):
        mock_sys.platform = "darwin"
        with pytest.raises(click.Abort):
            get_secret_from_gui("KEY", "proj")

    @patch("blindfold.secret_input._gui_tkinter", side_effect=RuntimeError("no tkinter"))
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_macos_osascript_timeout_sentinel_raises_abort(self, mock_run, mock_sys, mock_tk):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=0, stdout="__TIMEOUT__\n", stderr="")
        with pytest.raises(click.Abort):
            get_secret_from_gui("KEY", "proj")


# -----------------------------------------------------------------------
# get_secret_from_tty
# -----------------------------------------------------------------------

class TestGetSecretFromTTY:
    @patch("blindfold.secret_input.getpass.getpass", return_value="my-secret")
    def test_returns_secret(self, mock_getpass):
        result = get_secret_from_tty("Enter value: ")
        assert result == "my-secret"
        mock_getpass.assert_called_once_with(prompt="Enter value: ")

    @patch("blindfold.secret_input.getpass.getpass", return_value="")
    def test_empty_secret_is_valid(self, mock_getpass):
        result = get_secret_from_tty("Enter value: ")
        assert result == ""

    @patch(
        "blindfold.secret_input.getpass.getpass",
        side_effect=OSError("No /dev/tty"),
    )
    def test_tty_unavailable_raises_click_exception(self, mock_getpass):
        with pytest.raises(click.ClickException) as exc_info:
            get_secret_from_tty("Enter value: ")
        msg = exc_info.value.format_message()
        assert "/dev/tty" in msg
        assert "--clipboard" in msg

    @patch("blindfold.secret_input.getpass.getpass", return_value="secret\n")
    def test_does_not_strip_newline_from_tty(self, mock_getpass):
        """TTY input is returned as-is from getpass (no stripping)."""
        result = get_secret_from_tty("Enter value: ")
        assert result == "secret\n"


# -----------------------------------------------------------------------
# get_secret_from_clipboard — macOS
# -----------------------------------------------------------------------

class TestClipboardMacOS:
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_macos_uses_pbpaste(self, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="clipboard-content\n", stderr=""
        )
        result = get_secret_from_clipboard()
        assert result == "clipboard-content"
        mock_run.assert_called_once_with(
            ["pbpaste"],
            capture_output=True,
            text=True,
            timeout=5,
        )


# -----------------------------------------------------------------------
# get_secret_from_clipboard — Windows/WSL
# -----------------------------------------------------------------------

class TestClipboardWindows:
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_win32_uses_powershell(self, mock_run, mock_sys):
        mock_sys.platform = "win32"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="win-secret\n", stderr=""
        )
        result = get_secret_from_clipboard()
        assert result == "win-secret"
        mock_run.assert_called_once_with(
            ["powershell.exe", "-command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("blindfold.secret_input._is_wsl", return_value=True)
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.subprocess.run")
    def test_wsl_uses_powershell(self, mock_run, mock_sys, mock_wsl):
        mock_sys.platform = "linux"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="wsl-secret\n", stderr=""
        )
        result = get_secret_from_clipboard()
        assert result == "wsl-secret"
        mock_run.assert_called_once_with(
            ["powershell.exe", "-command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=5,
        )


# -----------------------------------------------------------------------
# get_secret_from_clipboard — Linux
# -----------------------------------------------------------------------

class TestClipboardLinux:
    @patch("blindfold.secret_input._is_wsl", return_value=False)
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.shutil.which", side_effect=lambda t: t == "xclip")
    @patch("blindfold.secret_input.subprocess.run")
    def test_linux_prefers_xclip(self, mock_run, mock_which, mock_sys, mock_wsl):
        mock_sys.platform = "linux"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="xclip-secret\n", stderr=""
        )
        result = get_secret_from_clipboard()
        assert result == "xclip-secret"
        mock_run.assert_called_once_with(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("blindfold.secret_input._is_wsl", return_value=False)
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.shutil.which", side_effect=lambda t: t == "xsel")
    @patch("blindfold.secret_input.subprocess.run")
    def test_linux_falls_back_to_xsel(self, mock_run, mock_which, mock_sys, mock_wsl):
        mock_sys.platform = "linux"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="xsel-secret\n", stderr=""
        )
        result = get_secret_from_clipboard()
        assert result == "xsel-secret"
        mock_run.assert_called_once_with(
            ["xsel", "--clipboard", "--output"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("blindfold.secret_input._is_wsl", return_value=False)
    @patch("blindfold.secret_input.sys")
    @patch("blindfold.secret_input.shutil.which", return_value=None)
    def test_linux_no_tool_raises(self, mock_which, mock_sys, mock_wsl):
        mock_sys.platform = "linux"
        with pytest.raises(click.ClickException) as exc_info:
            get_secret_from_clipboard()
        msg = exc_info.value.format_message()
        assert "xclip" in msg
        assert "xsel" in msg


# -----------------------------------------------------------------------
# _run_clipboard_cmd — error handling
# -----------------------------------------------------------------------

class TestRunClipboardCmd:
    @patch("blindfold.secret_input.subprocess.run", side_effect=FileNotFoundError)
    def test_tool_not_found(self, mock_run):
        with pytest.raises(click.ClickException) as exc_info:
            _run_clipboard_cmd(["nonexistent"], tool_name="nonexistent")
        assert "not found" in exc_info.value.format_message()

    @patch(
        "blindfold.secret_input.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=5),
    )
    def test_timeout(self, mock_run):
        with pytest.raises(click.ClickException) as exc_info:
            _run_clipboard_cmd(["slow-tool"], tool_name="slow-tool")
        assert "timed out" in exc_info.value.format_message()

    @patch("blindfold.secret_input.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="some error"
        )
        with pytest.raises(click.ClickException) as exc_info:
            _run_clipboard_cmd(["failing"], tool_name="failing")
        msg = exc_info.value.format_message()
        assert "failed" in msg

    @patch("blindfold.secret_input.subprocess.run")
    def test_no_trailing_newline(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="no-newline", stderr=""
        )
        result = _run_clipboard_cmd(["tool"], tool_name="tool")
        assert result == "no-newline"

    @patch("blindfold.secret_input.subprocess.run")
    def test_strips_trailing_newline(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="content\n", stderr=""
        )
        result = _run_clipboard_cmd(["tool"], tool_name="tool")
        assert result == "content"

    @patch("blindfold.secret_input.subprocess.run")
    def test_preserves_internal_newlines(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="line1\nline2\n", stderr=""
        )
        result = _run_clipboard_cmd(["tool"], tool_name="tool")
        assert result == "line1\nline2"


# -----------------------------------------------------------------------
# _is_wsl
# -----------------------------------------------------------------------

class TestIsWSL:
    @patch("blindfold.secret_input.sys")
    def test_non_linux_returns_false(self, mock_sys):
        mock_sys.platform = "darwin"
        assert _is_wsl() is False

    @patch("builtins.open", side_effect=OSError)
    @patch("blindfold.secret_input.sys")
    def test_no_proc_version_returns_false(self, mock_sys, mock_open):
        mock_sys.platform = "linux"
        assert _is_wsl() is False

    @patch(
        "builtins.open",
        mock_open(read_data="Linux version 5.10.0 Microsoft standard WSL2"),
    )
    @patch("blindfold.secret_input.sys")
    def test_wsl_detected(self, mock_sys):
        mock_sys.platform = "linux"
        assert _is_wsl() is True

    @patch(
        "builtins.open",
        mock_open(read_data="Linux version 6.5.0-generic (buildd@lcy02) x86_64"),
    )
    @patch("blindfold.secret_input.sys")
    def test_native_linux_returns_false(self, mock_sys):
        mock_sys.platform = "linux"
        assert _is_wsl() is False

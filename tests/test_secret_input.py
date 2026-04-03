"""Tests for blindfold.secret_input — secret input methods."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import click
import pytest

from blindfold.secret_input import (
    _get_secret_from_gui,
    _has_display,
    _is_wsl,
    _run_clipboard_cmd,
    _try_kdialog,
    _try_osascript,
    _try_pinentry,
    _try_zenity,
    get_secret_from_clipboard,
    get_secret_from_tty,
)


# -----------------------------------------------------------------------
# get_secret_from_tty — normal terminal path (stdin is a tty)
# -----------------------------------------------------------------------

class TestGetSecretFromTTY:
    @patch("blindfold.secret_input.sys.stdin")
    @patch("blindfold.secret_input.getpass.getpass", return_value="my-secret")
    def test_returns_secret(self, mock_getpass, mock_stdin):
        mock_stdin.isatty.return_value = True
        result = get_secret_from_tty("Enter value: ")
        assert result == "my-secret"
        mock_getpass.assert_called_once_with(prompt="Enter value: ")

    @patch("blindfold.secret_input.sys.stdin")
    @patch("blindfold.secret_input.getpass.getpass", return_value="")
    def test_empty_secret_is_valid(self, mock_getpass, mock_stdin):
        mock_stdin.isatty.return_value = True
        result = get_secret_from_tty("Enter value: ")
        assert result == ""

    @patch("blindfold.secret_input.sys.stdin")
    @patch(
        "blindfold.secret_input.getpass.getpass",
        side_effect=OSError("No /dev/tty"),
    )
    def test_tty_unavailable_raises_click_exception(self, mock_getpass, mock_stdin):
        mock_stdin.isatty.return_value = True
        with pytest.raises(click.ClickException) as exc_info:
            get_secret_from_tty("Enter value: ")
        msg = exc_info.value.format_message()
        assert "/dev/tty" in msg
        assert "--clipboard" in msg

    @patch("blindfold.secret_input.sys.stdin")
    @patch("blindfold.secret_input.getpass.getpass", return_value="secret\n")
    def test_does_not_strip_newline_from_tty(self, mock_getpass, mock_stdin):
        """getpass return value is passed through as-is (no stripping)."""
        mock_stdin.isatty.return_value = True
        result = get_secret_from_tty("Enter value: ")
        assert result == "secret\n"

    @patch("blindfold.secret_input._get_secret_from_gui", return_value=None)
    @patch("blindfold.secret_input.sys.stdin")
    def test_headless_no_gui_raises_clipboard_hint(self, mock_stdin, mock_gui):
        """When stdin is not a tty and no GUI is available, raise with --clipboard hint."""
        mock_stdin.isatty.return_value = False
        with pytest.raises(click.ClickException) as exc_info:
            get_secret_from_tty("Enter value: ")
        msg = exc_info.value.format_message()
        assert "--clipboard" in msg

    @patch("blindfold.secret_input._get_secret_from_gui", return_value="gui-secret")
    @patch("blindfold.secret_input.sys.stdin")
    def test_headless_uses_gui_dialog(self, mock_stdin, mock_gui):
        """When stdin is not a tty but a GUI dialog succeeds, return its value."""
        mock_stdin.isatty.return_value = False
        result = get_secret_from_tty("Enter value: ")
        assert result == "gui-secret"
        mock_gui.assert_called_once_with("Enter value: ")

    @patch("blindfold.secret_input._get_secret_from_gui")
    @patch("blindfold.secret_input.sys.stdin")
    def test_headless_gui_abort_propagates(self, mock_stdin, mock_gui):
        """click.Abort from the GUI dialog propagates to the caller."""
        mock_stdin.isatty.return_value = False
        mock_gui.side_effect = click.Abort()
        with pytest.raises(click.Abort):
            get_secret_from_tty("Enter value: ")


# -----------------------------------------------------------------------
# _has_display
# -----------------------------------------------------------------------

class TestHasDisplay:
    @patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True)
    def test_x11_display(self):
        assert _has_display() is True

    @patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True)
    def test_wayland_display(self):
        assert _has_display() is True

    @patch.dict("os.environ", {}, clear=True)
    def test_no_display(self):
        assert _has_display() is False


# -----------------------------------------------------------------------
# _get_secret_from_gui
# -----------------------------------------------------------------------

class TestGetSecretFromGUI:
    @patch("blindfold.secret_input._try_osascript", return_value="mac-secret")
    @patch("blindfold.secret_input.sys")
    def test_macos_uses_osascript(self, mock_sys, mock_osascript):
        mock_sys.platform = "darwin"
        result = _get_secret_from_gui("Enter value: ")
        assert result == "mac-secret"
        mock_osascript.assert_called_once_with("Enter value: ")

    @patch("blindfold.secret_input._try_kdialog", return_value=None)
    @patch("blindfold.secret_input._try_zenity", return_value=None)
    @patch("blindfold.secret_input._try_pinentry", return_value="pin-secret")
    @patch("blindfold.secret_input.sys")
    def test_linux_tries_pinentry_first(self, mock_sys, mock_pin, mock_zen, mock_kd):
        mock_sys.platform = "linux"
        result = _get_secret_from_gui("Enter value: ")
        assert result == "pin-secret"
        mock_pin.assert_called_once()
        mock_zen.assert_not_called()

    @patch("blindfold.secret_input._try_kdialog", return_value=None)
    @patch("blindfold.secret_input._try_zenity", return_value="zen-secret")
    @patch("blindfold.secret_input._try_pinentry", return_value=None)
    @patch("blindfold.secret_input.sys")
    def test_linux_falls_back_to_zenity(self, mock_sys, mock_pin, mock_zen, mock_kd):
        mock_sys.platform = "linux"
        result = _get_secret_from_gui("Enter value: ")
        assert result == "zen-secret"

    @patch("blindfold.secret_input._try_kdialog", return_value="kd-secret")
    @patch("blindfold.secret_input._try_zenity", return_value=None)
    @patch("blindfold.secret_input._try_pinentry", return_value=None)
    @patch("blindfold.secret_input.sys")
    def test_linux_falls_back_to_kdialog(self, mock_sys, mock_pin, mock_zen, mock_kd):
        mock_sys.platform = "linux"
        result = _get_secret_from_gui("Enter value: ")
        assert result == "kd-secret"

    @patch("blindfold.secret_input._try_kdialog", return_value=None)
    @patch("blindfold.secret_input._try_zenity", return_value=None)
    @patch("blindfold.secret_input._try_pinentry", return_value=None)
    @patch("blindfold.secret_input.sys")
    def test_returns_none_when_no_gui_available(self, mock_sys, mock_pin, mock_zen, mock_kd):
        mock_sys.platform = "linux"
        result = _get_secret_from_gui("Enter value: ")
        assert result is None


# -----------------------------------------------------------------------
# _try_pinentry
# -----------------------------------------------------------------------

class TestTryPinentry:
    @patch("blindfold.secret_input._has_display", return_value=False)
    def test_returns_none_when_no_display(self, mock_display):
        assert _try_pinentry("Enter: ") is None

    @patch("blindfold.secret_input.shutil.which", return_value=None)
    @patch("blindfold.secret_input._has_display", return_value=True)
    def test_returns_none_when_not_installed(self, mock_display, mock_which):
        assert _try_pinentry("Enter: ") is None

    @patch("blindfold.secret_input.subprocess.Popen", side_effect=OSError("no such file"))
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    @patch("blindfold.secret_input._has_display", return_value=True)
    def test_popen_error_returns_none(self, mock_display, mock_which, mock_popen):
        assert _try_pinentry("Enter: ") is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    def test_returns_secret(self, mock_which, mock_display):
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "OK Pleased to meet you\n",  # greeting
            "OK\n",                       # SETPROMPT response
            "D hunter2\n",               # GETPIN data
            "OK\n",                       # GETPIN done
        ]
        with patch("blindfold.secret_input.subprocess.Popen", return_value=mock_proc):
            result = _try_pinentry("Enter value: ")
        assert result == "hunter2"

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    def test_empty_pin_returns_empty_string(self, mock_which, mock_display):
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "OK Pleased to meet you\n",
            "OK\n",
            "OK\n",  # GETPIN with no D line
        ]
        with patch("blindfold.secret_input.subprocess.Popen", return_value=mock_proc):
            result = _try_pinentry("Enter value: ")
        assert result == ""

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    def test_setprompt_error_returns_none(self, mock_which, mock_display):
        """ERR on SETPROMPT (e.g. no display) returns None, does not abort."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "OK Pleased to meet you\n",
            "ERR 83886360 No display\n",  # SETPROMPT response
        ]
        with patch("blindfold.secret_input.subprocess.Popen", return_value=mock_proc):
            result = _try_pinentry("Enter value: ")
        assert result is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    def test_getpin_cancel_raises_abort(self, mock_which, mock_display):
        """ERR during GETPIN (user cancelled) raises click.Abort."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "OK Pleased to meet you\n",
            "OK\n",
            "ERR 83886179 Operation cancelled\n",
        ]
        with patch("blindfold.secret_input.subprocess.Popen", return_value=mock_proc):
            with pytest.raises(click.Abort):
                _try_pinentry("Enter value: ")

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/pinentry")
    def test_strips_trailing_colon_from_prompt(self, mock_which, mock_display):
        """The prompt is cleaned before being sent to SETPROMPT."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "OK Pleased to meet you\n",
            "OK\n",
            "D value\n",
            "OK\n",
        ]
        with patch("blindfold.secret_input.subprocess.Popen", return_value=mock_proc) as mock_popen:
            _try_pinentry("Enter API_KEY: ")
        # Check that SETPROMPT was sent with trailing colon/space stripped
        written = "".join(
            args[0] for args, kwargs in mock_proc.stdin.write.call_args_list
        )
        assert "SETPROMPT Enter API_KEY\n" in written


# -----------------------------------------------------------------------
# _try_zenity
# -----------------------------------------------------------------------

class TestTryZenity:
    @patch("blindfold.secret_input._has_display", return_value=False)
    def test_returns_none_when_no_display(self, mock_display):
        assert _try_zenity("Enter: ") is None

    @patch("blindfold.secret_input.shutil.which", return_value=None)
    @patch("blindfold.secret_input._has_display", return_value=True)
    def test_returns_none_when_not_installed(self, mock_display, mock_which):
        assert _try_zenity("Enter: ") is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.subprocess.run")
    def test_returns_secret(self, mock_run, mock_which, mock_display):
        mock_run.return_value = MagicMock(returncode=0, stdout="my-secret\n", stderr="")
        result = _try_zenity("Enter value: ")
        assert result == "my-secret"

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.subprocess.run")
    def test_cancel_raises_abort(self, mock_run, mock_which, mock_display):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with pytest.raises(click.Abort):
            _try_zenity("Enter value: ")

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch(
        "blindfold.secret_input.subprocess.run",
        side_effect=subprocess.TimeoutExpired("zenity", 120),
    )
    def test_timeout_returns_none(self, mock_run, mock_which, mock_display):
        assert _try_zenity("Enter: ") is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.subprocess.run", side_effect=OSError("no display"))
    def test_oserror_returns_none(self, mock_run, mock_which, mock_display):
        assert _try_zenity("Enter: ") is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/zenity")
    @patch("blindfold.secret_input.subprocess.run")
    def test_correct_command_used(self, mock_run, mock_which, mock_display):
        mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
        _try_zenity("Enter API_KEY: ")
        args = mock_run.call_args[0][0]
        assert args[0] == "zenity"
        assert "--hide-text" in args
        assert any("Enter API_KEY:" in a for a in args)


# -----------------------------------------------------------------------
# _try_kdialog
# -----------------------------------------------------------------------

class TestTryKdialog:
    @patch("blindfold.secret_input._has_display", return_value=False)
    def test_returns_none_when_no_display(self, mock_display):
        assert _try_kdialog("Enter: ") is None

    @patch("blindfold.secret_input.shutil.which", return_value=None)
    @patch("blindfold.secret_input._has_display", return_value=True)
    def test_returns_none_when_not_installed(self, mock_display, mock_which):
        assert _try_kdialog("Enter: ") is None

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/kdialog")
    @patch("blindfold.secret_input.subprocess.run")
    def test_returns_secret(self, mock_run, mock_which, mock_display):
        mock_run.return_value = MagicMock(returncode=0, stdout="kd-secret\n", stderr="")
        result = _try_kdialog("Enter value: ")
        assert result == "kd-secret"

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/kdialog")
    @patch("blindfold.secret_input.subprocess.run")
    def test_cancel_raises_abort(self, mock_run, mock_which, mock_display):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with pytest.raises(click.Abort):
            _try_kdialog("Enter value: ")

    @patch("blindfold.secret_input._has_display", return_value=True)
    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/kdialog")
    @patch(
        "blindfold.secret_input.subprocess.run",
        side_effect=subprocess.TimeoutExpired("kdialog", 120),
    )
    def test_timeout_returns_none(self, mock_run, mock_which, mock_display):
        assert _try_kdialog("Enter: ") is None


# -----------------------------------------------------------------------
# _try_osascript
# -----------------------------------------------------------------------

class TestTryOsascript:
    @patch("blindfold.secret_input.shutil.which", return_value=None)
    def test_returns_none_when_not_installed(self, mock_which):
        assert _try_osascript("Enter: ") is None

    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/osascript")
    @patch("blindfold.secret_input.subprocess.run")
    def test_returns_secret(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="button returned:OK, text returned:my-secret\n",
            stderr="",
        )
        result = _try_osascript("Enter value: ")
        assert result == "my-secret"

    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/osascript")
    @patch("blindfold.secret_input.subprocess.run")
    def test_secret_with_comma(self, mock_run, mock_which):
        """Secrets containing commas are parsed correctly."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="button returned:OK, text returned:pass,word\n",
            stderr="",
        )
        result = _try_osascript("Enter value: ")
        assert result == "pass,word"

    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/osascript")
    @patch("blindfold.secret_input.subprocess.run")
    def test_cancel_raises_abort(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with pytest.raises(click.Abort):
            _try_osascript("Enter value: ")

    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/osascript")
    @patch(
        "blindfold.secret_input.subprocess.run",
        side_effect=subprocess.TimeoutExpired("osascript", 120),
    )
    def test_timeout_returns_none(self, mock_run, mock_which):
        assert _try_osascript("Enter: ") is None

    @patch("blindfold.secret_input.shutil.which", return_value="/usr/bin/osascript")
    @patch("blindfold.secret_input.subprocess.run", side_effect=OSError)
    def test_oserror_returns_none(self, mock_run, mock_which):
        assert _try_osascript("Enter: ") is None


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

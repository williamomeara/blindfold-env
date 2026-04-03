"""Tests for blindfold.mcp_server — two-step secret entry via browser form."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from blindfold import mcp_server
from blindfold.mcp_server import (
    _build_html,
    _make_form_server,
    _serve_until_done,
    _sessions,
    blindfold_set,
    blindfold_set_confirm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return an available localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _submit_form(port: int, token: str, value: str) -> int:
    """POST a form submission to the local server. Returns the HTTP status code."""
    data = urllib.parse.urlencode({"value": value}).encode()
    url = f"http://127.0.0.1:{port}/{token}"
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req) as resp:
        return resp.status


def _get_form(port: int, token: str) -> tuple[int, str]:
    """GET the form page. Returns (status, body)."""
    url = f"http://127.0.0.1:{port}/{token}"
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read().decode()


# ---------------------------------------------------------------------------
# _build_html
# ---------------------------------------------------------------------------

class TestBuildHtml:
    def test_contains_key_name(self):
        html = _build_html("MY_API_KEY", "abc123")
        assert "MY_API_KEY" in html

    def test_contains_token_in_action(self):
        html = _build_html("KEY", "deadbeef")
        assert 'action="/deadbeef"' in html

    def test_is_valid_html(self):
        html = _build_html("KEY", "tok")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


# ---------------------------------------------------------------------------
# _make_form_server / _serve_until_done
# ---------------------------------------------------------------------------

class TestFormServer:
    def _start_server(self, key="SECRET_KEY", token="testtoken123"):
        port = _free_port()
        event = threading.Event()
        holder: list = [None]
        httpd = _make_form_server("127.0.0.1", port, key, token, holder, event)
        t = threading.Thread(target=_serve_until_done, args=(httpd, 10), daemon=True)
        t.start()
        # Give server a moment to bind
        time.sleep(0.05)
        return port, token, holder, event, httpd, t

    def test_get_returns_form_html(self):
        port, token, holder, event, httpd, t = self._start_server()
        status, body = _get_form(port, token)
        assert status == 200
        assert "SECRET_KEY" in body
        assert 'action="/' + token in body
        httpd._done = True

    def test_get_wrong_path_returns_404(self):
        port, token, holder, event, httpd, t = self._start_server()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/wrongpath")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        httpd._done = True

    def test_post_stores_value_and_sets_event(self):
        port, token, holder, event, httpd, t = self._start_server()
        status = _submit_form(port, token, "supersecret")
        assert status == 200
        assert event.is_set()
        assert holder[0] == "supersecret"

    def test_post_sets_done_flag(self):
        port, token, holder, event, httpd, t = self._start_server()
        _submit_form(port, token, "val")
        assert httpd._done is True

    def test_post_wrong_path_returns_404(self):
        port, token, holder, event, httpd, t = self._start_server()
        try:
            data = urllib.parse.urlencode({"value": "x"}).encode()
            urllib.request.urlopen(f"http://127.0.0.1:{port}/wrongpath", data=data)
        except urllib.error.HTTPError as e:
            assert e.code == 404
        httpd._done = True

    def test_post_returns_success_html(self):
        port, token, holder, event, httpd, t = self._start_server()
        data = urllib.parse.urlencode({"value": "val"}).encode()
        url = f"http://127.0.0.1:{port}/{token}"
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
        assert "Secret saved" in body


# ---------------------------------------------------------------------------
# blindfold_set (integration via env var for port)
# ---------------------------------------------------------------------------

class TestBlindfolSet:
    def test_returns_url_and_session_id(self):
        port = _free_port()
        with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port)}):
            with _isolated_cwd():
                result = blindfold_set("API_KEY")
        assert f"localhost:{port}/" in result
        assert "blindfold_set_confirm(" in result
        assert "API_KEY" in result

    def test_creates_session(self):
        port = _free_port()
        _sessions.clear()
        with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port)}):
            with _isolated_cwd():
                result = blindfold_set("MY_KEY")
        sid = re.search(r"confirm\('([^']+)'\)", result).group(1)
        assert sid in _sessions
        session = _sessions[sid]
        assert session["key"] == "MY_KEY"
        assert "token" in session
        assert "event" in session
        assert "holder" in session
        # Cleanup
        _sessions.pop(sid, None)

    def test_url_contains_128bit_token(self):
        port = _free_port()
        with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port)}):
            with _isolated_cwd():
                result = blindfold_set("KEY")
        match = re.search(r"localhost:\d+/([a-f0-9]+)", result)
        assert match is not None
        token = match.group(1)
        assert len(token) == 32  # 16 bytes hex = 32 chars
        # Cleanup
        sid = re.search(r"confirm\('([^']+)'\)", result).group(1)
        _sessions.pop(sid, None)

    def test_uses_blindfold_port_env_var(self):
        port = _free_port()
        with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port)}):
            with _isolated_cwd():
                result = blindfold_set("KEY")
        assert f":{port}/" in result
        sid = re.search(r"confirm\('([^']+)'\)", result).group(1)
        _sessions.pop(sid, None)


# ---------------------------------------------------------------------------
# blindfold_set_confirm
# ---------------------------------------------------------------------------

class TestBlindfolSetConfirm:
    def test_unknown_session_id(self):
        result = blindfold_set_confirm("nonexistent-id")
        assert "not found" in result.lower()

    def test_timeout(self):
        import threading
        event = threading.Event()
        holder: list = [None]
        sid = "timeout-test-session"
        _sessions[sid] = {
            "key": "KEY",
            "path": Path("/tmp/test.env"),
            "event": event,
            "holder": holder,
        }
        with patch.object(event, "wait", return_value=False):
            result = blindfold_set_confirm(sid)
        assert "Timed out" in result
        assert "KEY" in result
        assert sid not in _sessions

    def test_none_holder_value(self):
        import threading
        event = threading.Event()
        holder: list = [None]
        event.set()
        sid = "none-value-session"
        _sessions[sid] = {
            "key": "KEY",
            "path": Path("/tmp/test.env"),
            "event": event,
            "holder": holder,
        }
        result = blindfold_set_confirm(sid)
        assert "No value received" in result
        assert sid not in _sessions

    def test_removes_session_on_completion(self):
        import threading
        event = threading.Event()
        holder: list = ["myvalue"]
        event.set()
        sid = "removal-test-session"
        with _isolated_cwd() as td:
            path = Path(td) / ".env"
            _sessions[sid] = {
                "key": "MY_KEY",
                "path": path,
                "event": event,
                "holder": holder,
            }
            blindfold_set_confirm(sid)
        assert sid not in _sessions

    def test_writes_env_file(self):
        import threading
        event = threading.Event()
        holder: list = ["secretvalue"]
        event.set()
        sid = "write-test-session"
        with _isolated_cwd() as td:
            path = Path(td) / ".env"
            _sessions[sid] = {
                "key": "DB_PASSWORD",
                "path": path,
                "event": event,
                "holder": holder,
            }
            result = blindfold_set_confirm(sid)
            assert result == "Set DB_PASSWORD successfully"
            assert path.exists()
            content = path.read_text()
            assert "DB_PASSWORD" in content
            assert "secretvalue" in content


# ---------------------------------------------------------------------------
# Full integration: blindfold_set → form submit → blindfold_set_confirm
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_full_flow_writes_env(self):
        port = _free_port()
        _sessions.clear()

        with _isolated_cwd() as td:
            with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port)}):
                result = blindfold_set("FULL_FLOW_KEY")

            token = re.search(r"localhost:\d+/([a-f0-9]+)", result).group(1)
            sid = re.search(r"confirm\('([^']+)'\)", result).group(1)

            # Give server thread a moment to start
            time.sleep(0.1)

            # Submit the form
            _submit_form(port, token, "myfulltestvalue")

            # Confirm and write
            confirm_result = blindfold_set_confirm(sid)

            assert confirm_result == "Set FULL_FLOW_KEY successfully"
            env_path = Path(td) / ".env"
            assert env_path.exists()
            content = env_path.read_text()
            assert "FULL_FLOW_KEY" in content
            assert "myfulltestvalue" in content

    def test_each_session_has_unique_token(self):
        port1 = _free_port()
        port2 = _free_port()
        with _isolated_cwd():
            with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port1)}):
                r1 = blindfold_set("KEY1")
            # Clean up server by marking done
            sid1 = re.search(r"confirm\('([^']+)'\)", r1).group(1)

            with patch.dict("os.environ", {"BLINDFOLD_PORT": str(port2)}):
                r2 = blindfold_set("KEY2")
            sid2 = re.search(r"confirm\('([^']+)'\)", r2).group(1)

        token1 = re.search(r"localhost:\d+/([a-f0-9]+)", r1).group(1)
        token2 = re.search(r"localhost:\d+/([a-f0-9]+)", r2).group(1)
        assert token1 != token2
        assert sid1 != sid2

        _sessions.pop(sid1, None)
        _sessions.pop(sid2, None)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

import contextlib
import os
import tempfile


@contextlib.contextmanager
def _isolated_cwd():
    """Change to a temp directory for the duration of the block."""
    with tempfile.TemporaryDirectory() as td:
        old = os.getcwd()
        os.chdir(td)
        try:
            yield td
        finally:
            os.chdir(old)

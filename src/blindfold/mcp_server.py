"""
MCP server for blindfold-env.

Exposes blindfold operations as MCP tools so AI agents can manage
.env secrets natively without shell commands or CLAUDE.md instructions.

Run via: blindfold mcp-server
"""

from __future__ import annotations

import http.server
import os
import secrets
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from blindfold import env_file
from blindfold.cli import _mask_value

mcp = FastMCP("blindfold", instructions="Manage .env secrets without exposing values")

_sessions: dict[str, dict] = {}
_DEFAULT_PORT = 19876


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_FORM_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>blindfold — set {key}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f5;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 20px;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      padding: 36px 40px;
      width: 100%;
      max-width: 420px;
    }}
    .icon {{ font-size: 32px; margin-bottom: 12px; }}
    h1 {{ font-size: 18px; font-weight: 600; color: #111; margin-bottom: 4px; }}
    .subtitle {{ font-size: 13px; color: #666; margin-bottom: 24px; }}
    .key-name {{ font-family: monospace; font-weight: 600; color: #1a1a1a; }}
    label {{ font-size: 13px; font-weight: 500; color: #333; display: block; margin-bottom: 6px; }}
    .input-row {{ display: flex; gap: 8px; margin-bottom: 8px; }}
    input[type=password], input[type=text] {{
      flex: 1;
      padding: 10px 14px;
      border: 1.5px solid #d1d5db;
      border-radius: 8px;
      font-size: 15px;
      outline: none;
      transition: border-color 0.15s;
    }}
    input:focus {{ border-color: #6366f1; }}
    .toggle-btn {{
      padding: 10px 14px;
      background: #f3f4f6;
      border: 1.5px solid #d1d5db;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      color: #555;
      white-space: nowrap;
    }}
    .toggle-btn:hover {{ background: #e9eaec; }}
    .count {{ font-size: 12px; color: #9ca3af; margin-bottom: 16px; min-height: 18px; }}
    .error {{ font-size: 12px; color: #ef4444; margin-bottom: 12px; min-height: 18px; }}
    .submit-btn {{
      width: 100%;
      padding: 12px;
      background: #6366f1;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .submit-btn:hover {{ background: #4f46e5; }}
    .submit-btn:disabled {{ background: #a5b4fc; cursor: default; }}
    .alt-note {{
      margin-top: 24px;
      padding-top: 20px;
      border-top: 1px solid #f0f0f0;
      font-size: 12px;
      color: #9ca3af;
      line-height: 1.5;
    }}
    .alt-note code {{
      font-family: monospace;
      background: #f3f4f6;
      padding: 1px 5px;
      border-radius: 4px;
      color: #555;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#x1F512;</div>
    <h1>Set secret: <span class="key-name">{key}</span></h1>
    <p class="subtitle">Enter the secret value below. This page is only accessible to you.</p>
    <form method="POST" action="/{token}" id="f">
      <label for="v">Secret value</label>
      <div class="input-row">
        <input type="password" name="value" id="v" autofocus autocomplete="new-password">
        <button type="button" class="toggle-btn" onclick="toggle(this)">Show</button>
      </div>
      <div class="count" id="cnt"></div>
      <div class="error" id="err"></div>
      <button type="submit" class="submit-btn" id="btn">Save secret</button>
    </form>
    <div class="alt-note">
      Want a native GUI instead of this browser form?
      Run <code>blindfold agent</code> on your local machine and reinstall with
      <code>--agent</code> for a seamless macOS/Linux dialog.
    </div>
  </div>
  <script>
    var inp = document.getElementById('v');
    var cnt = document.getElementById('cnt');
    var err = document.getElementById('err');
    var btn = document.getElementById('btn');
    var shown = false;
    inp.addEventListener('input', function() {{
      var n = inp.value.length;
      cnt.textContent = n > 0 ? n + ' character' + (n === 1 ? '' : 's') : '';
      err.textContent = '';
    }});
    document.getElementById('f').addEventListener('submit', function(e) {{
      if (!inp.value) {{
        e.preventDefault();
        err.textContent = 'Please enter a value before saving.';
        inp.focus();
      }} else {{
        btn.disabled = true;
        btn.textContent = 'Saving\u2026';
      }}
    }});
    function toggle(btn) {{
      shown = !shown;
      inp.type = shown ? 'text' : 'password';
      btn.textContent = shown ? 'Hide' : 'Show';
    }}
  </script>
</body>
</html>
"""

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>blindfold — saved</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; background: #f5f5f5;
    }}
    .card {{
      background: white; border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      padding: 48px 40px; text-align: center; max-width: 380px;
    }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    h1 {{ font-size: 20px; font-weight: 600; color: #111; }}
    p {{ font-size: 14px; color: #666; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#x2705;</div>
    <h1>Secret saved</h1>
    <p>You can close this tab.</p>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP form server
# ---------------------------------------------------------------------------

def _build_html(key: str, token: str) -> str:
    return _FORM_HTML.format(key=key, token=token)


def _make_form_server(
    host: str,
    port: int,
    key: str,
    token: str,
    holder: list[Optional[str]],
    event: threading.Event,
) -> http.server.HTTPServer:
    """Return an HTTPServer with a closure-based handler.

    GET  /{token}  → HTML password form
    POST /{token}  → store secret, set event, respond 200
    Other paths    → 404
    """
    path_prefix = f"/{token}"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass  # suppress access logs

        def do_GET(self) -> None:
            if self.path != path_prefix:
                self._send(404, "Not found")
                return
            self._send(200, _build_html(key, token), "text/html")

        def do_POST(self) -> None:
            if self.path != path_prefix:
                self._send(404, "Not found")
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = urllib.parse.parse_qs(body)
            value = params.get("value", [""])[0]
            holder[0] = value
            event.set()
            self.server._done = True  # type: ignore[attr-defined]
            self._send(200, _SUCCESS_HTML, "text/html")

        def _send(self, code: int, body: str, content_type: str = "text/plain") -> None:
            encoded = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    httpd = http.server.HTTPServer((host, port), Handler)
    httpd._done = False  # type: ignore[attr-defined]
    return httpd


def _serve_until_done(httpd: http.server.HTTPServer, timeout_seconds: int) -> None:
    httpd.timeout = 1
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not httpd._done:  # type: ignore[attr-defined]
        httpd.handle_request()
    httpd.server_close()


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def blindfold_list(env_name: str = "") -> list[str]:
    """List all key names in the .env file. Values are never returned."""
    path = env_file.resolve_path(env_name or None, Path.cwd())
    return env_file.read_keys(path)


@mcp.tool()
def blindfold_get(key: str, env_name: str = "") -> str:
    """Return the masked value for a key (never the real value)."""
    path = env_file.resolve_path(env_name or None, Path.cwd())
    value = env_file.read_value(path, key)
    return _mask_value(value) if value is not None else f"Key '{key}' not found"


@mcp.tool()
def blindfold_set(key: str, env_name: str = "") -> str:
    """
    Start secret entry for KEY. Returns a URL for the user to open in their browser.
    After submitting the form, call blindfold_set_confirm(session_id) to complete.
    """
    path = env_file.resolve_path(env_name or None, Path.cwd())
    session_id = str(uuid.uuid4())
    token = secrets.token_hex(16)
    port = int(os.environ.get("BLINDFOLD_PORT", _DEFAULT_PORT))

    event = threading.Event()
    holder: list[Optional[str]] = [None]
    _sessions[session_id] = {
        "key": key,
        "path": path,
        "event": event,
        "holder": holder,
        "token": token,
    }

    httpd = _make_form_server("127.0.0.1", port, key, token, holder, event)
    threading.Thread(
        target=_serve_until_done, args=(httpd, 120), daemon=True
    ).start()

    url = f"http://localhost:{port}/{token}"
    return (
        f"Open this URL in your browser to enter the secret for {key}:\n\n"
        f"  {url}\n\n"
        f"Then call blindfold_set_confirm('{session_id}').\n"
        f"Link expires in 120 seconds."
    )


@mcp.tool()
def blindfold_set_confirm(session_id: str) -> str:
    """
    Wait for the browser form to be submitted, then write the secret to .env.
    Call this after blindfold_set() with the session_id it returned.
    """
    session = _sessions.pop(session_id, None)
    if session is None:
        return "Session not found or already completed."
    event: threading.Event = session["event"]
    holder: list[Optional[str]] = session["holder"]
    key: str = session["key"]
    path: Path = session["path"]

    if not event.wait(timeout=120):
        return f"Timed out waiting for secret input for {key}."
    value = holder[0]
    if value is None:
        return "No value received — form may have been cancelled."
    env_file.set_value(path, key, value)
    return f"Set {key} successfully"


@mcp.tool()
def blindfold_delete(key: str, env_name: str = "") -> str:
    """Delete a key from the .env file."""
    path = env_file.resolve_path(env_name or None, Path.cwd())
    env_file.delete_key(path, key)
    return f"Deleted {key}"


@mcp.tool()
def blindfold_rename(old_key: str, new_key: str, env_name: str = "") -> str:
    """Rename a key in the .env file."""
    path = env_file.resolve_path(env_name or None, Path.cwd())
    env_file.rename_key(path, old_key, new_key)
    return f"Renamed {old_key} → {new_key}"


def main() -> None:
    mcp.run()

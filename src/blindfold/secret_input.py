"""
Secret input methods for blindfold-env.

Provides two ways to obtain a secret value without exposing it to stdout
(and therefore to any AI assistant driving the CLI via stdio):

- GUI dialog:  When stdin is not a terminal (e.g. blindfold is driven by an
               AI assistant), spawns a platform-appropriate GUI dialog
               (pinentry, zenity, kdialog, or osascript) so the user can
               type the secret without it appearing in any terminal output.

               Requires a graphical session (DISPLAY/WAYLAND_DISPLAY on
               Linux, or native macOS GUI).  Falls back to a --clipboard
               hint for headless/SSH environments without a display.

- Clipboard:   Reads the system clipboard via a platform-appropriate
               command-line tool, so the secret never appears on any
               terminal at all.  This is the recommended path when
               blindfold is driven by an AI assistant without a display.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys

import click


# ---------------------------------------------------------------------------
# TTY / GUI dialog input
# ---------------------------------------------------------------------------

def get_secret_from_tty(prompt: str) -> str:
    """Read a secret interactively from a terminal or GUI dialog.

    When stdin is a real TTY (normal interactive use), delegates to
    :func:`getpass.getpass` which reads from ``/dev/tty`` directly.

    When stdin is not a TTY (e.g. blindfold is driven by an AI assistant),
    spawns a GUI password dialog — trying ``pinentry``, ``zenity``,
    ``kdialog``, and ``osascript`` in order — so the user can enter the
    secret without it appearing in any terminal output.

    Parameters
    ----------
    prompt:
        The prompt shown to the user, e.g. ``"Enter value for API_KEY: "``.

    Returns
    -------
    str
        The secret string entered by the user.

    Raises
    ------
    click.ClickException
        If no terminal or GUI dialog is available.
    click.Abort
        If the user cancels the GUI dialog.
    """
    if sys.stdin.isatty():
        try:
            return getpass.getpass(prompt=prompt)
        except OSError as exc:
            raise click.ClickException(
                f"Cannot open /dev/tty for secret input: {exc}\n"
                "Hint: use  blindfold set KEY --clipboard  to read the secret "
                "from your system clipboard instead."
            ) from exc

    # No terminal — try a GUI popup dialog.
    secret = _get_secret_from_gui(prompt)
    if secret is not None:
        return secret

    raise click.ClickException(
        "No usable terminal or GUI dialog found for secret input.\n"
        "Hint: copy the secret to your clipboard, then run:\n"
        "  blindfold set KEY --clipboard"
    )


def _get_secret_from_gui(prompt: str) -> str | None:
    """Try each available GUI dialog tool; return the secret or ``None``.

    On macOS tries ``osascript`` only.
    On Linux/other tries ``pinentry``, ``zenity``, ``kdialog`` in order.
    Returns ``None`` if no tool is available or can open a display.
    Raises :class:`click.Abort` if the user explicitly cancels a dialog.
    """
    if sys.platform == "darwin":
        return _try_osascript(prompt)

    for try_fn in (_try_pinentry, _try_zenity, _try_kdialog):
        result = try_fn(prompt)
        if result is not None:
            return result

    return None


def _has_display() -> bool:
    """Return ``True`` if a graphical display environment variable is set."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _try_pinentry(prompt: str) -> str | None:
    """Invoke ``pinentry`` via the Assuan protocol; return secret or ``None``.

    Returns ``None`` if pinentry is not installed, no display is available,
    or pinentry fails to start.  Raises :class:`click.Abort` if the user
    explicitly cancels (pinentry returns ``ERR`` during ``GETPIN``).
    """
    if not _has_display() or not shutil.which("pinentry"):
        return None

    desc = prompt.rstrip(": ")
    try:
        proc = subprocess.Popen(
            ["pinentry"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None

    try:
        proc.stdout.readline()  # greeting: "OK Pleased to meet you"

        proc.stdin.write(f"SETPROMPT {desc}\n")
        proc.stdin.flush()
        resp = proc.stdout.readline().rstrip("\n")
        if not resp.startswith("OK"):
            return None  # pinentry could not open display or other error

        proc.stdin.write("GETPIN\n")
        proc.stdin.flush()

        secret = None
        while True:
            line = proc.stdout.readline().rstrip("\n")
            if not line:
                break
            if line.startswith("D "):
                secret = line[2:]
            elif line.startswith("OK"):
                break
            elif line.startswith("ERR"):
                raise click.Abort()

        return secret if secret is not None else ""
    finally:
        try:
            proc.stdin.write("BYE\n")
            proc.stdin.flush()
        except OSError:
            pass
        proc.wait()


def _try_zenity(prompt: str) -> str | None:
    """Invoke ``zenity --entry --hide-text``; return secret or ``None``.

    Returns ``None`` if zenity is not installed or no display is available.
    Raises :class:`click.Abort` if the user cancels the dialog.
    """
    if not _has_display() or not shutil.which("zenity"):
        return None

    try:
        result = subprocess.run(
            ["zenity", "--entry", "--hide-text",
             "--title=blindfold", f"--text={prompt}"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        raise click.Abort()

    content = result.stdout
    if content.endswith("\n"):
        content = content[:-1]
    return content


def _try_kdialog(prompt: str) -> str | None:
    """Invoke ``kdialog --password``; return secret or ``None``.

    Returns ``None`` if kdialog is not installed or no display is available.
    Raises :class:`click.Abort` if the user cancels the dialog.
    """
    if not _has_display() or not shutil.which("kdialog"):
        return None

    try:
        result = subprocess.run(
            ["kdialog", "--title", "blindfold", "--password", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        raise click.Abort()

    content = result.stdout
    if content.endswith("\n"):
        content = content[:-1]
    return content


def _try_osascript(prompt: str) -> str | None:
    """Invoke an AppleScript password dialog; return secret or ``None``.

    Returns ``None`` if ``osascript`` is not available.
    Raises :class:`click.Abort` if the user cancels the dialog.
    """
    if not shutil.which("osascript"):
        return None

    script = (
        f'display dialog {prompt!r} '
        'with hidden answer default answer "" '
        'buttons {"Cancel", "OK"} default button "OK"'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        raise click.Abort()

    # stdout: "button returned:OK, text returned:<secret>"
    # Use find() to handle secrets that contain commas.
    marker = "text returned:"
    idx = result.stdout.find(marker)
    if idx != -1:
        content = result.stdout[idx + len(marker):]
        if content.endswith("\n"):
            content = content[:-1]
        return content

    return ""


# ---------------------------------------------------------------------------
# Clipboard input
# ---------------------------------------------------------------------------

# Ordered list of (command, args) to try on Linux.  We prefer xclip because
# it is the most commonly installed, but fall back to xsel.
_LINUX_CLIPBOARD_COMMANDS: list[tuple[str, list[str]]] = [
    ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
    ("xsel", ["xsel", "--clipboard", "--output"]),
]


def get_secret_from_clipboard() -> str:
    """Read the current system clipboard contents.

    Platform detection uses :data:`sys.platform`:

    - **Linux** — tries ``xclip``, then ``xsel``.
    - **macOS** (``darwin``) — uses ``pbpaste``.
    - **Windows / WSL** — uses ``powershell.exe -command Get-Clipboard``.

    Returns
    -------
    str
        The clipboard content with any trailing newline stripped.

    Raises
    ------
    click.ClickException
        If no suitable clipboard tool is found or if the tool exits with a
        non-zero status.
    """
    if sys.platform == "darwin":
        return _run_clipboard_cmd(["pbpaste"], tool_name="pbpaste")

    if sys.platform == "win32" or _is_wsl():
        return _run_clipboard_cmd(
            ["powershell.exe", "-command", "Get-Clipboard"],
            tool_name="powershell.exe",
        )

    # Linux / other Unix
    for tool_name, argv in _LINUX_CLIPBOARD_COMMANDS:
        if shutil.which(tool_name):
            return _run_clipboard_cmd(argv, tool_name=tool_name)

    raise click.ClickException(
        "No clipboard tool found.  Install one of the following:\n"
        "  - xclip   (e.g.  sudo apt install xclip)\n"
        "  - xsel    (e.g.  sudo apt install xsel)"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_wsl() -> bool:
    """Return ``True`` if running inside Windows Subsystem for Linux."""
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _run_clipboard_cmd(argv: list[str], *, tool_name: str) -> str:
    """Run a clipboard command and return its stdout, stripped of trailing newline.

    Raises
    ------
    click.ClickException
        If the command is not found or exits with an error.
    """
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        raise click.ClickException(
            f"Clipboard tool '{tool_name}' not found.\n"
            "Please install it and try again."
        )
    except subprocess.TimeoutExpired:
        raise click.ClickException(
            f"Clipboard tool '{tool_name}' timed out after 5 seconds."
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        msg = f"Clipboard tool '{tool_name}' failed (exit {result.returncode})."
        if stderr:
            msg += f"\n{stderr}"
        raise click.ClickException(msg)

    # Strip exactly one trailing newline — clipboard tools typically append one.
    content = result.stdout
    if content.endswith("\n"):
        content = content[:-1]
    return content

"""
Secret input methods for blindfold-env.

Provides two ways to obtain a secret value without exposing it to stdout
(and therefore to any AI assistant driving the CLI via stdio):

- TTY input:   Opens /dev/tty directly via ``getpass.getpass()`` so the
               user can type or paste a secret interactively.
- Clipboard:   Reads the system clipboard via a platform-appropriate
               command-line tool, so the secret never appears on any
               terminal at all.
"""

from __future__ import annotations

import getpass
import shutil
import subprocess
import sys

import click


# ---------------------------------------------------------------------------
# TTY input
# ---------------------------------------------------------------------------

def get_secret_from_tty(prompt: str) -> str:
    """Read a secret interactively from ``/dev/tty`` via :func:`getpass.getpass`.

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
        If ``/dev/tty`` is not available (e.g. when running inside a
        non-interactive pipe or an AI assistant session without a TTY).
    """
    try:
        return getpass.getpass(prompt=prompt)
    except OSError as exc:
        raise click.ClickException(
            f"Cannot open /dev/tty for secret input: {exc}\n"
            "Hint: use  blindfold set KEY --clipboard  to read the secret "
            "from your system clipboard instead."
        ) from exc


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

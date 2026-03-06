"""
Secret input methods for blindfold-env.

Provides three ways to obtain a secret value without exposing it to stdout
(and therefore to any AI assistant driving the CLI via stdio):

- GUI popup:   Shows a native password dialog on the user's screen via
               osascript (macOS), zenity (Linux), or tkinter (stdlib).
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
from pathlib import Path

import click

_ASSETS = Path(__file__).parent / "assets"
_ICON_ICNS = _ASSETS / "icon.icns"
_ICON_PNG = _ASSETS / "icon.png"


# ---------------------------------------------------------------------------
# GUI popup input
# ---------------------------------------------------------------------------

def get_secret_from_gui(key_name: str, project_name: str) -> str:
    """Show a native GUI password dialog and return the entered value.

    Tries tkinter first (provides show/hide toggle). Falls back to
    platform-native dialogs if tkinter is unavailable:

    - **macOS** — ``osascript`` AppleScript dialog.
    - **Linux** — ``zenity --entry --hide-text`` if installed.

    Parameters
    ----------
    key_name:
        The environment variable name, shown in the dialog prompt.
    project_name:
        The current project name (directory basename), shown for context.

    Returns
    -------
    str
        The secret entered by the user.

    Raises
    ------
    click.Abort
        If the user cancels the dialog or it times out.
    RuntimeError
        If no GUI method is available on this platform.
    """
    try:
        return _gui_tkinter(key_name, project_name)
    except click.Abort:
        raise
    except RuntimeError:
        pass

    if sys.platform == "darwin":
        return _gui_osascript(key_name, project_name)

    if sys.platform == "linux" and shutil.which("zenity"):
        return _gui_zenity(key_name, project_name)

    raise RuntimeError(
        "No GUI dialog available. Use --clipboard or --tty instead."
    )


def _gui_osascript(key_name: str, project_name: str) -> str:
    """macOS: AppleScript dialog with Show/Hide toggle, char count, and empty guard."""
    safe_key = key_name.replace("\\", "\\\\").replace('"', '\\"')
    safe_proj = project_name.replace("\\", "\\\\").replace('"', '\\"')
    icon_clause = (
        f'POSIX file "{_ICON_ICNS}"'
        if _ICON_ICNS.exists()
        else "caution"
    )

    script = f'''tell application (path to frontmost application as text) to activate
set val to ""
set showMode to false
set gaveUp to false
set warnEmpty to false
set basePrompt to "Secret value for {safe_key}:" & return & "Project: {safe_proj}"
repeat
    set suffix to ""
    if warnEmpty then
        set suffix to suffix & return & return & "Value is empty \u2014 type or paste a secret."
    end if
    if length of val > 0 then
        set suffix to suffix & return & (length of val as text) & " characters entered"
    end if
    set fullPrompt to basePrompt & suffix
    if showMode then
        set r to display dialog fullPrompt default answer val \u00ac
            buttons {{"Cancel", "Hide", "Save"}} default button "Save" \u00ac
            with title "Set Secret - blindfold-env" \u00ac
            with icon {icon_clause} giving up after 180
    else
        set r to display dialog fullPrompt default answer val with hidden answer \u00ac
            buttons {{"Cancel", "Show", "Save"}} default button "Save" \u00ac
            with title "Set Secret - blindfold-env" \u00ac
            with icon {icon_clause} giving up after 180
    end if
    if gave up of r then
        set gaveUp to true
        exit repeat
    end if
    set val to text returned of r
    if button returned of r is "Save" then
        if val is "" then
            set warnEmpty to true
        else
            exit repeat
        end if
    else if button returned of r is "Show" then
        set showMode to true
        set warnEmpty to false
    else if button returned of r is "Hide" then
        set showMode to false
        set warnEmpty to false
    end if
end repeat
if gaveUp then
    "__TIMEOUT__"
else
    val
end if
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        raise RuntimeError("osascript not found — cannot show GUI dialog on macOS.")
    except subprocess.TimeoutExpired:
        raise click.Abort()

    if result.returncode != 0:
        # User clicked Cancel or pressed Escape
        raise click.Abort()

    output = result.stdout.rstrip("\n")
    if output == "__TIMEOUT__":
        raise click.Abort()
    return output


def _gui_zenity(key_name: str, project_name: str) -> str:
    """Linux: use zenity --entry --hide-text dialog."""
    text = f"Secret value for {key_name}:\nProject: {project_name}"

    while True:
        cmd = [
                    "zenity",
                    "--entry",
                    "--hide-text",
                    f"--title=Set Secret - blindfold-env",
                    f"--text={text}",
                    "--ok-label=Save",
                ]
        if _ICON_PNG.exists():
            cmd.append(f"--window-icon={_ICON_PNG}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            raise RuntimeError("zenity not found.")
        except subprocess.TimeoutExpired:
            raise click.Abort()

        if result.returncode != 0:
            raise click.Abort()

        content = result.stdout
        if content.endswith("\n"):
            content = content[:-1]

        if content:
            return content

        # Empty value — ask user whether to save it or try again
        confirm = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=Set Secret - blindfold-env",
                "--text=Value is empty. Save an empty secret?",
                "--ok-label=Save Empty",
                "--cancel-label=Try Again",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if confirm.returncode == 0:
            return content  # return ""
        # else loop back and show the entry dialog again


def _gui_tkinter(key_name: str, project_name: str) -> str:
    """Custom tkinter dialog with a show/hide eye toggle, char count, and empty guard."""
    try:
        import tkinter as tk
    except ImportError:
        raise RuntimeError(
            "tkinter is not available. Install it or use --clipboard / --tty instead."
        )

    result: list[str | None] = [None]

    root = tk.Tk()
    root.title("Set Secret \u2014 blindfold-env")
    root.resizable(False, False)
    root.lift()
    root.attributes("-topmost", True)

    if _ICON_PNG.exists():
        try:
            img = tk.PhotoImage(file=str(_ICON_PNG))
            root.iconphoto(True, img)
        except tk.TclError:
            pass

    # Prompt label
    tk.Label(
        root,
        text=f"Secret value for {key_name}:\nProject: {project_name}",
        justify="left",
        padx=20,
        pady=(0, 6),
    ).pack(anchor="w")

    # Entry + eye button on the same row
    entry_frame = tk.Frame(root)
    entry_frame.pack(padx=20, pady=(0, 4))

    entry = tk.Entry(entry_frame, show="\u2022", width=36)
    entry.pack(side=tk.LEFT)
    entry.focus_set()

    def toggle() -> None:
        if entry["show"]:
            entry.config(show="")
            eye_btn.config(text="Hide")
        else:
            entry.config(show="\u2022")
            eye_btn.config(text="Show")

    eye_btn = tk.Button(entry_frame, text="Show", width=5, command=toggle)
    eye_btn.pack(side=tk.LEFT, padx=(6, 0))

    # Live character count label
    count_var = tk.StringVar(value="")
    tk.Label(root, textvariable=count_var, fg="gray", padx=20).pack(anchor="w")

    def on_key_release(event=None) -> None:
        n = len(entry.get())
        count_var.set(f"{n} characters" if n > 0 else "")

    entry.bind("<KeyRelease>", on_key_release)

    # Inline error label (initially empty)
    error_var = tk.StringVar(value="")
    tk.Label(root, textvariable=error_var, fg="red", padx=20).pack(anchor="w")

    # Save / Cancel buttons
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=(4, 16))

    def on_ok(event=None) -> None:
        val = entry.get()
        if not val:
            error_var.set("Value is empty \u2014 type or paste a secret.")
            return
        result[0] = val
        root.destroy()

    def on_cancel(event=None) -> None:
        root.destroy()

    tk.Button(btn_frame, text="Cancel", width=8, command=on_cancel).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text="Save", width=8, command=on_ok, default="active").pack(side=tk.LEFT, padx=6)

    root.bind("<Return>", on_ok)
    root.bind("<Escape>", on_cancel)

    root.mainloop()

    if result[0] is None:
        raise click.Abort()
    return result[0]


# ---------------------------------------------------------------------------
# TTY input
# ---------------------------------------------------------------------------

def get_secret_from_tty(prompt: str) -> str:
    """Read a secret interactively from ``/dev/tty`` via :func:`getpass.getpass`.

    Parameters
    ----------
    prompt:
        The prompt shown to the user, e.g. ``"Secret value for API_KEY: "``.

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

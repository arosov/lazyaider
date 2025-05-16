import subprocess
import os

# This helper is internal to this module
def _run_tmux_command(command_args: list[str], check: bool = True, capture_output: bool = False, text: bool = False) -> subprocess.CompletedProcess:
    """
    Runs a tmux command.
    Lets FileNotFoundError and CalledProcessError (if check=True) propagate.
    """
    return subprocess.run(["tmux"] + command_args, check=check, capture_output=capture_output, text=text)

def send_keys_to_pane(target_pane: str, keys: str, capture_output: bool = False):
    """Sends keys to the specified tmux pane."""
    _run_tmux_command(["send-keys", "-t", target_pane, keys], capture_output=capture_output)

def detach_client(session_name: str):
    """Detaches the client from the specified tmux session."""
    _run_tmux_command(["detach-client", "-s", session_name], capture_output=True)

def kill_session(session_name: str):
    """Kills the specified tmux session."""
    _run_tmux_command(["kill-session", "-t", session_name], capture_output=True)

def session_exists(session_name: str) -> bool:
    """Checks if a tmux session with the given name exists."""
    result = _run_tmux_command(["has-session", "-t", session_name], check=False, capture_output=True, text=True)
    return result.returncode == 0

def new_session(session_name: str, window_name: str = "main", term_width: int | None = None, term_height: int | None = None):
    """Creates a new detached tmux session."""
    cmd_args = ["new-session", "-d", "-s", session_name, "-n", window_name]
    if term_width is not None and term_height is not None:
        cmd_args.extend(["-x", str(term_width), "-y", str(term_height)])
    _run_tmux_command(cmd_args)

def split_window(target_pane: str, horizontal: bool = True, size_specifier: str | None = None):
    """Splits the specified tmux pane. Uses -l for size_specifier (e.g., "15%")."""
    cmd_args = ["split-window"]
    if horizontal:
        cmd_args.append("-h")
    else:
        cmd_args.append("-v")
    if size_specifier:
        cmd_args.extend(["-l", size_specifier])
    cmd_args.extend(["-t", target_pane])
    _run_tmux_command(cmd_args)

def set_global_option(option: str, value: str):
    """Sets a global tmux option."""
    _run_tmux_command(["set-option", "-g", option, value])

def select_pane(target_pane: str):
    """Selects the specified tmux pane."""
    _run_tmux_command(["select-pane", "-t", target_pane])

def attach_session(session_name: str):
    """Replaces the current process with 'tmux attach-session'."""
    # FileNotFoundError will propagate from os.execvp if tmux is not found.
    os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])

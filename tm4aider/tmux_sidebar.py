import subprocess
import os
import sys
from . import tmux_utils # Use relative import within the package

def manage_tmux_session(session_name: str, app_command: str, shell_pane_target: str, app_pane_target: str):
    """
    Manages the tmux session for TM4Aider.
    Creates a new session if one doesn't exist, or restarts the app in an existing session.
    Then attaches to the session.
    """
    try:
        # Check if the tmux session already exists
        if not tmux_utils.session_exists(session_name):
            # Session does not exist, create and configure it
            print(f"Creating and configuring new tmux session: {session_name}")
            # Get current terminal size
            try:
                terminal_size = os.get_terminal_size()
                term_width = terminal_size.columns
                term_height = terminal_size.lines
            except OSError:
                # Fallback if terminal size can't be determined (e.g., not a TTY)
                # Tmux will use its default or the client's size upon attach.
                term_width = None
                term_height = None
                print("Warning: Could not determine terminal size. Tmux will use default sizing.", file=sys.stderr)

            # Create a new detached session.
            tmux_utils.new_session(session_name, window_name="main", term_width=term_width, term_height=term_height)

            # Split pane 0.0 (shell_pane_target) horizontally. New pane (app_pane_target) is to the right.
            tmux_utils.split_window(shell_pane_target, horizontal=True, size_specifier="15%")
            # app_command is now defined before the try block.
            # The following send_keys will use it to start the app in the new pane.
            tmux_utils.send_keys_to_pane(app_pane_target, app_command, capture_output=False)
            tmux_utils.send_keys_to_pane(app_pane_target, "Enter", capture_output=False)
        else:
            # Session exists
            print(f"Session {session_name} exists. Restarting TM4Aider in the right pane.")
            # Send app_command to app_pane_target to restart/ensure it's running
            tmux_utils.send_keys_to_pane(app_pane_target, app_command, capture_output=False)
            tmux_utils.send_keys_to_pane(app_pane_target, "Enter", capture_output=False)

        # Ensure mouse mode is enabled for the session
        tmux_utils.set_global_option("mouse", "on")

        # Set pane border lines to heavy
        tmux_utils.set_global_option("pane-border-lines", "heavy")

        # Select the shell pane to ensure it has focus on attach
        tmux_utils.select_pane(shell_pane_target)

        # Attach to the session
        tmux_utils.attach_session(session_name)

    except FileNotFoundError: # Catches if tmux command itself or os.execvp("tmux") fails
        print("Error: tmux command not found. Please ensure tmux is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e: # subprocess is still needed for this exception type
        print(f"Error during tmux setup: {e.stderr.decode() if e.stderr else e}", file=sys.stderr)
        sys.exit(1)

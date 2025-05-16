import subprocess # Still needed for CalledProcessError
import argparse
import sys
import os
from tm4aider import tmux_utils
from tm4aider.sidebar import Sidebar

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TM4Aider")
    parser.add_argument(
        "--run-in-tmux-pane",
        action="store_true",
        help="Flag to indicate the app is being run inside a designated tmux pane."
    )
    parser.add_argument(
        "--target-pane",
        type=str,
        help="The tmux target pane ID for sending commands (e.g., session_name:window.pane)."
    )
    parser.add_argument(
        "--session-name",
        type=str,
        help="The tmux session name to be managed/killed."
    )

    args = parser.parse_args()

    # Use a consistent session name, whether passed or defined
    # If --session-name is provided (when run inside tmux), use that. Otherwise, use default.
    SESSION_NAME = args.session_name if args.session_name else "tm4aider-session"


    if args.run_in_tmux_pane:
        # This branch is executed when the script is run by tmux to host the Textual app
        if not args.target_pane:
            print("Error: --target-pane is required when --run-in-tmux-pane is set.", file=sys.stderr)
            sys.exit(1)
        if not args.session_name: # session_name is crucial for the kill-session functionality
            print("Error: --session-name is required when --run-in-tmux-pane is set.", file=sys.stderr)
            sys.exit(1)

        Sidebar.TMUX_TARGET_PANE = args.target_pane
        Sidebar.TMUX_SESSION_NAME = args.session_name # Pass session name to app
        app = Sidebar()
        app.run()
    else:
        # This branch is executed when the user runs `python shell_app.py`
        # It sets up or attaches to the tmux session.

        shell_pane_target = f"{SESSION_NAME}:0.0"  # Shell will be in pane 0 of window 0
        app_pane_target = f"{SESSION_NAME}:0.1"    # App will be in pane 1 of window 0 (to the right)

        # Construct the command to run this script (shell_app.py) inside the app_pane_target
        # This recursive call will have --run-in-tmux-pane and --session-name set.
        app_command = (
            f"{sys.executable} {os.path.abspath(sys.argv[0])} "
            f"--run-in-tmux-pane "
            f"--target-pane {shell_pane_target} "
            f"--session-name {SESSION_NAME}"
        )

        try:
            # Check if the tmux session already exists
            if not tmux_utils.session_exists(SESSION_NAME):
                # Session does not exist, create and configure it
                print(f"Creating and configuring new tmux session: {SESSION_NAME}")
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
                tmux_utils.new_session(SESSION_NAME, window_name="main", term_width=term_width, term_height=term_height)

                # Split pane 0.0 (shell_pane_target) horizontally. New pane (app_pane_target) is to the right.
                tmux_utils.split_window(shell_pane_target, horizontal=True, size_specifier="15%")
                # app_command is now defined before the try block.
                # The following send_keys will use it to start the app in the new pane.
                tmux_utils.send_keys_to_pane(app_pane_target, app_command, capture_output=False)
                tmux_utils.send_keys_to_pane(app_pane_target, "Enter", capture_output=False)
            else:
                # Session exists
                print(f"Session {SESSION_NAME} exists. Restarting TM4Aider in the right pane.")
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
            tmux_utils.attach_session(SESSION_NAME)

        except FileNotFoundError: # Catches if tmux command itself or os.execvp("tmux") fails
            print("Error: tmux command not found. Please ensure tmux is installed and in your PATH.", file=sys.stderr)
            sys.exit(1)
        except subprocess.CalledProcessError as e: # subprocess is still needed for this exception type
            print(f"Error during tmux setup: {e.stderr.decode() if e.stderr else e}", file=sys.stderr)
            sys.exit(1)

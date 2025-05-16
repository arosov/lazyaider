import argparse
import sys
import os
from tm4aider.sidebar import Sidebar
from tm4aider.tmux_sidebar import manage_tmux_session # New import

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
        # This branch is executed when the user runs `python tm4aider.py` (or equivalent).
        # It sets up or attaches to the tmux session using the new manage_tmux_session function.

        shell_pane_target = f"{SESSION_NAME}:0.0"  # Shell will be in pane 0 of window 0
        app_pane_target = f"{SESSION_NAME}:0.1"    # App will be in pane 1 of window 0 (to the right)

        # Construct the command to run this script (tm4aider.py) inside the app_pane_target
        # This recursive call will have --run-in-tmux-pane and --session-name set.
        app_command = (
            f"{sys.executable} {os.path.abspath(sys.argv[0])} "
            f"--run-in-tmux-pane "
            f"--target-pane {shell_pane_target} "
            f"--session-name {SESSION_NAME}"
        )

        manage_tmux_session(SESSION_NAME, app_command, shell_pane_target, app_pane_target)

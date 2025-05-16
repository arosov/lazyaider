import argparse
import sys
import os
import uuid # For generating unique default session names if needed

from tm4aider.sidebar import Sidebar
from tm4aider.tmux_sidebar import manage_tmux_session
from tm4aider import config # Import config module
from tm4aider import tmux_utils # Import tmux_utils for session_exists
from tm4aider.session_selector import SessionSelectorApp # Import the new app


DEFAULT_SESSION_BASENAME = "tm4aider-session"

def get_unique_session_name(base_name: str) -> str:
    """Generates a unique session name if the base_name already exists."""
    # This function might be more complex if we need to check against all tmux sessions,
    # but for now, let's assume we just need a new name not in our config.
    # Or, even simpler, tmux itself will fail to create a session if the name is taken.
    # For now, let's just return a simple default or a user-provided one.
    # The session selector will handle new name inputs.
    # If no sessions exist, we'll propose a default.
    
    # Check against existing tmux sessions to suggest a truly unique name
    # if we are creating a *new* default one.
    i = 1
    name_candidate = base_name
    # We only need this if we are *creating* a default session without user input yet.
    # If user provides a name via selector, tmux_utils.new_session will handle if it exists.
    # For now, let's simplify: if no sessions in config, suggest DEFAULT_SESSION_BASENAME.
    # The manage_tmux_session will handle if it's truly new or not.
    return base_name


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

    SESSION_NAME: str | None = None

    if args.run_in_tmux_pane:
        # This branch is executed when the script is run by tmux to host the Textual app
        if not args.target_pane:
            print("Error: --target-pane is required when --run-in-tmux-pane is set.", file=sys.stderr)
            sys.exit(1)
        if not args.session_name: # session_name is crucial for the kill-session functionality
            print("Error: --session-name is required when --run-in-tmux-pane is set.", file=sys.stderr)
            sys.exit(1)
        
        SESSION_NAME = args.session_name
        Sidebar.TMUX_TARGET_PANE = args.target_pane
        Sidebar.TMUX_SESSION_NAME = SESSION_NAME # Pass session name to app
        # Pass config to Sidebar so it can remove session on destroy
        Sidebar.APP_CONFIG = config.settings 
        app = Sidebar()
        app.run()
    else:
        # This branch is executed when the user runs `python tm4aider.py` (or equivalent).
        # It determines the session name, then sets up or attaches to the tmux session.

        managed_sessions_from_config = config.settings.get("managed_sessions", [])
        active_managed_sessions = [
            s_name for s_name in managed_sessions_from_config if tmux_utils.session_exists(s_name)
        ]

        if active_managed_sessions:
            print("Found active managed sessions. Launching selector...")
            selector_app = SessionSelectorApp(active_sessions=active_managed_sessions)
            SESSION_NAME = selector_app.run() # This will block until the app exits
            
            if SESSION_NAME is None:
                print("Session selection cancelled. Exiting.")
                sys.exit(0)
            
            if SESSION_NAME not in managed_sessions_from_config:
                # This means a new session name was entered in the selector
                print(f"New session '{SESSION_NAME}' will be created and added to config.")
                config.add_session_to_config(SESSION_NAME)
            else:
                print(f"Using existing session: {SESSION_NAME}")

        else: # No active managed sessions found in config, or config is empty/new
            print("No active managed sessions found. Proposing a new default session.")
            # For simplicity, we'll use a fixed default name.
            # If it already exists in tmux (but wasn't in our config or wasn't active),
            # manage_tmux_session will handle it (e.g. by re-using or erroring if name collision strategy isn't robust)
            # For now, let's assume manage_tmux_session will create if not exists.
            SESSION_NAME = DEFAULT_SESSION_BASENAME
            
            # Check if this default name is already in tmux but not in our config (e.g. user created it manually)
            # If we want to ensure it's *our* session, we might need more complex naming or checking.
            # For now, if it's not in config, add it. manage_tmux_session will create if it doesn't exist at all.
            if SESSION_NAME not in managed_sessions_from_config:
                 print(f"Default session '{SESSION_NAME}' will be created and added to config.")
                 config.add_session_to_config(SESSION_NAME)
            else: # It was in config, but not active. We'll try to use/recreate it.
                 print(f"Using session from config (currently inactive): {SESSION_NAME}")


        if not SESSION_NAME: # Should not happen if logic above is correct
            print("Error: Session name could not be determined.", file=sys.stderr)
            sys.exit(1)

        shell_pane_target = f"{SESSION_NAME}:0.0"
        app_pane_target = f"{SESSION_NAME}:0.1"

        app_command = (
            f"{sys.executable} {os.path.abspath(sys.argv[0])} "
            f"--run-in-tmux-pane "
            f"--target-pane {shell_pane_target} "
            f"--session-name {SESSION_NAME}"
        )

        manage_tmux_session(SESSION_NAME, app_command, shell_pane_target, app_pane_target)

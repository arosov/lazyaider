import argparse
import sys
import os
import uuid

from lazyaider.sidebar import Sidebar
from lazyaider.tmux_sidebar import manage_tmux_session
from lazyaider import config # Import config module
from lazyaider import tmux_utils # Import tmux_utils for session_exists
from lazyaider.session_selector import SessionSelectorApp # Import the new app

# feature_input_app.FeatureInputApp is no longer directly launched from here.
# It's used by plan_generator.py and section_editor.py.

DEFAULT_SESSION_BASENAME = "lazyaider-session"

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


def main_cli():
    parser = argparse.ArgumentParser(description="Run LazyAider")
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
    parser.add_argument(
        "--load-session",
        type=str,
        help="The tmux session name to load directly, skipping the selector."
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
        # This branch is executed when the user runs `python lazyaider.py` (or equivalent).
        # This script now directly proceeds with tmux session management.
        # Plan generation is handled by plan_generator.py

        if args.load_session:
            SESSION_NAME = args.load_session
            print(f"Loading session '{SESSION_NAME}' directly as requested.")
            # Ensure the loaded session is in config
            current_managed_sessions_dict = config.settings.get(config.KEY_MANAGED_SESSIONS, {})
            if SESSION_NAME not in current_managed_sessions_dict:
                print(f"Adding session '{SESSION_NAME}' to configuration.")
                config.add_session_to_config(SESSION_NAME) # This will save config
            else:
                print(f"Session '{SESSION_NAME}' is already in configuration.")
        else:
            # Original tmux session management logic starts here
            managed_sessions_dict = config.settings.get(config.KEY_MANAGED_SESSIONS, {})
            all_configured_session_names = list(managed_sessions_dict.keys())

            active_managed_sessions = [
                s_name for s_name in all_configured_session_names if tmux_utils.session_exists(s_name)
            ]

            if active_managed_sessions:
                print("Found active managed sessions. Launching selector...")
                selector_app = SessionSelectorApp(
                    active_sessions=active_managed_sessions,
                    default_session_basename=DEFAULT_SESSION_BASENAME
                )
                SESSION_NAME_FROM_SELECTOR = selector_app.run() # This will block until the app exits

                if SESSION_NAME_FROM_SELECTOR is None:
                    print("Session selection cancelled. Exiting.")
                    sys.exit(0)

                # Process any renames that occurred in the selector
                if hasattr(selector_app, 'renamed_map') and selector_app.renamed_map:
                    print("Processing session renames...")
                    for original_name, new_name in selector_app.renamed_map.items():
                        # Check if the original session still exists in tmux before trying to rename
                        # This is important because the renamed_map tracks original names from the start of the dialog
                        if tmux_utils.session_exists(original_name):
                            try:
                                print(f"  Renaming tmux session '{original_name}' to '{new_name}'...")
                                tmux_utils.rename_session(original_name, new_name)
                            except Exception as e:
                                print(f"  Error renaming tmux session '{original_name}' to '{new_name}': {e}", file=sys.stderr)
                                # Decide if we should exit or try to continue. For now, let's print and continue.
                                # The config update below might lead to inconsistencies if tmux rename failed but config changes.
                                # However, SessionNameValidator in RenameSessionScreen should prevent collision with other *managed* sessions.
                                # This error would likely be due to collision with an *unmanaged* tmux session.
                        else:
                            # If original_name doesn't exist, it might have been the source of a rename chain
                            # and the current new_name is its final form.
                            # Or it was killed externally.
                            print(f"  Original tmux session '{original_name}' not found. It might have been already renamed or killed.")

                        # Update configuration: remove old name, add new name.
                        # These functions handle loading and saving the config.
                        config.remove_session_from_config(original_name)
                        config.add_session_to_config(new_name)
                        print(f"  Updated configuration: removed '{original_name}', added '{new_name}'.")

                SESSION_NAME = SESSION_NAME_FROM_SELECTOR # This is the final name to use

                # Ensure the final SESSION_NAME (selected, created, or renamed) is in config.
                # config.settings would have been updated by add_session_to_config / remove_session_from_config
                # if renames or creations happened that modified it.
                current_managed_sessions_dict = config.settings.get(config.KEY_MANAGED_SESSIONS, {})
                if SESSION_NAME not in current_managed_sessions_dict:
                    # This case handles newly created sessions (not renames of existing config items).
                    # Renames are handled by remove(old)/add(new) which updates config.settings.
                    # A session selected from selector_app.run() that was "Create New" path.
                    print(f"Adding new session '{SESSION_NAME}' to configuration.")
                    config.add_session_to_config(SESSION_NAME) # This will save config
                else:
                    print(f"Using session '{SESSION_NAME}' (already in configuration or updated via rename).")

            else: # No active managed sessions found from config, or config is empty/new
                print("No active managed sessions found. Proposing a new default session.")
                SESSION_NAME = DEFAULT_SESSION_BASENAME

                current_managed_sessions_dict = config.settings.get(config.KEY_MANAGED_SESSIONS, {})
                if SESSION_NAME not in current_managed_sessions_dict:
                     print(f"Default session '{SESSION_NAME}' will be created and added to config.")
                     config.add_session_to_config(SESSION_NAME) # This will save config
                else: # It was in config (e.g. as a key in managed_sessions_dict), but not active. We'll try to use/recreate it.
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

if __name__ == "__main__":
    main_cli()

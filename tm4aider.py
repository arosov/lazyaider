import argparse
import sys
import os
from textual.app import App, ComposeResult
from tm4aider import tmux_utils
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Static

class TM4Aider(App):
    """Task Manager for Aider coding assistant"""

    TITLE = "TM4Aider"
    BINDINGS = []  # Removed Ctrl+C binding
    CSS = """
    Screen {
        layout: vertical;
    }
    Horizontal#main_layout {
        height: 1fr; /* Make Horizontal fill available vertical space between Header and Footer */
    }
    #sidebar {
        width: 100%; /* Sidebar takes 20% of the width */
        height: 100%; /* Fill height of parent Horizontal */
        padding: 1;
        border-left: thick $primary-background-darken-2;
        background: $primary-background-lighten-1; /* Slightly different background for sidebar */
    }
    .sidebar-title {
        padding-bottom: 1;
        text-align: center;
        text-style: bold;
        color: $text;
    }
    #sidebar > Button { /* Style buttons directly under sidebar */
        width: 100%;
        margin-bottom: 1;
    }
    """

    # These will be set dynamically when the app is launched by the main script logic
    TMUX_TARGET_PANE: str | None = None
    TMUX_SESSION_NAME: str | None = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="main_layout"):
            # Terminal widget removed
            with VerticalScroll(id="sidebar"):
                yield Static("Controls", classes="sidebar-title")
                yield Button("Start Aider", id="btn_start_aider", variant="success")
                yield Button("Detach Session", id="btn_detach_session", variant="primary")
                yield Button("Quit Session", id="btn_quit_session", variant="error")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events from the sidebar."""
        button_id = event.button.id

        if button_id == "btn_start_aider":
            command_to_run = "aider"
            if self.TMUX_TARGET_PANE:
                try:
                    # Send the command string "aider"
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, command_to_run, capture_output=True)
                    # Send the "Enter" key to execute the command
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter", capture_output=True)
                    self.log(f"Sent command to tmux pane {self.TMUX_TARGET_PANE}: {command_to_run}")
                except FileNotFoundError:
                    self.log.error("Error: tmux command not found. Is tmux installed and in PATH?")
                except subprocess.CalledProcessError as e: # subprocess is still needed for this exception type
                    self.log.error(f"Error sending command to tmux: {e.stderr.decode() if e.stderr else e}")
            else:
                self.log.warning("TMUX_TARGET_PANE is not set. Cannot send command.")

        elif button_id == "btn_detach_session":
            if self.TMUX_SESSION_NAME: # We need a session to detach from
                try:
                    # Detach the client currently attached to this session
                    # If run from within tmux, this will detach the current client.
                    tmux_utils.detach_client(self.TMUX_SESSION_NAME)
                    self.log(f"Detached from tmux session: {self.TMUX_SESSION_NAME}")
                    # The app itself should also quit after detaching,
                    # as it's no longer visible or interactive.
                    await self.action_custom_quit(kill_session=False)
                except FileNotFoundError:
                    self.log.error("Error: tmux command not found when trying to detach.")
                except subprocess.CalledProcessError as e:
                    self.log.error(f"Error detaching from tmux session '{self.TMUX_SESSION_NAME}': {e.stderr.decode() if e.stderr else e}")
            else:
                self.log.warning("TMUX_SESSION_NAME is not set. Cannot detach session.")


        elif button_id == "btn_quit_session":
            await self.action_custom_quit()

    async def action_custom_quit(self, kill_session: bool = True) -> None:
        """Custom quit action that also attempts to kill the tmux session."""
        if kill_session and self.TMUX_SESSION_NAME:
            try:
                tmux_utils.kill_session(self.TMUX_SESSION_NAME)
                self.log(f"Sent kill-session for tmux session: {self.TMUX_SESSION_NAME}")
            except FileNotFoundError:
                self.log.error("Error: tmux command not found when trying to kill session.")
            except subprocess.CalledProcessError as e: # subprocess is still needed for this exception type
                # Log error, but proceed to quit app anyway
                self.log.error(f"Error killing tmux session '{self.TMUX_SESSION_NAME}': {e.stderr.decode() if e.stderr else e}")

        self.app.exit() # Proceed with normal app quit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TM4Aider, optionally managing a tmux session.")
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

        TM4Aider.TMUX_TARGET_PANE = args.target_pane
        TM4Aider.TMUX_SESSION_NAME = args.session_name # Pass session name to app
        app = TM4Aider()
        app.run()
    else:
        # This branch is executed when the user runs `python shell_app.py`
        # It sets up or attaches to the tmux session.

        shell_pane_target = f"{SESSION_NAME}:0.0"  # Shell will be in pane 0 of window 0
        app_pane_target = f"{SESSION_NAME}:0.1"    # App will be in pane 1 of window 0 (to the right)

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
                # Construct the command to run this script (shell_app.py) inside the app_pane_target
                # This recursive call will have --run-in-tmux-pane and --session-name set.
                app_command = (
                    f"{sys.executable} {os.path.abspath(sys.argv[0])} "
                    f"--run-in-tmux-pane "
                    f"--target-pane {shell_pane_target} "
                    f"--session-name {SESSION_NAME}"
                )
                tmux_utils.send_keys_to_pane(app_pane_target, app_command, capture_output=False)
                tmux_utils.send_keys_to_pane(app_pane_target, "Enter", capture_output=False)
            else:
                print(f"Attaching to existing tmux session: {SESSION_NAME}")

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

import subprocess # Still needed for CalledProcessError
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Static
from tm4aider import tmux_utils

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
                yield Button("Destroy Session", id="btn_quit_session", variant="error")
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

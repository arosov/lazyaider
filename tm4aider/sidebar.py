import subprocess # Still needed for CalledProcessError
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Static, Collapsible
from tm4aider import tmux_utils

class Sidebar(App):
    """Task Manager for Aider coding assistant"""

    TITLE = "Sidebar"
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
    /* .sidebar-title is removed as Collapsible provides its own title */
    #sidebar Collapsible Button { /* Style buttons inside Collapsible within #sidebar */
        width: 100%;
        margin-bottom: 1;
    }
    """

    # These will be set dynamically when the app is launched by the main script logic
    TMUX_TARGET_PANE: str | None = None
    TMUX_SESSION_NAME: str | None = None
    APP_CONFIG: dict | None = None # To hold the loaded config settings

    def __init__(self):
        super().__init__()
        # Theme will be set in on_mount

    async def on_mount(self) -> None:
        """Apply theme from config when app is mounted."""
        from tm4aider import config as app_config_module
        theme_name_from_config = app_config_module.settings.get(app_config_module.KEY_THEME_NAME, app_config_module.DEFAULT_THEME_NAME)

        if theme_name_from_config == "dark":
            self.dark = True
        elif theme_name_from_config == "light":
            self.dark = False
        else:
            # For custom themes, they must be registered by the app.
            self.theme = theme_name_from_config
        # App.on_mount() is an empty async method, so no explicit super call is strictly needed here.

    def watch_theme(self, old_theme: str | None, new_theme: str | None) -> None:
        """Saves the theme when it changes."""
        if new_theme is not None:
            from tm4aider import config as app_config_module
            # Only save if it's not one of the built-in ones handled by watch_dark
            if new_theme not in ("light", "dark"):
                app_config_module.update_theme_in_config(new_theme)

    def watch_dark(self, dark: bool) -> None:
        """Saves the theme ("light" or "dark") when App.dark changes."""
        from tm4aider import config as app_config_module
        new_theme_name = "dark" if dark else "light"
        app_config_module.update_theme_in_config(new_theme_name)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="main_layout"):
            # Terminal widget removed
            with VerticalScroll(id="sidebar"):
                with Collapsible(title="Controls", collapsed=False):
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
            session_to_kill = self.TMUX_SESSION_NAME # Capture before it might be cleared
            try:
                # Remove from config before attempting to kill
                # Requires config module and settings to be accessible
                from tm4aider import config as app_config # late import
                app_config.remove_session_from_config(session_to_kill)
                self.log(f"Removed session '{session_to_kill}' from config.")

                tmux_utils.kill_session(session_to_kill)
                self.log(f"Sent kill-session for tmux session: {session_to_kill}")

            except FileNotFoundError:
                self.log.error("Error: tmux command not found when trying to kill session.")
            except subprocess.CalledProcessError as e: # subprocess is still needed for this exception type
                # Log error, but proceed to quit app anyway
                self.log.error(f"Error killing tmux session '{session_to_kill}': {e.stderr.decode() if e.stderr else e}")
            except Exception as e:
                self.log.error(f"An unexpected error occurred during session removal from config: {e}")


        self.app.exit() # Proceed with normal app quit

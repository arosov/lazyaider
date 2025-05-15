from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Terminal, Static

class ShellApp(App):
    """A Textual application to manage a shell session with a command sidebar."""

    TITLE = "Textual Shell"
    CSS = """
    Screen {
        layout: vertical;
    }
    Horizontal#main_layout {
        height: 1fr; /* Make Horizontal fill available vertical space between Header and Footer */
    }
    Terminal {
        width: 3fr; /* Terminal takes 3/4 of the width */
    }
    #sidebar {
        width: 1fr; /* Sidebar takes 1/4 of the width */
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

    # Predefined commands: key is for ID and label generation, value is the command string
    COMMANDS = {
        "ls": "ls -la",
        "pwd": "pwd",
        "date": "date",
        "git_status": "git status",
        "free_space": "df -h",
        "show_python_version": "python --version",
    }

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="main_layout"):
            yield Terminal(id="terminal")
            with VerticalScroll(id="sidebar"):
                yield Static("Quick Commands", classes="sidebar-title")
                for cmd_id in self.COMMANDS:
                    # Generate a user-friendly label from the command ID
                    label = cmd_id.replace("_", " ").capitalize()
                    yield Button(label, id=f"btn_{cmd_id}", variant="primary")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted. Focus the terminal."""
        terminal = self.query_one(Terminal)
        terminal.focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events from the sidebar."""
        terminal = self.query_one(Terminal)
        # Ensure the pressed button has an ID and it starts with "btn_"
        if event.button.id and event.button.id.startswith("btn_"):
            cmd_key = event.button.id[4:]  # Extract command key from button ID (e.g., "ls" from "btn_ls")
            command_to_run = self.COMMANDS.get(cmd_key)
            
            if command_to_run:
                # Send the command to the terminal, appending a newline to execute it.
                terminal.write_text(command_to_run + "\n")
                terminal.focus() # Re-focus the terminal after sending the command

if __name__ == "__main__":
    app = ShellApp()
    app.run()

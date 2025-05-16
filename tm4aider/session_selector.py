import os
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Container
from textual.widgets import Button, Footer, Header, Label, Input, Static, ListView, ListItem
from textual.validation import Regex, Validator, ValidationResult

class SessionNameValidator(Validator):
    def validate(self, value: str) -> ValidationResult:
        # tmux session names cannot contain periods or colons, and must not be empty.
        # For simplicity, let's restrict to alphanumeric and hyphens, not starting/ending with hyphen.
        if not value:
            return self.failure("Session name cannot be empty.")
        if not value[0].isalnum() or not value[-1].isalnum():
             return self.failure("Session name must start and end with an alphanumeric character.")
        if not all(c.isalnum() or c == '-' for c in value):
            return self.failure("Session name can only contain alphanumeric characters and hyphens.")
        if " " in value: # Also disallow spaces for simplicity
            return self.failure("Session name cannot contain spaces.")
        return self.success()


class SessionSelectorApp(App[str | None]):
    """A Textual app to select an existing tmux session or create a new one."""

    TITLE = "TM4Aider Session Selector"
    CSS = """
    Screen {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #session_list_view {
        height: auto;
        max-height: 10; /* Limit height of list view */
        margin-bottom: 1;
        border: round $primary-lighten-2;
    }
    Input {
        margin-bottom: 1;
    }
    Label {
        margin-bottom: 1;
    }
    .button_row {
        width: 100%;
        text-align: center; /* Center buttons */
        margin-top: 1;
    }
    Button {
        min-width: 15; /* Ensure buttons have a decent minimum width */
        margin-left: 1;
        margin-right: 1;
    }
    """

    def __init__(self, active_sessions: list[str]):
        super().__init__()
        self.active_sessions = active_sessions
        self.selected_session_name: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Header(show_clock=False)
            yield Label("Select an active session or create a new one:")

            if self.active_sessions:
                yield Label("Active Sessions:")
                # Use ListView instead of VerticalScroll for list items
                list_view = ListView(id="session_list_view")
                for session in self.active_sessions:
                    # Ensure ListItem children are focusable by default or make Label focusable
                    # Label itself is not focusable by default, ListItem handles focus.
                    # Store the session name in the ListItem's name attribute (passed to constructor) for easy retrieval.
                    list_item = ListItem(Label(session), name=session)
                    list_view.append(list_item)
                yield list_view
            else:
                yield Static("No active managed sessions found.")

            yield Label("Create New Session:")
            yield Input(
                placeholder="Enter new session name (e.g., my-project)",
                id="new_session_name_input",
                validators=[SessionNameValidator()]
            )
            with Container(classes="button_row"):
                yield Button("Use Selected/Create", id="btn_proceed", variant="primary")
                yield Button("Cancel", id="btn_cancel", variant="error")
            yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self.active_sessions:
            self.query_one(ListView).focus()
        else:
            self.query_one("#new_session_name_input").focus()

    async def on_list_item_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        # Clear the input field if a list item is selected
        self.query_one("#new_session_name_input", Input).value = ""
        # Retrieve the session name from the ListItem's name attribute
        if event.item and event.item.name:
            self.selected_session_name = event.item.name


    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_proceed":
            new_session_input = self.query_one("#new_session_name_input", Input)
            new_session_name = new_session_input.value.strip()

            if new_session_name:
                # Validate the new session name
                validation_result = new_session_input.validate(new_session_name)
                if not validation_result or not validation_result.is_valid:
                    new_session_input.border_title = "Validation Error"
                    new_session_input.styles.border = ("round", "red")
                    if validation_result and validation_result.failures:
                        self.notify(validation_result.failures[0].description, title="Invalid Name", severity="error")
                    return # Do not proceed
                else:
                    new_session_input.border_title = None
                    new_session_input.styles.border = None # Reset border

                self.selected_session_name = new_session_name
                self.exit(self.selected_session_name)
            elif self.selected_session_name and self.active_sessions and self.selected_session_name in self.active_sessions:
                # An existing session was selected from the list
                self.exit(self.selected_session_name)
            else:
                # No new name, and no valid existing selection
                self.notify("Please select an existing session or enter a new session name.", title="Selection Required", severity="warning")
        
        elif button_id == "btn_cancel":
            self.exit(None) # Exit without a selection

    def on_input_changed(self, event: Input.Changed) -> None:
        """Clear list selection if user types in input."""
        if event.input.id == "new_session_name_input" and event.value:
            if self.active_sessions:
                try:
                    list_view = self.query_one(ListView)
                    list_view.clear_selection() # Clear selection in the ListView widget
                except Exception: # ListView might not exist if no active_sessions
                    pass 
                self.selected_session_name = None # Also clear internal tracking
            # Reset validation appearance on change
            event.input.border_title = None
            event.input.styles.border = None


if __name__ == "__main__":
    # Example usage:
    app = SessionSelectorApp(active_sessions=["session-alpha", "another-project"])
    selected = app.run()
    print(f"Selected session: {selected}")

    app_no_sessions = SessionSelectorApp(active_sessions=[])
    selected_no_sessions = app_no_sessions.run()
    print(f"Selected session (no initial): {selected_no_sessions}")
    
    # Test with a name that should be valid
    app_valid_new = SessionSelectorApp(active_sessions=[])
    # Simulate user typing 'new-valid-session' and pressing proceed
    # This part is hard to test directly without running the app interactively
    # For now, this just shows how it would be called.
    # selected_valid_new = app_valid_new.run()
    # print(f"Selected session (valid new): {selected_valid_new}")

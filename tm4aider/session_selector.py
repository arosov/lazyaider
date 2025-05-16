import os
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Container # VerticalScroll is not used, but keep for now if other parts might use it.
from textual.widgets import Button, Footer, Header, Label, Input, Static, ListView, ListItem
from textual.validation import Regex, Validator, ValidationResult
from textual.css.query import NoMatches # Changed from textual.errors import QueryError
from textual.screen import ModalScreen
from textual.binding import Binding # For potential future use


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


class RenameSessionScreen(ModalScreen[str | None]):
    """A modal screen to rename a session."""

    CSS = """
    RenameSessionScreen {
        align: center middle;
    }

    #rename_dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    Input { /* Style for Input within this modal */
        margin-bottom: 1;
    }
    
    .button_row { /* Style for button row within this modal */
        width: 100%;
        text-align: center; 
        margin-top: 1;
    }

    Button { /* Style for Buttons within this modal */
        min-width: 15;
        margin-left: 1;
        margin-right: 1;
    }
    """

    def __init__(self, current_name: str, existing_sessions: list[str]):
        super().__init__()
        self.current_name = current_name
        self.existing_sessions = existing_sessions # Other existing session names to check for duplicates

    def compose(self) -> ComposeResult:
        with Container(id="rename_dialog"):
            yield Label(f"Rename session: {self.current_name}")
            yield Input(
                id="new_session_name_input_modal", # Unique ID for this input
                placeholder="Enter new session name",
                validators=[SessionNameValidator()] # Reuse the validator
            )
            with Container(classes="button_row"):
                yield Button("Rename", id="btn_rename_modal", variant="primary")
                yield Button("Cancel", id="btn_cancel_modal", variant="error")

    def on_mount(self) -> None:
        """Focus the input field when the modal is mounted."""
        self.query_one("#new_session_name_input_modal", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses within the modal."""
        if event.button.id == "btn_rename_modal":
            input_widget = self.query_one("#new_session_name_input_modal", Input)
            new_name = input_widget.value.strip()
            
            validation_result = input_widget.validate(new_name)
            if not validation_result or not validation_result.is_valid:
                input_widget.border_title = "Validation Error"
                input_widget.styles.border = ("round", "red")
                if validation_result and validation_result.failures:
                    self.notify(validation_result.failures[0].description, title="Invalid Name", severity="error")
                return

            if new_name == self.current_name: # No change
                self.dismiss(None) # Or self.dismiss(new_name) if you want to signal "no change but confirmed"
                return

            if new_name in self.existing_sessions:
                input_widget.border_title = "Error: Name Exists"
                input_widget.styles.border = ("round", "red")
                self.notify(f"Session '{new_name}' already exists.", title="Name Exists", severity="error")
                return

            input_widget.border_title = None # Clear any previous error styling
            input_widget.styles.border = None
            self.dismiss(new_name) # Dismiss the modal, returning the new name
        elif event.button.id == "btn_cancel_modal":
            self.dismiss(None) # Dismiss the modal, returning None

    def on_input_changed(self, event: Input.Changed) -> None:
        """Reset validation appearance on input change within the modal."""
        if event.input.id == "new_session_name_input_modal":
            event.input.border_title = None
            event.input.styles.border = None


class SessionSelectorApp(App[str | None]):
    """A Textual app to select an existing tmux session or create/rename one."""

    TITLE = "TM4Aider Session Management"
    BINDINGS = [
        Binding("enter", "select_session", "Use Selected", show=False, priority=True),
    ]
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

    def __init__(self, active_sessions: list[str], default_session_basename: str):
        super().__init__()
        self.active_sessions = active_sessions[:] # Work with a copy
        self.default_session_basename = default_session_basename
        self.selected_session_name: str | None = None
        # To track renames: dict[original_name, current_name_after_renames]
        # This is for the caller to know what renames happened if a session is picked after renaming.
        self.renamed_map: dict[str, str] = {}

    def _generate_unique_name_from_base(self, base_name: str, existing_names: list[str]) -> str:
        """Generates a unique name: base_name, then base_name-1, base_name-2, etc."""
        if base_name not in existing_names:
            return base_name
        
        i = 1
        # Loop indefinitely until a unique name is found.
        while True:
            candidate_name = f"{base_name}-{i}"
            if candidate_name not in existing_names:
                return candidate_name
            i += 1

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Header(show_clock=False)
            yield Label("Select an active session, or create/rename a session:")

            if self.active_sessions:
                yield Label("Active Sessions:")
                # ListView will be populated by _populate_session_list if needed
                with ListView(id="session_list_view"): 
                    for session in self.active_sessions:
                        list_item = ListItem(Label(session), name=session)
                        yield list_item
            else:
                yield Static("No active managed sessions found.")
            
            # Buttons for actions
            with Container(classes="button_row"):
                yield Button("Use Selected", id="btn_use_selected", variant="primary", disabled=True)
                yield Button("Rename Selected", id="btn_rename_selected", disabled=True)
            with Container(classes="button_row"):
                yield Button("Create New Session", id="btn_create_new")
                yield Button("Cancel", id="btn_cancel", variant="error")
            yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self.active_sessions:
            list_view = self.query_one(ListView)
            if list_view.children: # Check if there are items in the list view
                list_view.index = 0 # Select the first item
                # on_list_view_selected will be triggered, setting selected_session_name and enabling buttons.
            list_view.focus() # Ensure the list view has focus for keyboard navigation
            # If list_view.index was set, on_list_view_selected handles button states.
            # If list was empty (though self.active_sessions was true), buttons remain disabled.
            if not list_view.children or list_view.index is None or list_view.index < 0 :
                 self.query_one("#btn_use_selected", Button).disabled = True
                 self.query_one("#btn_rename_selected", Button).disabled = True
        else:
            # No sessions, focus on create new button
            self.query_one("#btn_create_new", Button).focus()
            self.query_one("#btn_use_selected", Button).disabled = True 
            self.query_one("#btn_rename_selected", Button).disabled = True

    def _populate_session_list(self) -> None:
        """Populates or repopulates the session list view."""
        try:
            list_view = self.query_one(ListView)
            list_view.clear() # Clear existing items before repopulating
            for session_name in self.active_sessions:
                list_item = ListItem(Label(session_name), name=session_name)
                list_view.append(list_item)
        except NoMatches: 
            # This might happen if the list view isn't present (e.g. no active sessions at start)
            # Or if called at an unexpected time.
            pass

    async def on_list_view_selected(self, event: ListView.Selected) -> None: # Renamed from on_list_item_selected
        """Handle list item selection to enable/disable context-sensitive buttons."""
        if event.item and event.item.name: # event.item should be the selected ListItem
            self.selected_session_name = event.item.name
            self.query_one("#btn_use_selected", Button).disabled = False
            self.query_one("#btn_rename_selected", Button).disabled = False
        else: 
            # This case (no item.name) should ideally not happen if an item is truly selected.
            # Safety net:
            self.selected_session_name = None
            self.query_one("#btn_use_selected", Button).disabled = True
            self.query_one("#btn_rename_selected", Button).disabled = True
    
    def _clear_selection_effects(self) -> None:
        """Clears current selection state and disables related buttons."""
        self.selected_session_name = None
        try:
            list_view = self.query_one(ListView)
            list_view.index = -1 # Deselects in the ListView widget
        except NoMatches:
            pass 
        self.query_one("#btn_use_selected", Button).disabled = True
        self.query_one("#btn_rename_selected", Button).disabled = True

    async def _handle_rename_result(self, new_name: str | None) -> None:
        """Callback function executed after the RenameSessionScreen is dismissed."""
        if new_name and self.selected_session_name: # new_name is not None and a session was selected for rename
            old_name = self.selected_session_name
            
            if old_name == new_name: # No actual change in name
                # Optionally, re-focus list view or provide feedback
                self.query_one(ListView).focus()
                return

            # Update the session name in the internal list
            try:
                idx = self.active_sessions.index(old_name)
                self.active_sessions[idx] = new_name
            except ValueError:
                # This should not happen if selected_session_name was valid from active_sessions
                self.notify(f"Error: Original session '{old_name}' not found in list.", severity="error")
                return # Abort if inconsistent state

            # Update the renamed_map to track changes from original names
            # If old_name was already a renamed name, find its original source
            original_name_for_old_session = old_name
            for original, current_renamed_val in self.renamed_map.items():
                if current_renamed_val == old_name:
                    original_name_for_old_session = original
                    break
            self.renamed_map[original_name_for_old_session] = new_name
            
            # Refresh the ListView to show the new name
            self._populate_session_list()
            
            # Try to re-select the newly renamed item in the ListView
            try:
                list_view = self.query_one(ListView)
                new_item_index = -1
                for i, child_item in enumerate(list_view.children): # Iterate through ListItems
                    if isinstance(child_item, ListItem) and child_item.name == new_name:
                        new_item_index = i
                        break
                
                if new_item_index != -1:
                    list_view.index = new_item_index # Highlight the item
                    self.selected_session_name = new_name # Update internal selection state
                    # Ensure buttons are correctly enabled for the new selection
                    self.query_one("#btn_use_selected", Button).disabled = False
                    self.query_one("#btn_rename_selected", Button).disabled = False
                    list_view.focus() # Ensure the list view has focus
                else:
                    # If item not found (should not happen if _populate_session_list is correct)
                    self._clear_selection_effects() # Clear selection as a fallback
            except NoMatches: # Should not happen if list_view exists
                 self._clear_selection_effects()
        
        # If new_name is None (modal was cancelled), selection remains as it was.
        # Ensure focus returns to an appropriate widget in the main app.
        try:
            self.query_one(ListView).focus()
        except NoMatches: # If no listview (e.g. all sessions deleted then one created and renamed)
            self.query_one("#btn_create_new").focus()


    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn_use_selected":
            if self.selected_session_name:
                # If the selected session was renamed, we want to exit with its *current* name.
                # The self.selected_session_name should already reflect the current name after rename.
                self.exit(self.selected_session_name)
            else:
                # This should not be reachable if button is properly disabled.
                self.notify("Please select a session from the list first.", title="Selection Required", severity="warning")
        
        elif button_id == "btn_rename_selected":
            if self.selected_session_name:
                # Pass other existing session names for validation in the modal
                other_sessions = [s for s in self.active_sessions if s != self.selected_session_name]
                self.app.push_screen(
                    RenameSessionScreen(self.selected_session_name, other_sessions),
                    self._handle_rename_result # Pass the callback
                )
            else:
                # This should not be reachable if button is properly disabled.
                self.notify("Please select a session to rename.", title="Selection Required", severity="warning")

        elif button_id == "btn_create_new":
            # Generate a unique name based on the default and current active sessions
            new_session_name = self._generate_unique_name_from_base(
                self.default_session_basename,
                self.active_sessions 
            )
            # Exit with the new session name. The caller (tm4aider.py) will handle
            # the actual creation and config update.
            self.exit(new_session_name)

        elif button_id == "btn_cancel":
            self.exit(None) # Exit the app, returning None

    async def action_select_session(self) -> None:
        """Action bound to the Enter key. Uses the currently selected session."""
        if self.selected_session_name:
            self.exit(self.selected_session_name)
        # If no session is selected, Enter effectively does nothing in this context,
        # or rather, it won't trigger an exit. Default Textual behavior for Enter might occur
        # depending on focus (e.g., activating a focused button).

if __name__ == "__main__":
    # Example usage:
    example_default_basename = "dev-session" # Define a basename for testing
    initial_sessions = ["session-alpha", "another-project", "beta-test", "dev-session", "dev-session-1"]
    
    print(f"--- Running with initial sessions: {initial_sessions} ---")
    # Pass the default_session_basename to the constructor
    app = SessionSelectorApp(
        active_sessions=initial_sessions,
        default_session_basename=example_default_basename
    )
    selected_session = app.run() 
    print(f"Selected session: {selected_session}")
    # Check if renamed_map exists and print if it does (it's part of the app instance)
    if selected_session and hasattr(app, 'renamed_map') and app.renamed_map:
        print(f"Renamed map: {app.renamed_map}")

    print("\n--- Running with no initial sessions ---")
    app_no_sessions = SessionSelectorApp(
        active_sessions=[],
        default_session_basename=example_default_basename
    )
    selected_no_sessions = app_no_sessions.run()
    print(f"Selected session (no initial): {selected_no_sessions}")
    if selected_no_sessions and hasattr(app_no_sessions, 'renamed_map') and app_no_sessions.renamed_map:
        print(f"Renamed map (no initial): {app_no_sessions.renamed_map}")
    
    # Interactive testing is recommended for the full rename flow.

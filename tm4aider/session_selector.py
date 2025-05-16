import os
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Container # VerticalScroll is not used, but keep for now if other parts might use it.
from textual.widgets import Button, Footer, Header, Label, Input, Static, ListView, ListItem
from textual.widgets.list_view import ListView # Explicit import for subclassing clarity
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
        align-horizontal: center; /* Center buttons horizontally */
        margin-top: 1;
    }

    Button { /* Style for Buttons within this modal */
        width: 17; /* Accommodates "Rename" / "Cancel" with padding */
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

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key press on the input field to attempt rename."""
        if event.input.id == "new_session_name_input_modal":
            # Simulate the "Rename" button press logic
            input_widget = event.input
            new_name = input_widget.value.strip()
            validation_result = input_widget.validate(new_name) # Re-validate on submit
            if not validation_result or not validation_result.is_valid:
                input_widget.border_title = "Validation Error"
                input_widget.styles.border = ("round", "red")
                if validation_result and validation_result.failures:
                    self.notify(validation_result.failures[0].description, title="Invalid Name", severity="error")
                return

            if new_name == self.current_name:
                self.dismiss(None)
                return

            if new_name in self.existing_sessions:
                input_widget.border_title = "Error: Name Exists"
                input_widget.styles.border = ("round", "red")
                self.notify(f"Session '{new_name}' already exists.", title="Name Exists", severity="error")
                return

            input_widget.border_title = None
            input_widget.styles.border = None
            self.dismiss(new_name)


class SessionListView(ListView):
    """Custom ListView to trigger app exit on Enter key press."""

    def action_select_cursor(self) -> None:
        """Called when Enter is pressed (or other selection actions)."""
        super().action_select_cursor()  # Perform default selection logic (posts ListView.Selected)
        # After the default selection logic (which updates highlight and posts message),
        # tell the app to process this as a confirmed selection.
        # self.app will be the SessionSelectorApp instance.
        # We need to ensure action_select_session is awaitable if it becomes async,
        # but actions are typically synchronous unless they schedule work.
        # For now, direct call is fine. If action_select_session becomes async,
        # we might need to self.app.call_later(self.app.action_select_session) or similar.
        # However, action_select_session is currently async.
        # Actions on widgets are typically not async.
        # Let's schedule the call to the async app action.
        self.app.call_later(self.app.action_select_session)


class SessionSelectorApp(App[str | None]):
    """A Textual app to select an existing tmux session or create/rename one."""

    TITLE = "TM4Aider Session Management"
    BINDINGS = [
        Binding("enter", "try_select_session_with_enter", "Use Selected", show=False), # Removed priority=True
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
        align-horizontal: center; /* Center buttons horizontally */
        margin-top: 1;
    }
    Button {
        width: 24; /* Accommodates "Create New Session" with padding */
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

        # self.theme will be set in on_mount

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
                # Use the custom SessionListView
                with SessionListView(id="session_list_view"):
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

    async def on_mount(self) -> None: # Make async
        """Called when app is mounted."""
        # Apply theme from config when app is mounted
        from tm4aider import config as app_config_module
        theme_name_from_config = app_config_module.settings.get("theme_name", app_config_module.DEFAULT_THEME_NAME)
        if theme_name_from_config == "dark":
            self.dark = True
        elif theme_name_from_config == "light":
            self.dark = False
        else:
            # For custom themes, they must be registered by the app.
            # This line might raise InvalidThemeError if 'theme_name_from_config' is not a registered theme.
            self.theme = theme_name_from_config

        list_view = None
        try:
            # ListView is only composed if self.active_sessions is truthy.
            list_view = self.query_one(ListView)
        except NoMatches:
            pass # list_view remains None, handled below.

        if list_view and list_view.children: # Active sessions exist and ListView is populated.
            list_view.index = 0 # Select the first item.
            # Manually update selection state and button states, as setting index
            # programmatically doesn't fire the on_list_view_selected event.
            first_item_widget = list_view.children[0]
            if isinstance(first_item_widget, ListItem) and first_item_widget.name:
                self.selected_session_name = first_item_widget.name
                self.query_one("#btn_use_selected", Button).disabled = False
                self.query_one("#btn_rename_selected", Button).disabled = False
            else:
                # Fallback: if the first item isn't as expected (e.g., no name), keep buttons disabled.
                self.selected_session_name = None # Ensure it's cleared
                self.query_one("#btn_use_selected", Button).disabled = True
                self.query_one("#btn_rename_selected", Button).disabled = True
            list_view.focus()
        else:
            # This block covers:
            # 1. No active sessions (so list_view is None or ListView was not composed).
            # 2. Active sessions, but ListView somehow has no children (e.g., self.active_sessions was empty list).
            self.query_one("#btn_use_selected", Button).disabled = True
            self.query_one("#btn_rename_selected", Button).disabled = True
            try:
                # Focus on "Create New" button as it's the most likely action.
                self.query_one("#btn_create_new", Button).focus()
            except NoMatches:
                # This should ideally not happen if the button is always composed.
                # If it does, focus will fall back to Textual's default.
                pass

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

    async def action_try_select_session_with_enter(self) -> None:
        """
        Attempts to submit the current selection via Enter key,
        but only if no modal screen is active.
        """
        # self.screen_stack[0] is the SessionSelectorApp's main screen.
        # If len > 1, another screen (e.g., modal, command palette) is on top.
        if len(self.screen_stack) == 1:
            await self.action_select_session()
        # If a modal or other screen is active, do nothing, allowing that screen
        # to handle the Enter key.

    async def action_select_session(self) -> None:
        """Action to use the currently selected session. Can be called by button or Enter binding."""
        # Only act if a session is selected AND the ListView has focus.
        # This prevents Enter from triggering session selection when focus is on
        # other elements like the command input in the Footer or command palette.
        try:
            list_view = self.query_one(ListView)
            if list_view.has_focus and self.selected_session_name:
                self.exit(self.selected_session_name)
        except NoMatches:
            # If ListView doesn't exist (e.g., no sessions), this action shouldn't fire.
            pass
        # If conditions are not met (e.g., ListView not focused, or no session selected),
        # Enter should be handled by the focused widget or do nothing if no other
        # binding/handler for Enter exists for that widget.

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

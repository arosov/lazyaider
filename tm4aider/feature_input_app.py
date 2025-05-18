import functools
import time # Add this import
import re # Add this import
import shutil # Add this import
import tempfile
import os
import subprocess
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Button, Static, TextArea, LoadingIndicator, RadioSet, RadioButton # Add RadioSet, RadioButton
from textual.worker import Worker
from textual.timer import Timer # Add this import

# Import the LLM planner function and config
# generate_plan is only used in 'create_plan' mode
# from .llm_planner import generate_plan
from . import config # Import config to access settings like model name
from .tmux_utils import run_command_in_new_window_and_wait

class FeatureInputApp(App[str | tuple[str, str] | None]): # Modified return type
    """
    App for feature description input and plan generation,
    or for editing existing text content (e.g., a plan section).
    """

    BINDINGS = [
        ("escape", "request_quit_or_reset", "Back/Cancel"),
        ("ctrl+e", "open_external_editor", "External Edit"),
    ]
    CSS_PATH = "feature_input_app.tcss"

    # TITLE will be set in on_mount based on mode

    # UI States (primarily for 'create_plan' mode)
    STATE_INPUT_FEATURE = "input_feature"  # Also used by 'edit_section' for the main text area
    STATE_LOADING_PLAN = "loading_plan"    # Only for 'create_plan'
    STATE_DISPLAY_PLAN = "display_plan"    # Only for 'create_plan'

    def __init__(self,
                 mode: str = "create_plan", # "create_plan" or "edit_section"
                 initial_text: str | None = None,
                 window_title: str | None = None):
        super().__init__()
        self.mode = mode
        self.initial_text = initial_text
        self.custom_window_title = window_title

        # Theme will be set in on_mount
        self.current_ui_state = self.STATE_INPUT_FEATURE
        self.generated_plan_content: str | None = None # For 'create_plan' mode
        self.feature_description_content: str | None = None # For 'create_plan' mode (original feature desc)
        
        # LLM related attributes, only for 'create_plan' mode
        self._llm_worker: Worker | None = None
        self._llm_call_start_time: float | None = None
        self._loading_timer: Timer | None = None
        self.repomix_available: bool = False # To track if repomix is available for 'create_plan'


    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="app-container"):
            # Feature Input Area (State 1 / Edit Mode primary view)
            with Vertical(id="feature_input_container"):
                yield Static("Describe the feature you want to implement:", classes="label", id="feature_label") # Text updated in on_mount
                yield TextArea(
                    id="feature_description_input", # Used for feature desc (create) or section content (edit)
                    language="markdown",
                    show_line_numbers=True,
                    soft_wrap=True,
                )
                with Horizontal(id="feature_buttons_container", classes="button-container"):
                    # RadioSet for repomap method (only for 'create_plan' mode)
                    with RadioSet(id="repomap_method_radioset"): # Visibility handled in on_mount
                        yield RadioButton("Aider's repomap", id="radio_aider_repomap", value="aider")
                        yield RadioButton("Repomix like a savage", id="radio_repomix", value="repomix")
                    yield Button("Generate Plan", variant="primary", id="generate_plan_button") # Label updated in on_mount
                    yield Button("Cancel", variant="error", id="cancel_initial_button") # Label updated in on_mount

            # Loading Indicator Area (State 2 - only for 'create_plan' mode)
            with Vertical(id="loading_container", classes="hidden"): # Visibility handled in _set_ui_state
                yield LoadingIndicator(id="spinner")
                yield Static(
                    "This may take a moment. Press Esc to try and cancel.",
                    id="loading_subtext"
                )

            # Plan Display Area (State 3 - only for 'create_plan' mode)
            with Vertical(id="plan_display_container", classes="hidden"): # Visibility handled in _set_ui_state
                yield Static("Generated Plan:", classes="label", id="plan_label") # Text updated in on_mount
                yield TextArea(
                    id="plan_display_area", # Used for LLM output in 'create_plan'
                    language="markdown",
                    show_line_numbers=True,
                    soft_wrap=True,
                    read_only=True,
                )
                with Horizontal(id="plan_buttons_container", classes="button-container"): # Visibility handled in _set_ui_state
                    yield Button("Save Plan & Exit", variant="success", id="save_plan_button")
                    yield Button("Discard & Exit", variant="error", id="discard_plan_button")
        yield Footer()

    def _set_ui_state(self, new_state: str) -> None:
        self.current_ui_state = new_state

        is_edit_mode = self.mode == "edit_section"

        # Main input container is always visible in 'input_feature' state for both modes
        self.query_one("#feature_input_container").set_class(new_state != self.STATE_INPUT_FEATURE, "hidden")
        
        # Loading and plan display containers are only for 'create_plan' mode
        self.query_one("#loading_container").set_class(is_edit_mode or new_state != self.STATE_LOADING_PLAN, "hidden")
        self.query_one("#plan_display_container").set_class(is_edit_mode or new_state != self.STATE_DISPLAY_PLAN, "hidden")
        
        # Plan buttons container (Save/Discard for generated plan) is part of plan_display_container, so implicitly handled.

        if new_state == self.STATE_INPUT_FEATURE: # Focus main text area
            self.query_one("#feature_description_input", TextArea).focus()
        elif not is_edit_mode and new_state == self.STATE_DISPLAY_PLAN: # Focus plan display (only create_plan)
            self.query_one("#plan_display_area", TextArea).focus()


    async def on_mount(self) -> None:
        """Apply theme, configure UI based on mode, and focus the input widget."""
        # Set Title
        if self.custom_window_title:
            self.TITLE = self.custom_window_title
        elif self.mode == "edit_section":
            self.TITLE = "TM4Aider - Edit Section"
        else: # create_plan
            self.TITLE = "TM4Aider - AI Powered Plan Generation"


        # Apply theme from config
        theme_name_from_config = config.settings.get(config.KEY_THEME_NAME, config.DEFAULT_THEME_NAME)
        if theme_name_from_config == "dark":
            self.dark = True
        elif theme_name_from_config == "light":
            self.dark = False
        else:
            # For custom themes, they must be registered by the app.
            # If 'theme_name_from_config' is not a registered theme,
            # Textual will raise an InvalidThemeError.
            # This app currently doesn't register custom themes, so only "light" or "dark"
            # from config will work without error unless Textual has other built-ins.
            try:
                self.theme = theme_name_from_config
            except Exception as e: # Catch potential InvalidThemeError
                # Fallback to default if custom theme fails (e.g., not registered)
                # and print a warning.
                import sys
                print(f"Warning: Failed to set theme '{theme_name_from_config}': {e}. Falling back to default.", file=sys.stderr)
                self.dark = config.DEFAULT_THEME_NAME == "dark"

        # Mode-specific UI setup
        feature_desc_input_widget = self.query_one("#feature_description_input", TextArea)
        generate_button_widget = self.query_one("#generate_plan_button", Button)
        cancel_button_widget = self.query_one("#cancel_initial_button", Button)
        feature_label_widget = self.query_one("#feature_label", Static)
        repomap_radioset_widget = self.query_one("#repomap_method_radioset", RadioSet)
        # The line "repomap_container = repomap_radioset_widget.parent" was removed.
        # Hiding repomap_container (parent of RadioSet) was hiding the entire button row.

        if self.mode == "edit_section":
            feature_desc_input_widget.text = self.initial_text or ""
            generate_button_widget.label = "Save Changes"
            cancel_button_widget.label = "Discard & Exit" # Or "Cancel Edit" - "Discard & Exit" is consistent
            feature_label_widget.update("Edit Section Content:")
            repomap_radioset_widget.display = False # Hide the RadioSet widget itself
            # Ensure loading and plan display areas are hidden from the start for edit_mode
            self.query_one("#loading_container").display = False
            self.query_one("#plan_display_container").display = False
        else: # create_plan mode
            # Check for repomix availability and configure RadioButton
            repomix_path = shutil.which("repomix")
            self.repomix_available = repomix_path is not None
            radio_repomix_button = self.query_one("#radio_repomix", RadioButton)
            if not self.repomix_available:
                radio_repomix_button.disabled = True
                radio_repomix_button.label = "Repomix (not found)"
            repomap_radioset_widget.value = "aider" # Default for create_plan

        self._set_ui_state(self.STATE_INPUT_FEATURE) # Initial state for both modes

    def watch_theme(self, old_theme: str | None, new_theme: str | None) -> None:
        """Saves the theme when it changes."""
        if new_theme is not None:
            # Only save if it's not one of the built-in ones handled by watch_dark
            if new_theme not in ("light", "dark"):
                config.update_theme_in_config(new_theme)

    def watch_dark(self, dark: bool) -> None:
        """Saves the theme ("light" or "dark") when App.dark changes."""
        new_theme_name = "dark" if dark else "light"
        config.update_theme_in_config(new_theme_name)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        description_area = self.query_one("#feature_description_input", TextArea)

        if button_id == "generate_plan_button": # "Generate Plan" or "Save Changes"
            if self.mode == "edit_section":
                edited_text = description_area.text
                self.exit(edited_text) # Return the edited text
            else: # create_plan mode
                description = description_area.text.strip()
                if not description:
                    description_area.border_title = "Description cannot be empty!"
                    description_area.styles.border_type = "heavy"
                    description_area.styles.border_title_color = "red"
                    description_area.styles.border = ("heavy", "red")
                    return
                
                self.feature_description_content = description # Store original feature description

                # Reset border styles
                description_area.border_title = None
                description_area.styles.border_type = None
                description_area.styles.border_title_color = None
                description_area.styles.border = None

                # --- Start LLM plan generation (only for create_plan mode) ---
                # Import generate_plan here to avoid import if not used
                from .llm_planner import generate_plan

                current_model_name = config.settings.get(config.KEY_LLM_MODEL, "Unknown Model")
                loading_text_widget = self.query_one("#loading_subtext", Static)
                loading_text_widget.update(f"Generating plan with {current_model_name}, please wait...")

                self._llm_call_start_time = time.monotonic()
                if self._loading_timer is not None:
                    self._loading_timer.stop()
                self._loading_timer = self.set_interval(0.1, self._update_loading_time)

                self._set_ui_state(self.STATE_LOADING_PLAN)

                if self._llm_worker is not None:
                    await self._llm_worker.cancel()

                selected_repomap_method = self.query_one("#repomap_method_radioset", RadioSet).value
                bound_call_generate_plan = functools.partial(self._call_generate_plan, description, selected_repomap_method, generate_plan)
                self._llm_worker = self.run_worker(bound_call_generate_plan, thread=True)
                # --- End LLM plan generation ---

        elif button_id == "cancel_initial_button": # "Cancel" or "Discard & Exit"
            self.exit(None) # Exit without returning data

        elif button_id == "save_plan_button": # Only for 'create_plan' mode (saves LLM generated plan)
            if self.generated_plan_content is not None and self.feature_description_content is not None:
                # Return tuple for 'create_plan' mode
                self.exit((self.generated_plan_content, self.feature_description_content))
            else:
                self.exit(None)

        elif button_id == "discard_plan_button": # Only for 'create_plan' mode (discards LLM generated plan)
            self.exit(None)

    def _call_generate_plan(self, description: str, repomap_method: str, generate_plan_func) -> None:
        """
        Synchronous wrapper to call generate_plan_func (passed as arg)
        and then update UI from thread. Only for 'create_plan' mode.
        """
        try:
            plan_data = generate_plan_func(description, session_name=None, repomap_method=repomap_method)
            self.call_from_thread(self._handle_plan_generation_result, plan_data)
        except Exception as e:
            error_message = f"# Error During Plan Generation Call\n\nAn unexpected error occurred: {type(e).__name__} - {e}"
            self.call_from_thread(self._handle_plan_generation_result, error_message)


    def _handle_plan_generation_result(self, plan_data: tuple[str, str, int | None] | str) -> None:
        """
        Called from worker thread with the result of plan generation.
        Only for 'create_plan' mode.
        """
        self._llm_worker = None
        plan_display_widget = self.query_one("#plan_display_area", TextArea)
        plan_display_widget.clear()

        if isinstance(plan_data, tuple):
            plan_content, model_name, token_count = plan_data
            self.generated_plan_content = plan_content # Store the actual plan for exit

            display_text = plan_content
            display_text += f"\n\n---\nModel used: {model_name}"
            if token_count is not None:
                display_text += f"\nToken usage: {token_count} tokens"
            else:
                display_text += f"\nToken usage: N/A"
            plan_display_widget.load_text(display_text)
        else: # It's an error string
            self.generated_plan_content = plan_data # Store the error message
            plan_display_widget.load_text(plan_data)

        if self._loading_timer is not None:
            self._loading_timer.stop()
            self._loading_timer = None

        total_elapsed_time_str = ""
        if self._llm_call_start_time is not None: # Use renamed variable
            total_elapsed_time = time.monotonic() - self._llm_call_start_time # Use renamed variable
            total_elapsed_time_str = f"\nTime taken: {total_elapsed_time:.2f} seconds"
            self._llm_call_start_time = None # Reset for next run

        if isinstance(plan_data, tuple):
            # Append time taken to the existing display_text for successful plan
            current_text = plan_display_widget.text
            plan_display_widget.load_text(current_text + total_elapsed_time_str)
        else:
            # For error messages, also append the time taken if available
            current_text = plan_display_widget.text # This is the error message text
            if total_elapsed_time_str: # Only append if time was actually calculated
                plan_display_widget.load_text(current_text + total_elapsed_time_str)
            # If total_elapsed_time_str is empty (e.g. _llm_call_start_time was None),
            # just the error message (already loaded) will be shown.

        self._set_ui_state(self.STATE_DISPLAY_PLAN)
        # Reset loading subtext for next time
        self.query_one("#loading_subtext", Static).update("This may take a moment. Press Esc to try and cancel.")

    def _update_loading_time(self) -> None:
        """Periodically updates the loading subtext with elapsed time."""
        if self._llm_call_start_time is not None and self.current_ui_state == self.STATE_LOADING_PLAN: # Use renamed variable
            elapsed_time = time.monotonic() - self._llm_call_start_time # Use renamed variable
            current_model_name = config.settings.get(config.KEY_LLM_MODEL, "Unknown Model")
            loading_text_widget = self.query_one("#loading_subtext", Static)
            loading_text_widget.update(f"Generating plan with {current_model_name}, please wait... (Elapsed: {elapsed_time:.1f}s)")


    async def action_request_quit_or_reset(self) -> None:
        """Handles Escape key. Behavior depends on mode and current UI state."""
        if self.mode == "edit_section":
            # In edit mode, Esc always means cancel/discard changes
            self.exit(None)
        else: # create_plan mode
            if self.current_ui_state == self.STATE_DISPLAY_PLAN:
                # On plan display (after LLM), Esc discards and exits
                self.exit(None)
            elif self.current_ui_state == self.STATE_LOADING_PLAN:
                # While LLM is loading, Esc attempts to cancel
                if self._loading_timer is not None:
                    self._loading_timer.stop()
                    self._loading_timer = None
                self._llm_call_start_time = None

                if self._llm_worker is not None:
                    await self._llm_worker.cancel()
                    self._llm_worker = None
                    self.query_one("#loading_subtext", Static).update("Cancellation requested... returning to input.")
                    # Use a short delay before resetting UI state to allow message to be seen
                    self.set_timer(0.5, lambda: self._set_ui_state(self.STATE_INPUT_FEATURE))
                else: # Should not happen if worker was supposed to be running
                    self._set_ui_state(self.STATE_INPUT_FEATURE)
            else: # STATE_INPUT_FEATURE (in create_plan mode)
                self.exit(None)

    def _update_text_area_from_external(self, text_content: str | None) -> None:
        """Called from worker thread to update TextArea and handle cleanup."""
        text_area = self.query_one("#feature_description_input", TextArea)
        if text_content is not None:
            # Ensure the text area is editable before trying to load text
            if not text_area.read_only:
                text_area.load_text(text_content)
                self.notify("Content updated from external editor.")
            else:
                self.notify("Text area is read-only. Cannot update from external editor.", severity="warning")
        # If text_content is None, an error was already notified by the worker.
        text_area.focus()

    def _run_external_editor_sync(self, editor_cmd: str, current_text: str, temp_file_path: str) -> None:
        """
        Synchronous part: creates temp file, runs the editor, reads back the file, and cleans up.
        This runs in a worker thread.
        """
        try:
            with open(temp_file_path, "w", encoding="utf-8") as tmpfile_write:
                tmpfile_write.write(current_text)

            # The command for tmux new-window should be a single string for the shell command part
            # Ensure the temp_file_path is quoted to handle spaces or special characters.
            quoted_temp_file_path = f"'{temp_file_path.replace("'", "'\\''")}'" # Basic POSIX sh quoting
            full_editor_command_for_tmux = f"{editor_cmd} {quoted_temp_file_path}"
            
            # Use the utility function from tmux_utils
            # It's configured to not check=True by default, so we check returncode manually.
            # text=True implies utf-8 for capture_output.
            process = run_command_in_new_window_and_wait(
                window_name="TM4Aider-Edit",
                command_to_run=full_editor_command_for_tmux,
                capture_output=True,
                text=True,
                check=False # Explicitly False to match original logic of checking returncode
            )

            if process.returncode != 0:
                error_message = f"External editor process error (code {process.returncode})."
                if process.stderr:
                    error_message += f"\nStderr: {process.stderr.strip()}"
                if process.stdout:
                    error_message += f"\nStdout: {process.stdout.strip()}" # Some editors output to stdout on error
                self.call_from_thread(self.notify, error_message, title="Editor Error", severity="error", timeout=10)
                self.call_from_thread(self._update_text_area_from_external, None) # Signal no update
                return

            with open(temp_file_path, "r", encoding="utf-8") as tmpfile_read:
                updated_text = tmpfile_read.read()
            self.call_from_thread(self._update_text_area_from_external, updated_text)

        except FileNotFoundError: # For tmux command itself
            self.call_from_thread(self.notify, "Error: 'tmux' command not found. Is tmux installed and in PATH?", title="TMUX Error", severity="error", timeout=10)
            self.call_from_thread(self._update_text_area_from_external, None)
        except Exception as e:
            self.call_from_thread(self.notify, f"An unexpected error occurred with the external editor: {e}", title="Editor Error", severity="error", timeout=10)
            self.call_from_thread(self._update_text_area_from_external, None)
        finally:
            try:
                os.remove(temp_file_path)
            except OSError:
                # self.call_from_thread(self.notify, f"Warning: Could not delete temporary file: {temp_file_path}", severity="warning")
                pass # Silently attempt removal

    async def action_open_external_editor(self) -> None:
        """Handles Ctrl+E: Opens content in an external editor via tmux new-window."""
        editor_cmd_str = config.settings.get(config.KEY_TEXT_EDITOR)

        if not editor_cmd_str:
            self.notify(
                "No external text editor is configured.\n"
                "Set 'text_editor: your_editor_command' in '.tm4aider.conf.yml' (e.g., 'text_editor: nano').",
                title="External Editor Not Configured",
                severity="warning",
                timeout=10
            )
            return

        text_area = self.query_one("#feature_description_input", TextArea)
        if text_area.read_only:
            self.notify("Cannot edit read-only text area with external editor.", severity="warning")
            return
            
        current_text = text_area.text

        try:
            # Create a temporary file that persists until manually deleted by _run_external_editor_sync.
            # Suffix .md is important for editors that rely on extension for syntax highlighting.
            fd, temp_file_path = tempfile.mkstemp(suffix=".md", text=True)
            os.close(fd) # Close file descriptor, _run_external_editor_sync will open/write/read/delete.
        except Exception as e:
            self.notify(f"Failed to create temporary file: {e}", title="File Error", severity="error")
            return

        self.notify(f"Opening with '{editor_cmd_str}'. Close editor window/tab to return.", title="External Edit", timeout=5)
        
        # Pass current_text and temp_file_path to the worker.
        # The worker will write current_text to temp_file_path before launching editor.
        self.run_worker(
            functools.partial(self._run_external_editor_sync, editor_cmd_str, current_text, temp_file_path),
            thread=True,
            exclusive=True # Ensure only one external editor instance at a time
        )


if __name__ == "__main__":
    # This __main__ block is for direct testing of the FeatureInputApp.
    # It primarily tests the "create_plan" mode.
    # To test "edit_section" mode, you might run section_editor.py directly,
    # or add CLI arguments here to switch modes for testing.
    import os

    # Define constants for directory names for testing purposes
    TM4AIDER_DIR_NAME_TEST = ".tm4aider"
    PLANS_SUBDIR_NAME_TEST = "plans"

    # Helper functions for plan saving (mirrored from plan_generator.py for test purposes)
    def _extract_plan_title_for_test(markdown_content: str) -> str:
        """Extracts the plan title from the first H1 header in markdown."""
        lines = markdown_content.splitlines()
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("# "):
                title = stripped_line[2:].strip()
                if title:
                    return title
        return "untitled-plan"

    def _sanitize_for_path_for_test(text: str) -> str:
        """Converts a string into a slug suitable for file/directory names."""
        text = text.lower()
        text = re.sub(r'\s+', '-', text)
        text = re.sub(r'[^a-z0-9\-]', '', text)
        text = re.sub(r'-+', '-', text)
        text = text.strip('-')
        if not text:
            return "default-plan-title"
        return text

    # Determine the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    css_file_path = os.path.join(script_dir, "feature_input_app.tcss")

    # Ensure your OPENAI_API_KEY (or other LLM provider key) is set in your environment
    # if you want the LLM call to succeed during direct testing.
    # Also, ensure tm4aider.config and tm4aider.llm_planner are importable from this context.
    # This might require adjusting PYTHONPATH or running from the project root.
    # For simplicity, this example assumes `litellm` and `tm4aider` modules are accessible.

    # Create/update dummy CSS file for testing if it doesn't exist
    css_content = """
    #app-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
        align: center top;
    }
    .hidden { display: none !important; }
    #feature_input_container, #loading_container, #plan_display_container {
        width: 100%; align: center top; padding: 1; gap: 1;
    }
    #loading_container { padding-top: 5; height: 20; align: center middle; }
    #loading_subtext { width: 100%; text-align: center; }
    .label { width: 100%; text-align: center; padding: 1 0; }
    TextArea { width: 90%; max-width: 100%; height: 15; border: round $primary; margin-bottom: 1; }
    #feature_description_input { height: 10; }
    #plan_display_area { height: 20; }
    TextArea:focus { border: round $primary-focus; }
    .button-container { width: 90%; max-width: 100%; align: center middle; padding-top: 1; height: auto; layout: horizontal; grid-size: 2; grid-gutter: 1; }
    Button { width: 100%; }
    """
    os.makedirs(os.path.dirname(css_file_path), exist_ok=True)
    try:
        with open(css_file_path, "w") as f:
            f.write(css_content)
        print(f"Ensure CSS is present/updated at {css_file_path}")
    except IOError as e:
        print(f"Could not write CSS to {css_file_path}: {e}")

    print("Testing FeatureInputApp in 'create_plan' mode. Ensure LLM API keys and dependencies are configured.")
    # Default test is for "create_plan" mode
    app_create = FeatureInputApp(mode="create_plan")
    app_result_create = app_create.run()

    if app_result_create:
        # In 'create_plan' mode, result is a tuple (plan_content, feature_description)
        if isinstance(app_result_create, tuple) and len(app_result_create) == 2:
            plan_content, feature_description = app_result_create

            print("\n--- Generated Plan (from app exit - create_plan mode) ---")
            print(plan_content)

            plan_title = _extract_plan_title_for_test(plan_content)
            sanitized_title = _sanitize_for_path_for_test(plan_title)
            
            plan_dir_name = TM4AIDER_DIR_NAME_TEST
            plans_subdir = PLANS_SUBDIR_NAME_TEST
            save_dir_path = os.path.join(plan_dir_name, plans_subdir, sanitized_title)
            
            try:
                os.makedirs(save_dir_path, exist_ok=True)
                plan_file_path = os.path.join(save_dir_path, f"{sanitized_title}.md")
                with open(plan_file_path, "w", encoding="utf-8") as f_out_plan:
                    f_out_plan.write(plan_content)
                print(f"\nPlan saved to {plan_file_path} (relative to CWD)")

                feature_desc_file_path = os.path.join(save_dir_path, "feature_description.md")
                with open(feature_desc_file_path, "w", encoding="utf-8") as f_out_desc:
                    f_out_desc.write(feature_description)
                print(f"Feature description saved to {feature_desc_file_path} (relative to CWD)")

            except IOError as e_save:
                print(f"\nError saving files for 'create_plan' test: {e_save}")
        else:
            print(f"\nUnexpected result type from 'create_plan' mode: {app_result_create}")
    else:
        print("\n'create_plan' mode: Input/Plan generation cancelled or discarded.")

    # Example of how to test "edit_section" mode (can be run separately or conditionally)
    # print("\nTesting FeatureInputApp in 'edit_section' mode (dummy test)...")
    # dummy_initial_text = "## Section to Edit\n\nThis is some initial content."
    # app_edit = FeatureInputApp(mode="edit_section", initial_text=dummy_initial_text, window_title="Test Edit Mode")
    # app_result_edit = app_edit.run()
    # if app_result_edit is not None:
    #     # In 'edit_section' mode, result is a string (edited_text)
    #     print("\n--- Edited Text (from app exit - edit_section mode) ---")
    #     print(app_result_edit)
    # else:
    #     print("\n'edit_section' mode: Edit cancelled or discarded.")

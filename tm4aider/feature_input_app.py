import functools
import time # Add this import
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Button, Static, TextArea, LoadingIndicator
from textual.worker import Worker
from textual.timer import Timer # Add this import

# Import the LLM planner function and config
from .llm_planner import generate_plan
from . import config # Import config to access settings like model name

class FeatureInputApp(App[str | None]):
    """A Textual app to get feature description, generate a plan, and display it."""

    BINDINGS = [
        ("escape", "request_quit_or_reset", "Back/Cancel"),
    ]
    CSS_PATH = "feature_input_app.tcss"

    TITLE = "TM4Aider - AI Powered Plan Generation"

    # UI States
    STATE_INPUT_FEATURE = "input_feature"
    STATE_LOADING_PLAN = "loading_plan"
    STATE_DISPLAY_PLAN = "display_plan"

    def __init__(self):
        super().__init__()

        # Set theme based on config
        theme_name = config.settings.get("theme_name", config.DEFAULT_THEME_NAME)
        self.dark = theme_name == "dark" # Control theme via self.dark for built-in light/dark

        self.current_ui_state = self.STATE_INPUT_FEATURE
        self.generated_plan_content: str | None = None
        self._llm_worker: Worker | None = None
        self._llm_call_start_time: float | None = None # Renamed to avoid conflict
        self._loading_timer: Timer | None = None


    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="app-container"):
            # Feature Input Area (State 1)
            with Vertical(id="feature_input_container"):
                yield Static("Enter the feature you want to implement:", classes="label", id="feature_label")
                yield TextArea(
                    id="feature_description_input",
                    language="markdown",
                    show_line_numbers=True,
                    soft_wrap=True,
                )
                with Horizontal(id="feature_buttons_container", classes="button-container"):
                    yield Button("Generate Plan", variant="primary", id="generate_plan_button")
                    yield Button("Cancel", variant="error", id="cancel_initial_button")

            # Loading Indicator Area (State 2)
            with Vertical(id="loading_container", classes="hidden"):
                yield LoadingIndicator(id="spinner") # Added ID for CSS targeting
                yield Static(
                    "This may take a moment. Press Esc to try and cancel.",
                    id="loading_subtext"
                    # The 'styles' argument was removed from here.
                    # Styling is handled by tm4aider/feature_input_app.tcss
                )

            # Plan Display Area (State 3)
            with Vertical(id="plan_display_container", classes="hidden"):
                yield Static("Generated Plan:", classes="label", id="plan_label")
                yield TextArea(
                    id="plan_display_area",
                    language="markdown",
                    show_line_numbers=True,
                    soft_wrap=True,
                    read_only=True, # Plan is for display
                )
                with Horizontal(id="plan_buttons_container", classes="button-container"):
                    yield Button("Save Plan & Exit", variant="success", id="save_plan_button")
                    yield Button("Discard & Exit", variant="error", id="discard_plan_button")
                    # yield Button("Edit Feature", variant="default", id="edit_feature_button") # Future enhancement
        yield Footer()

    def _set_ui_state(self, new_state: str) -> None:
        self.current_ui_state = new_state
        self.query_one("#feature_input_container").set_class(new_state != self.STATE_INPUT_FEATURE, "hidden")
        self.query_one("#loading_container").set_class(new_state != self.STATE_LOADING_PLAN, "hidden")
        self.query_one("#plan_display_container").set_class(new_state != self.STATE_DISPLAY_PLAN, "hidden")

        if new_state == self.STATE_INPUT_FEATURE:
            self.query_one("#feature_description_input", TextArea).focus()
        elif new_state == self.STATE_DISPLAY_PLAN:
            self.query_one("#plan_display_area", TextArea).focus()


    async def on_mount(self) -> None:
        """Focus the input widget on mount."""
        self._set_ui_state(self.STATE_INPUT_FEATURE)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "generate_plan_button":
            description_area = self.query_one("#feature_description_input", TextArea)
            description = description_area.text.strip()
            if not description:
                description_area.border_title = "Description cannot be empty!"
                description_area.styles.border_type = "heavy" # Make it more visible
                description_area.styles.border_title_color = "red"
                description_area.styles.border = ("heavy", "red")
                return
            
            description_area.border_title = None # Reset border title
            # Reset border styles by removing the ones applied for the error state.
            # This allows the default CSS to take over again.
            description_area.styles.border_type = None 
            description_area.styles.border_title_color = None
            # If you want to be absolutely sure it reverts to the CSS,
            # you might need to re-apply the original CSS border if it was more complex
            # than just "round $primary". For now, clearing specific overrides is often enough.
            # Or, if the default border is simple, like "round $primary",
            # and you know the resolved color of $primary, you could use that.
            # For now, let's try removing the overrides.
            # If the CSS for TextArea defines a border, it should reappear.
            # If not, we might need to explicitly set it to a known default.
            # A common default might be:
            # description_area.styles.border = ("round", "blue") # or some other known color
            # For now, let's rely on CSS to re-apply.
            # If the CSS for TextArea is `border: round $primary;`, this should work.
            # We can also explicitly remove the 'heavy' and 'red' border if that was the only change.
            # To reset to the CSS-defined style, we clear the inline overrides.
            # Textual will then fall back to the styles defined in feature_input_app.tcss for TextArea.
            description_area.styles.border_type = None 
            description_area.styles.border_title_color = None
            description_area.styles.border = None # This should make it revert to the CSS `border: round $primary;`

            # Get model name for display
            current_model_name = config.settings.get("llm_model", "Unknown Model")
            loading_text_widget = self.query_one("#loading_subtext", Static)
            # Initial message, timer will update it with elapsed time
            loading_text_widget.update(f"Generating plan with {current_model_name}, please wait...")
            
            self._llm_call_start_time = time.monotonic() # Use renamed variable
            if self._loading_timer is not None:
                self._loading_timer.stop() # Should not be running, but good practice
            self._loading_timer = self.set_interval(0.1, self._update_loading_time) # Update frequently for smoothness

            self._set_ui_state(self.STATE_LOADING_PLAN)
            
            if self._llm_worker is not None: # Should not happen, but good practice
                await self._llm_worker.cancel()
            
            bound_call_generate_plan = functools.partial(self._call_generate_plan, description)
            self._llm_worker = self.run_worker(bound_call_generate_plan, thread=True)

        elif button_id == "cancel_initial_button":
            self.exit(None) # Exit without a plan

        elif button_id == "save_plan_button":
            self.exit(self.generated_plan_content) # Exit with the generated plan

        elif button_id == "discard_plan_button":
            self.exit(None) # Exit without a plan
        
    def _call_generate_plan(self, description: str) -> None:
        """Synchronous wrapper to call generate_plan and then update UI from thread."""
        try:
            # generate_plan now returns a tuple (plan_content, model_name, token_count) or an error string
            plan_data = generate_plan(description)
            self.call_from_thread(self._handle_plan_generation_result, plan_data)
        except Exception as e:
            # This catch is for unexpected errors in the _call_generate_plan itself,
            # not for errors returned by generate_plan (which are handled as strings).
            error_message = f"# Error During Plan Generation Call\n\nAn unexpected error occurred: {type(e).__name__} - {e}"
            self.call_from_thread(self._handle_plan_generation_result, error_message)


    def _handle_plan_generation_result(self, plan_data: tuple[str, str, int | None] | str) -> None:
        """Called from worker thread with the result of plan generation."""
        self._llm_worker = None # Clear worker reference
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
            current_model_name = config.settings.get("llm_model", "Unknown Model")
            loading_text_widget = self.query_one("#loading_subtext", Static)
            loading_text_widget.update(f"Generating plan with {current_model_name}, please wait... (Elapsed: {elapsed_time:.1f}s)")


    async def action_request_quit_or_reset(self) -> None:
        """Handles Escape key."""
        if self.current_ui_state == self.STATE_DISPLAY_PLAN:
            # On plan display, Esc discards and exits (same as "Discard & Exit" button)
            self.exit(None)
        elif self.current_ui_state == self.STATE_LOADING_PLAN:
            if self._loading_timer is not None:
                self._loading_timer.stop()
                self._loading_timer = None
            self._llm_call_start_time = None # Use renamed variable

            if self._llm_worker is not None:
                await self._llm_worker.cancel() # Attempt to cancel the worker
                self._llm_worker = None
                self.query_one("#loading_subtext", Static).update("Cancellation requested... returning to input.")
                self.set_timer(0.5, lambda: self._set_ui_state(self.STATE_INPUT_FEATURE)) # Give time for UI update
            else: 
                self._set_ui_state(self.STATE_INPUT_FEATURE)
        else: # STATE_INPUT_FEATURE
            self.exit(None)


if __name__ == "__main__":
    # This __main__ block is for direct testing of the FeatureInputApp.
    # It will create/update a CSS file in the expected location relative to this script.
    import os
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

    print("Testing FeatureInputApp. Ensure LLM API keys and dependencies are configured.")
    app = FeatureInputApp()
    plan = app.run()
    if plan:
        print("\n--- Generated Plan (from app exit) ---")
        print(plan)
        try:
            with open("plan.md", "w", encoding="utf-8") as f_out:
                f_out.write(plan)
            print("\nPlan saved to plan.md (in current directory)")
        except IOError as e_save:
            print(f"\nError saving plan.md: {e_save}")
    else:
        print("\nInput/Plan generation cancelled or discarded.")

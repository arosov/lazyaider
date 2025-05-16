from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Button, Static, TextArea, LoadingIndicator
from textual.worker import Worker # Removed WorkerState as it's not directly used

# Import the LLM planner function and config
from tm4aider.llm_planner import generate_plan
# config is implicitly used by generate_plan, no direct import needed here unless for other settings

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
        self.current_ui_state = self.STATE_INPUT_FEATURE
        self.generated_plan_content: str | None = None
        self._llm_worker: Worker | None = None


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
                yield LoadingIndicator("Generating plan, please wait...")
                yield Static("This may take a moment. Press Esc to try and cancel.", id="loading_subtext")

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
            
            description_area.border_title = None # Reset border
            description_area.styles.border = ("round", "$primary") # Reset to default


            self._set_ui_state(self.STATE_LOADING_PLAN)
            # Run generate_plan in a worker thread to avoid blocking UI
            if self._llm_worker is not None: # Should not happen, but good practice
                await self._llm_worker.cancel()
            self._llm_worker = self.run_worker(self._call_generate_plan, description, thread=True)

        elif button_id == "cancel_initial_button":
            self.exit(None) # Exit without a plan

        elif button_id == "save_plan_button":
            self.exit(self.generated_plan_content) # Exit with the generated plan

        elif button_id == "discard_plan_button":
            self.exit(None) # Exit without a plan
        
    def _call_generate_plan(self, description: str) -> None:
        """Synchronous wrapper to call generate_plan and then update UI from thread."""
        try:
            plan = generate_plan(description)
            self.call_from_thread(self._handle_plan_generation_result, plan)
        except Exception as e:
            error_plan = f"# Error During Plan Generation Call\n\nAn unexpected error occurred: {e}"
            self.call_from_thread(self._handle_plan_generation_result, error_plan)


    def _handle_plan_generation_result(self, plan_content: str) -> None:
        """Called from worker thread with the result of plan generation."""
        self._llm_worker = None # Clear worker reference
        self.generated_plan_content = plan_content
        plan_display_widget = self.query_one("#plan_display_area", TextArea)
        plan_display_widget.clear()
        plan_display_widget.load_text(plan_content)
        self._set_ui_state(self.STATE_DISPLAY_PLAN)


    async def action_request_quit_or_reset(self) -> None:
        """Handles Escape key."""
        if self.current_ui_state == self.STATE_DISPLAY_PLAN:
            # On plan display, Esc discards and exits (same as "Discard & Exit" button)
            self.exit(None)
        elif self.current_ui_state == self.STATE_LOADING_PLAN:
            if self._llm_worker is not None:
                await self._llm_worker.cancel() # Attempt to cancel the worker
                self._llm_worker = None
                # Optionally, provide feedback that cancellation was attempted
                self.query_one("#loading_subtext").update("Cancellation requested... returning to input.")
                # Give a moment for any cancellation to process before switching state
                self.set_timer(0.5, lambda: self._set_ui_state(self.STATE_INPUT_FEATURE))
            else: # Should not happen if worker is active
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

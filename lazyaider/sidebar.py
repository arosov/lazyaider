import asyncio
import random
import subprocess # Still needed for CalledProcessError
import re # For parsing markdown sections
import shutil # For file copying
import sys # To get the current python interpreter path
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical, Grid
from textual.widgets import Button, Footer, Header, Static, Collapsible, Select, Label, Switch
from lazyaider import tmux_utils
from lazyaider.venv_utils import get_venv_activation_prefix # Import the new utility

class Sidebar(App):
    """Task Manager for Aider coding assistant"""

    TITLE = "LazyAider"
    BINDINGS = []
    CSS_PATH = "sidebar.tcss"

    # These will be set dynamically when the app is launched by the main script logic
    TMUX_TARGET_PANE: str | None = None
    TMUX_SESSION_NAME: str | None = None
    APP_CONFIG: dict | None = None # To hold the loaded config settings

    # For storing currently loaded plan details
    current_plan_markdown_content: str | None = None
    current_selected_plan_name: str | None = None

    # Constants for the refresh option in the Select widget
    REFRESH_PLAN_LIST_PROMPT_TEXT: str = "(Refresh plan list)"
    REFRESH_PLAN_LIST_VALUE: str = "_internal_refresh_plans_"

    def __init__(self):
        super().__init__()
        # Theme will be set in on_mount

    async def on_mount(self) -> None:
        """Apply theme from config when app is mounted."""
        from lazyaider import config as app_config_module
        theme_name_from_config = app_config_module.settings.get(app_config_module.KEY_THEME_NAME, app_config_module.DEFAULT_THEME_NAME)

        if theme_name_from_config == "dark":
            self.dark = True
        elif theme_name_from_config == "light":
            self.dark = False
        else:
            # For custom themes, they must be registered by the app.
            self.theme = theme_name_from_config
        # App.on_mount() is an empty async method, so no explicit super call is strictly needed here.

        await self._refresh_plan_list()

    async def _refresh_plan_list(self) -> None:
        """Refreshes the list of available plans in the Select widget."""
        load_plan_select = self.query_one("#sel_load_plan", Select)
        # Store current value to attempt re-selection if Select.BLANK is not the value
        previous_selected_value = load_plan_select.value if load_plan_select.value is not Select.BLANK else None
        if previous_selected_value == self.REFRESH_PLAN_LIST_VALUE:
            previous_selected_value = None # Don't treat refresh action as a persistent selection to restore

        lazyaider_dir_name = ".lazyaider"
        plans_subdir_name = "plans"
        plans_base_path = Path(lazyaider_dir_name) / plans_subdir_name

        plan_options = [(self.REFRESH_PLAN_LIST_PROMPT_TEXT, self.REFRESH_PLAN_LIST_VALUE)] # Always add as first option
        if plans_base_path.is_dir():
            for item in sorted(plans_base_path.iterdir()): # Sort for consistent order
                if item.is_dir():
                    plan_options.append((item.name, item.name)) # Use a tuple (text, value)

        load_plan_select.set_options(plan_options)
        load_plan_select.disabled = False # Always enabled as refresh option is present

        if len(plan_options) > 1: # Actual plans exist (more than just the refresh option)
            load_plan_select.prompt = "Select a plan..."
            # Log count of actual plans, excluding the refresh option itself
            self.log(f"Refreshed plan list. Found {len(plan_options) - 1} actual plans in {plans_base_path}.")
        else: # Only the refresh option exists
            load_plan_select.prompt = "No plans found (Refresh list)"
            self.log(f"No actual plan directories found in {plans_base_path}. 'Load plan' select shows only refresh option.")

        load_plan_select.refresh() # Explicitly refresh the widget

        available_plan_values = [val for _, val in plan_options]
        restored_selection = False

        # Try to restore previously selected value if still valid
        if previous_selected_value and previous_selected_value in available_plan_values:
            load_plan_select.value = previous_selected_value
            self.log(f"Restored previously selected plan '{previous_selected_value}'.")
            restored_selection = True
        # If not restored from previous, try config (only if TMUX_SESSION_NAME is set)
        elif self.TMUX_SESSION_NAME:
            from lazyaider import config as app_config_module # Ensure import
            active_plan_name_from_config = app_config_module.settings.get(app_config_module.KEY_MANAGED_SESSIONS, {})\
                .get(self.TMUX_SESSION_NAME, {})\
                .get(app_config_module.KEY_SESSION_ACTIVE_PLAN_NAME)

            if active_plan_name_from_config and active_plan_name_from_config in available_plan_values:
                load_plan_select.value = active_plan_name_from_config
                self.log(f"Pre-selected plan '{active_plan_name_from_config}' for session '{self.TMUX_SESSION_NAME}' from config.")
                restored_selection = True
            elif active_plan_name_from_config: # Configured plan not found
                self.log.warning(f"Plan '{active_plan_name_from_config}' from config for session '{self.TMUX_SESSION_NAME}' not found in available plans. Ignoring.")

        if not restored_selection and load_plan_select.value is not Select.BLANK and \
           (previous_selected_value is not None and previous_selected_value not in available_plan_values):
            # If a previous selection existed (and it wasn't the refresh action itself being re-evaluated as 'previous')
            # and is no longer valid, and no other selection was made (either restored or from config),
            # explicitly set to BLANK to trigger on_select_changed for clearing.
            # This handles the case where a plan was deleted.
            self.log(f"Previously selected value '{previous_selected_value}' is no longer valid and no other selection restored. Setting Select to BLANK.")
            load_plan_select.value = Select.BLANK

    def watch_theme(self, old_theme: str | None, new_theme: str | None) -> None:
        """Saves the theme when it changes."""
        if new_theme is not None:
            from lazyaider import config as app_config_module
            # Only save if it's not one of the built-in ones handled by watch_dark
            if new_theme not in ("light", "dark"):
                app_config_module.update_theme_in_config(new_theme)

    def watch_dark(self, dark: bool) -> None:
        """Saves the theme ("light" or "dark") when App.dark changes."""
        from lazyaider import config as app_config_module
        new_theme_name = "dark" if dark else "light"
        app_config_module.update_theme_in_config(new_theme_name)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="main_layout"):
            # Terminal widget removed
            with VerticalScroll(id="sidebar"):
                with Collapsible(title="Controls", collapsed=False, id="controls_collapsible"):
                    yield Button("Start Aider", id="btn_start_aider", variant="success")
                    yield Button("Generate plan", id="btn_generate_plan") # Default variant
                    yield Button("Detach Session", id="btn_detach_session", variant="primary")
                    yield Button("Destroy Session", id="btn_quit_session", variant="error")
                with Collapsible(title="Plan", collapsed=True, id="plan_collapsible"): # New section for Plan
                    yield Select([], id="sel_load_plan", prompt="Load plan...")
                    with Horizontal(id="reset_switch_container"):
                        yield Switch(value=True, id="sw_use_reset")
                        yield Label("Use /reset")
                    yield Grid(id="plan_sections_container") # Container for dynamic plan sections
        yield Footer()

    def _parse_markdown_sections(self, markdown_content: str) -> list[str]:
        """Extracts section titles (## Title) from markdown."""
        # Matches lines starting with "## " and captures the text after it.
        sections = re.findall(r"^## (.*)", markdown_content, re.MULTILINE)
        return sections

    def _get_section_content_by_index(self, section_index: int) -> str | None:
        """
        Extracts the content of a specific markdown section by its index.
        A section is defined by a "## Title" header.
        """
        if not self.current_plan_markdown_content:
            self.log.warning("No plan content loaded to extract section from.")
            return None

        # Find all section headers with their start positions
        headers = list(re.finditer(r"^## .*", self.current_plan_markdown_content, re.MULTILINE))

        if not 0 <= section_index < len(headers):
            self.log.error(f"Section index {section_index} is out of bounds (0-{len(headers)-1}).")
            return None

        section_header_match = headers[section_index]
        # Content starts after the header line
        content_start_pos = section_header_match.end()
        # Content ends at the start of the next header, or at the end of the document
        if section_index + 1 < len(headers):
            next_header_match = headers[section_index + 1]
            content_end_pos = next_header_match.start()
        else:
            content_end_pos = len(self.current_plan_markdown_content)

        # Extract the content, strip leading/trailing whitespace from the section block
        section_content = self.current_plan_markdown_content[content_start_pos:content_end_pos].strip()
        return section_content

    def _extract_file_paths(self, text: str) -> list[str]:
        """
        Extracts potential file paths from a string.
        This regex looks for sequences like 'path/to/file.ext' or 'file.ext'.
        It's a best-effort extraction and might not capture all valid paths or might capture non-paths.
        """
        # Regex to find file paths:
        # - (?:[a-zA-Z0-9_.-]+/)* : Optional directory structure (e.g., "dir1/dir2/")
        # - [a-zA-Z0-9_.-]+       : File name part
        # - \.                    : Literal dot for extension
        # Extracts file paths from a markdown bullet list.
        # e.g., "- path/to/file.py", "* `another/file.rs`"
        extracted_paths = []
        lines = text.splitlines()
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("- ") or stripped_line.startswith("* "):
                # Remove the bullet point part
                path_candidate = stripped_line[2:].strip()
                # Remove potential backticks
                if path_candidate.startswith("`") and path_candidate.endswith("`"):
                    path_candidate = path_candidate[1:-1]
                if path_candidate: # Ensure not empty after stripping
                    extracted_paths.append(path_candidate)

        unique_paths = sorted(list(set(extracted_paths)))
        self.log(f"Extracted file paths from markdown list: {unique_paths}")
        return unique_paths

    def _parse_section_content_chunks(self, section_content: str) -> dict[str, str]:
        """
        Parses section content into 'files_md' and 'prompt_content' chunks.
        The 'files_md' chunk is everything before the first double newline.
        The 'prompt_content' chunk is everything after the first double newline.
        """
        parts = section_content.strip().split('\n\n', 1)
        files_md = parts[0] if len(parts) > 0 else ""
        prompt_content = parts[1] if len(parts) > 1 else ""
        return {
            "files_md": files_md,
            "prompt_content": prompt_content,
        }

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events from the sidebar."""
        button_id = event.button.id

        if button_id == "btn_start_aider":
            aider_script_path = Path("aider.sh")
            if aider_script_path.is_file() and aider_script_path.exists():
                command_to_run = "./aider.sh"
                self.log("Found aider.sh, using it to start Aider.")
            else:
                command_to_run = "aider"
                self.log("aider.sh not found, using 'aider' command.")

            if self.TMUX_TARGET_PANE:
                try:
                    # Send the command string
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

        elif button_id == "btn_generate_plan":
            if not self.TMUX_SESSION_NAME:
                self.log.warning("TMUX_SESSION_NAME is not set. Cannot manage plan generator window.")
                return

            plan_generator_window_name = "lazyaider-plan-gen"
            # log_dir and log_file_path are not used here anymore since redirection was removed
            # log_dir = Path(".lazyaider") / "logs"
            # log_file_path = log_dir / "plan_generator.log"
            python_executable = sys.executable
            plan_generator_module = "lazyaider.plan_generator"

            activate_command_part = get_venv_activation_prefix()
            if activate_command_part:
                # Log the part before '&&' to show the source command
                self.log(f"Virtual environment activation prefix generated: {activate_command_part.split('&&')[0].strip()}")
            else:
                self.log.info("No virtual environment activation prefix generated.")

            # Construct the actual command to generate the plan
            actual_plan_command = f"\"{python_executable}\" -m {plan_generator_module}"
            command_to_run = f"{activate_command_part}{actual_plan_command}"

            self.log(f"Constructed command for plan generator: {command_to_run}")

            target_window_specifier = f"{self.TMUX_SESSION_NAME}:{plan_generator_window_name}"
            # Pane 0 is the default initial pane in a new window
            target_pane_for_keys = f"{target_window_specifier}.0"

            try:
                # Try to select the window. If successful, it exists and is now active.
                if tmux_utils.select_window(target_window_specifier):
                    self.log.info(f"Window '{plan_generator_window_name}' exists. Selecting and running command.")
                    # Window exists and is selected, send the command to its first pane.
                    tmux_utils.send_keys_to_pane(target_pane_for_keys, command_to_run)
                    tmux_utils.send_keys_to_pane(target_pane_for_keys, "Enter")
                else:
                    self.log.info(f"Window '{plan_generator_window_name}' does not exist. Creating new window and running command.")
                    # Create the window, run the command in it, and select it (default behavior of create_window).
                    tmux_utils.create_window(self.TMUX_SESSION_NAME, plan_generator_window_name, command_to_run, select=True)

                self.log.info(f"Successfully initiated plan generator in window '{plan_generator_window_name}'.")

            except FileNotFoundError:
                self.log.error("Error: tmux command not found. Is tmux installed and in PATH?")
            except subprocess.CalledProcessError as e:
                # This might be caught if check=True was used somewhere unexpectedly, or if a command truly fails.
                self.log.error(f"Error managing tmux window for plan generator: {e.stderr.decode() if e.stderr else e}")
            except Exception as e:
                self.log.error(f"An unexpected error occurred while managing plan generator window: {e}")

        elif button_id and button_id.startswith("plan_sec_"):
            parts = button_id.split("_")
            section_index = -1  # Ensure section_index is defined for the finally-like color update
            action_type = ""
            try:
                section_index = int(parts[2])
                action_type = parts[3]  # "ask", "code", "arch", or "edit"
            except (IndexError, ValueError) as e:
                self.log.error(f"Error parsing plan section button ID '{button_id}': {e}")
                return # Exit if parsing fails

            if action_type in ("ask", "code", "arch"):
                self.log(f"Plan section Aider command: Index {section_index}, Action: {action_type}")

                if not self.TMUX_TARGET_PANE:
                    self.log.warning("TMUX_TARGET_PANE not set. Cannot send section to Aider.")
                    return

                if not self.current_plan_markdown_content:
                    self.log.warning("No plan content loaded. Cannot process section action.")
                    return

                section_content = self._get_section_content_by_index(section_index)

                if section_content is None:
                    self.log.error(f"Could not retrieve content for section index {section_index}.")
                    return

                # Parse section content into chunks
                content_chunks = self._parse_section_content_chunks(section_content)
                files_md_chunk = content_chunks["files_md"]
                prompt_chunk = content_chunks["prompt_content"]

                # For debug purposes, write each chunk to a separate file
                try:
                    debug_dir = Path(".lazyaider") / "debug_chunks"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    plan_name_for_file = self.current_selected_plan_name or "unknown_plan"
                    base_filename = f"plan_{plan_name_for_file}_sec_{section_index}_{action_type}"

                    files_debug_path = debug_dir / f"{base_filename}_files.md"
                    prompt_debug_path = debug_dir / f"{base_filename}_prompt.txt"

                    files_debug_path.write_text(files_md_chunk, encoding="utf-8")
                    prompt_debug_path.write_text(prompt_chunk, encoding="utf-8")
                    self.log(f"Saved content chunks for sec {section_index} to {debug_dir}")
                except Exception as e:
                    self.log.error(f"Error saving debug chunk files: {e}")

                # Check the "Use /reset" switch state
                reset_switch = self.query_one("#sw_use_reset", Switch)
                if reset_switch.value:
                    try:
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "/reset")
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                        self.log("Sent to Aider: /reset")
                    except Exception as e:
                        self.log.error(f"Error sending /reset command to tmux: {e}")
                        # Decide if we should return or continue. For now, let's continue.

                # Extract file paths from the "files_md" chunk
                potential_file_paths = self._extract_file_paths(files_md_chunk)
                existing_files = []
                if potential_file_paths:
                    for p_path_str in potential_file_paths:
                        # Check relative to CWD, which is typical for Aider
                        if Path(p_path_str).exists() and Path(p_path_str).is_file():
                            existing_files.append(p_path_str)
                        else:
                            self.log(f"File path '{p_path_str}' from 'Files to add' list does not exist or is not a file.")

                if existing_files:
                    files_to_add_str = " ".join(existing_files)
                    add_command = f"/add {files_to_add_str}"
                    try:
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, add_command)
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                        self.log(f"Sent to Aider: {add_command}")
                    except Exception as e:
                        self.log.error(f"Error sending /add command to tmux: {e}")
                        return # Stop if we can't add files

                # Determine the Aider command prefix
                aider_command_prefix = f"/{action_type} " # e.g., "/ask ", "/code ", "/architect "

                full_prompt_content = prompt_chunk.strip()

                try:
                    from lazyaider import config as app_config_module # Ensure access to config
                    delay_value = app_config_module.settings.get(
                        app_config_module.KEY_DELAY_SEND_INPUT,
                        app_config_module.DEFAULT_DELAY_SEND_INPUT
                    )

                    if not full_prompt_content: # Check if content is empty
                        self.log.warning(f"Prompt content for section {section_index} is empty. Sending command prefix '{aider_command_prefix.strip()}' only with Enter.")
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, aider_command_prefix.strip())
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                        return

                    # New sending logic for non-empty content using tags
                    self.log(f"Sending section {section_index} ({action_type}) to Aider using tag-based multiline input.")

                    # Generate a random 8-digit number for the tag
                    tag_id = f"{random.randint(10000000, 99999999)}"
                    opening_tag = f"{{tag{tag_id}"
                    closing_tag = f"tag{tag_id}}}"

                    # 1. Send the opening tag on its own line.
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, opening_tag)
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                    self.log(f"Sent to Aider: {opening_tag}")

                    # 2. Send the command prefix and the full prompt content.
                    # Newlines in full_prompt_content are handled by send_keys_to_pane.
                    content_to_send = f"{aider_command_prefix.strip()} {full_prompt_content}"
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, content_to_send)
                    self.log(f"Sent to Aider (content): {content_to_send[:100]}...")

                    # Ensure content is followed by a newline before the closing tag,
                    # so the closing tag starts on a new line.
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                    self.log("Sent to Aider: Enter (after content to ensure closing tag is on new line)")

                    # 3. Sleep after sending content and its trailing Enter, before closing tag and final submission.
                    await asyncio.sleep(delay_value)

                    # 4. Send the closing tag on its own line.
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, closing_tag)
                    self.log(f"Sent to Aider: {closing_tag}")

                    # 5. Send the final Enter to submit the entire tagged block.
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                    self.log("Sent to Aider: Enter (to submit tagged block)")

                    self.log(f"Submitted command to Aider for section {section_index} ({action_type}) using tag-based input.")

                    # Save the last successfully processed step
                    if self.TMUX_SESSION_NAME and self.current_selected_plan_name:
                        app_config_module.update_session_last_aider_step(
                            self.TMUX_SESSION_NAME,
                            self.current_selected_plan_name,
                            section_index
                        )
                        self.log(f"Saved last Aider step for plan '{self.current_selected_plan_name}', section {section_index}.")

                except Exception as e:
                    self.log.error(f"Error sending command/prompt to tmux: {e}")

            elif action_type == "edit":
                self.log(f"Plan section Edit button: Index {section_index}")
                try:
                    if not self.TMUX_SESSION_NAME:
                        self.log.warning("TMUX_SESSION_NAME not set. Cannot open editor window.")
                        return
                    if not self.current_selected_plan_name:
                        self.log.warning("No plan selected. Cannot determine file to edit.")
                        return

                    lazyaider_dir_name = ".lazyaider"
                    plans_subdir_name = "plans"
                    plan_dir_path = Path(lazyaider_dir_name) / plans_subdir_name / self.current_selected_plan_name
                    active_markdown_filename = f"current-{self.current_selected_plan_name}.md"
                    active_markdown_file_path = plan_dir_path / active_markdown_filename

                    if not active_markdown_file_path.is_file():
                        self.log.error(f"Working plan file not found: {active_markdown_file_path}. Cannot edit.")
                        return

                    editor_window_name = f"lazyaider-edit-s{section_index}-{self.current_selected_plan_name[:10]}"

                    # Use sys.executable for robustness
                    python_executable = sys.executable
                    section_editor_module_path = "lazyaider.section_editor" # Assuming it can be run with -m

                    activate_command_part = get_venv_activation_prefix()
                    if activate_command_part:
                        self.log(f"Using venv activation for section editor: {activate_command_part.split('&&')[0].strip()}")
                    # else: # Optionally log if no venv detected for editor launch
                        # self.log.info("No venv activation for section editor.")

                    actual_editor_command = f"\"{python_executable}\" -m {section_editor_module_path} --file-path \"{active_markdown_file_path.resolve()}\" --section-index {section_index}"
                    command_to_run = f"{activate_command_part}{actual_editor_command}"

                    self.log(f"Constructed command for section editor: {command_to_run}")

                    target_window_specifier = f"{self.TMUX_SESSION_NAME}:{editor_window_name}"
                    target_pane_for_keys = f"{target_window_specifier}.0"

                    if tmux_utils.select_window(target_window_specifier):
                        self.log.info(f"Editor window '{editor_window_name}' exists. Selecting and re-running command.")
                        tmux_utils.send_keys_to_pane(target_pane_for_keys, command_to_run)
                        tmux_utils.send_keys_to_pane(target_pane_for_keys, "Enter")
                    else:
                        self.log.info(f"Editor window '{editor_window_name}' does not exist. Creating.")
                        tmux_utils.create_window(self.TMUX_SESSION_NAME, editor_window_name, command_to_run, select=True)

                    self.log.info(f"Launched section editor for section {section_index} in window '{editor_window_name}'.")
                    self.log.info("IMPORTANT: After editing, re-select the plan from the dropdown to see changes in the sidebar.")

                except FileNotFoundError:
                    self.log.error("Error: tmux command not found. Is tmux installed and in PATH?")
                except subprocess.CalledProcessError as e:
                    self.log.error(f"Error managing tmux window for section editor: {e.stderr.decode() if e.stderr else e}")
                except Exception as e: # Catch any other unexpected error during edit launch
                    self.log.error(f"An unexpected error occurred while launching section editor: {e}")
            else:
                self.log.warning(f"Unknown action type '{action_type}' for button ID '{button_id}'")
                return # Do not proceed to color update if action is unknown

            # After processing any valid plan_sec_ button action, update label colors,
            # but only if the action was not "edit".
            if section_index != -1 and action_type != "edit":
                # This updates colors based on the *just clicked* section.
                # The on_select_changed will handle initial load coloring.
                self._update_section_label_colors(last_processed_index=section_index)


    def _update_section_label_colors(self, last_processed_index: int | None) -> None:
        """Updates the colors of section labels based on the last processed index."""
        from lazyaider import config as app_config_module # Ensure access to config settings
        try:
            plan_sections_container_widget = self.query_one("#plan_sections_container", Grid)
            num_sections = len(plan_sections_container_widget.children)

            completed_color = app_config_module.settings.get(app_config_module.KEY_LABEL_COLOR_COMPLETED, app_config_module.DEFAULT_LABEL_COLOR_COMPLETED)
            current_color = app_config_module.settings.get(app_config_module.KEY_LABEL_COLOR_CURRENT, app_config_module.DEFAULT_LABEL_COLOR_CURRENT)

            for i in range(num_sections):
                try:
                    label_to_style = self.query_one(f"#section_label_{i}", Label)
                    if last_processed_index is not None:
                        if i < last_processed_index:
                            label_to_style.styles.color = completed_color # Completed
                        elif i == last_processed_index:
                            label_to_style.styles.color = current_color  # Current/Last processed
                        else:
                            label_to_style.styles.color = None    # Upcoming (default/CSS)
                    else:
                        label_to_style.styles.color = None # No progress, all default
                except Exception:
                    self.log.warning(f"Could not find label #section_label_{i} for styling during color update.")

            if last_processed_index is not None:
                self.log(f"Updated section label colors based on last processed index: {last_processed_index}.")
            else:
                self.log("Reset section label colors as no last processed index was provided.")
        except Exception as e:
            self.log.error(f"Error updating section label colors: {e}")

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select change events."""
        plan_sections_container = self.query_one("#plan_sections_container", Grid)

        if event.select.id == "sel_load_plan":
            if event.value == self.REFRESH_PLAN_LIST_VALUE:
                self.log("User selected refresh option. Refreshing plan list.")
                # Set Select to BLANK before calling refresh. This achieves:
                # 1. Visually clears the "(Refresh plan list)" text from the Select widget.
                # 2. Ensures _refresh_plan_list (when it reads previous_selected_value) sees None.
                # 3. Queues an on_select_changed event for BLANK, which will run after this handler returns
                #    and after _refresh_plan_list completes (if _refresh_plan_list doesn't set a new value).
                event.select.value = Select.BLANK
                await self._refresh_plan_list()
                # _refresh_plan_list might have set a new value (e.g. restored from config),
                # which would trigger its own on_select_changed.
                # If not, the on_select_changed for BLANK will proceed.
                return # Stop processing this specific "refresh" event.

            # Clear previous sections first (only if not the refresh action)
            await plan_sections_container.remove_children()

            if event.value is not Select.BLANK and event.value is not None:
                # This check ensures we don't try to process REFRESH_PLAN_LIST_VALUE as a plan name
                self.current_selected_plan_name = str(event.value) # Store selected plan name
                self.log(f"Plan selected: {self.current_selected_plan_name}.")

                # Save selected plan to config
                if self.TMUX_SESSION_NAME:
                    from lazyaider import config as app_config_module # late import
                    app_config_module.update_session_active_plan_name(self.TMUX_SESSION_NAME, self.current_selected_plan_name)
                    self.log(f"Saved active plan '{self.current_selected_plan_name}' for session '{self.TMUX_SESSION_NAME}' to config.")
                else:
                    self.log.warning("TMUX_SESSION_NAME not set. Cannot save active plan to config.")

                lazyaider_dir_name = ".lazyaider"
                plans_subdir_name = "plans"
                plan_dir_path = Path(lazyaider_dir_name) / plans_subdir_name / self.current_selected_plan_name

                original_markdown_filename = f"{self.current_selected_plan_name}.md"
                original_markdown_file_path = plan_dir_path / original_markdown_filename

                active_markdown_filename = f"current-{self.current_selected_plan_name}.md"
                active_markdown_file_path = plan_dir_path / active_markdown_filename

                if not original_markdown_file_path.is_file():
                    self.log.error(f"Original plan markdown file not found: {original_markdown_file_path}")
                    self.current_plan_markdown_content = None
                    self.current_selected_plan_name = None
                    await plan_sections_container.mount(Label(f"Original plan file '{original_markdown_filename}' not found in '{plan_dir_path.name}'."))
                    return

                try:
                    shutil.copy2(original_markdown_file_path, active_markdown_file_path)
                    self.log(f"Copied '{original_markdown_file_path}' to '{active_markdown_file_path}'.")
                except (shutil.Error, IOError) as e:
                    self.log.error(f"Error copying plan file from '{original_markdown_file_path}' to '{active_markdown_file_path}': {e}")
                    self.current_plan_markdown_content = None
                    self.current_selected_plan_name = None
                    await plan_sections_container.mount(Label(f"Error creating working copy of plan: {e}"))
                    return

                self.log(f"Loading plan from working copy: {active_markdown_file_path}")

                try:
                    self.current_plan_markdown_content = active_markdown_file_path.read_text(encoding="utf-8") # Store content
                    section_titles = self._parse_markdown_sections(self.current_plan_markdown_content)

                    if not section_titles:
                        await plan_sections_container.mount(Label("No sections (## Title) found in plan."))
                        # Keep self.current_plan_markdown_content as it's valid, just no sections
                        return

                    for i, title in enumerate(section_titles):
                        # Assign an ID to the label for later styling
                        section_label = Label(f"{title.strip()}", id=f"section_label_{i}")
                        ask_button = Button("ask", id=f"plan_sec_{i}_ask", classes="plan_action_button")
                        code_button = Button("code", id=f"plan_sec_{i}_code", classes="plan_action_button")
                        arch_button = Button("arch", id=f"plan_sec_{i}_arch", classes="plan_action_button")
                        edit_button = Button("Edit", id=f"plan_sec_{i}_edit", variant="default", classes="plan_action_button edit_button_style")

                        # Define children when creating the Horizontal container
                        buttons_container = Horizontal(ask_button, code_button, arch_button, edit_button)

                        # Define children when creating the Vertical container for the section item
                        section_item_container = Vertical(
                            section_label,
                            buttons_container,
                            classes="plan_section_item_container"
                        )

                        # Mount the fully constructed item container into the main plan sections container
                        await plan_sections_container.mount(section_item_container)

                    self.log(f"Displayed {len(section_titles)} sections for plan '{self.current_selected_plan_name}'.")

                    # After displaying sections, update colors based on saved progress
                    if self.TMUX_SESSION_NAME and self.current_selected_plan_name:
                        from lazyaider import config as app_config_module # Ensure import
                        last_step = app_config_module.get_session_last_aider_step(
                            self.TMUX_SESSION_NAME,
                            self.current_selected_plan_name
                        )
                        self._update_section_label_colors(last_processed_index=last_step)
                        if last_step is not None:
                            self.log(f"Applied initial section colors based on saved last step: {last_step} for plan '{self.current_selected_plan_name}'.")
                        else:
                            self.log(f"No saved last step found for plan '{self.current_selected_plan_name}'. Default colors applied.")


                except Exception as e:
                    self.log.error(f"Error loading or parsing plan file {active_markdown_file_path}: {e}")
                    self.current_plan_markdown_content = None # Clear on error
                    self.current_selected_plan_name = None
                    await plan_sections_container.mount(Label(f"Error loading plan: {e}"))

            else: # Plan selection cleared or event.value is None/BLANK
                self.log("Plan selection cleared.")
                self.current_plan_markdown_content = None # Clear stored content
                self.current_selected_plan_name = None # Clear stored name
                # Children already cleared at the start of the handler

                # Clear selected plan from config
                if self.TMUX_SESSION_NAME:
                    from lazyaider import config as app_config_module # late import
                    app_config_module.update_session_active_plan_name(self.TMUX_SESSION_NAME, None)
                    self.log(f"Cleared active plan for session '{self.TMUX_SESSION_NAME}' in config.")
                else:
                    self.log.warning("TMUX_SESSION_NAME not set. Cannot clear active plan from config.")

    async def action_custom_quit(self, kill_session: bool = True) -> None:
        """Custom quit action that also attempts to kill the tmux session."""
        if kill_session and self.TMUX_SESSION_NAME:
            session_to_kill = self.TMUX_SESSION_NAME # Capture before it might be cleared
            try:
                # Remove from config before attempting to kill
                # Requires config module and settings to be accessible
                from lazyaider import config as app_config # late import
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

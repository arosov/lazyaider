import subprocess # Still needed for CalledProcessError
import re # For parsing markdown sections
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical, Grid
from textual.widgets import Button, Footer, Header, Static, Collapsible, Select, Label
# SelectOption import removed
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
        background: $primary-background-lighten-1; /* Slightly different background for sidebar */
    }
    #sidebar {
        width: 100%;
        padding: 1;
        border-left: thick $primary-background-darken-2;
        background: $primary-background-lighten-1; /* Slightly different background for sidebar */
    }
    /* .sidebar-title is removed as Collapsible provides its own title */
    #controls_collapsible Button { /* Style buttons inside the Controls Collapsible */
        width: 100%;
        margin-bottom: 0;
        margin-right: 4;
    }
    #sel_load_plan {
        margin-right: 4;
    }
    #plan_sections_container {
        padding: 0 0; /* Add some padding around the sections */
        height: auto; /* Explicitly wrap content */
        /* Grid properties for a single column layout where rows wrap content */
        grid-size: 1; /* Defines one column */
        grid-rows: auto; /* Each row takes the height of its content */
    }
    #plan_sections_container Label {
        margin: 1 0 0 0; /* Margin for section titles */
        text-style: italic;
        width: 100%; /* Ensure label wraps within its container */
        height: auto; /* Explicitly wrap content (label + buttons horizontal) */
    }
    #plan_sections_container Horizontal {
        align: left top;
        margin: 0 0 0 0; /* Margin for button groups */
        height: auto; /* Explicitly wrap content (label + buttons horizontal) */
    }
    .plan_section_item_container {
    }
    .plan_section_item_container {
        height: auto; /* Explicitly wrap content (label + buttons horizontal) */
        align: left top; /* Align label and buttons horizontal to the top-left */
        margin-bottom: 0; /* Add some space between plan items */
    }
    .plan_action_button {
        margin-right: 0; /* Space between action buttons */
        min-width: 6; /* Removed as auto width is desired */
        padding: 0 0; /* Reduce inner padding: 0 for top/bottom, 1 for left/right */
    }
    #plan_collapsible {
        align: left top; /* Aligns the title and the content box to top-left */
        /* overflow_y: auto; /* Removed to let the parent VerticalScroll handle scrolling */
        /* Rely on default height behavior for Collapsible widget. */
    }
    #plan_collapsible > .collapsible-content {
        align: left top; /* Aligns children (Select, plan_sections_container) to top-left */
        height: auto; /* Explicitly set to wrap content */
    }
    """

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

        await self._refresh_plan_list()

    async def _refresh_plan_list(self) -> None:
        """Refreshes the list of available plans in the Select widget."""
        load_plan_select = self.query_one("#sel_load_plan", Select)
        # Store current value to attempt re-selection if Select.BLANK is not the value
        previous_selected_value = load_plan_select.value if load_plan_select.value is not Select.BLANK else None
        if previous_selected_value == self.REFRESH_PLAN_LIST_VALUE:
            previous_selected_value = None # Don't treat refresh action as a persistent selection to restore

        tm4aider_dir_name = ".tm4aider"
        plans_subdir_name = "plans"
        plans_base_path = Path(tm4aider_dir_name) / plans_subdir_name

        plan_options = [(self.REFRESH_PLAN_LIST_PROMPT_TEXT, self.REFRESH_PLAN_LIST_VALUE)] # Always add as first option
        if plans_base_path.is_dir():
            for item in sorted(plans_base_path.iterdir()): # Sort for consistent order
                if item.is_dir():
                    plan_options.append((item.name, item.name)) # Use a tuple (text, value)

        # Check if there are any actual plans beyond the refresh option
        if len(plan_options) > 1: # More than just the refresh option
            load_plan_select.set_options(plan_options)
            load_plan_select.disabled = False
            load_plan_select.prompt = "Select a plan..."
            load_plan_select.refresh() # Explicitly refresh the widget
            self.log(f"Refreshed plan list. Found {len(plan_options)} options in {plans_base_path}.")

            available_plan_values = [val for _, val in plan_options]
            restored_selection = False

            # Try to restore previously selected value if still valid
            if previous_selected_value and previous_selected_value in available_plan_values:
                load_plan_select.value = previous_selected_value
                self.log(f"Restored previously selected plan '{previous_selected_value}'.")
                restored_selection = True
            # If not restored from previous, try config (only if TMUX_SESSION_NAME is set)
            elif self.TMUX_SESSION_NAME:
                from tm4aider import config as app_config_module # Ensure import
                active_plan_name_from_config = app_config_module.settings.get(app_config_module.KEY_MANAGED_SESSIONS, {})\
                    .get(self.TMUX_SESSION_NAME, {})\
                    .get(app_config_module.KEY_SESSION_ACTIVE_PLAN_NAME)

                if active_plan_name_from_config and active_plan_name_from_config in available_plan_values:
                    load_plan_select.value = active_plan_name_from_config
                    self.log(f"Pre-selected plan '{active_plan_name_from_config}' for session '{self.TMUX_SESSION_NAME}' from config.")
                    restored_selection = True
                elif active_plan_name_from_config: # Configured plan not found
                    self.log.warning(f"Plan '{active_plan_name_from_config}' from config for session '{self.TMUX_SESSION_NAME}' not found in available plans. Ignoring.")
            
            if not restored_selection and load_plan_select.value is not Select.BLANK and previous_selected_value not in available_plan_values:
                # If a previous selection existed but is no longer valid, and no other selection was made,
                # explicitly set to BLANK to trigger on_select_changed for clearing.
                load_plan_select.value = Select.BLANK


        else: # No plan_options
            current_value_before_clear = load_plan_select.value
            load_plan_select.set_options([])
            load_plan_select.disabled = True
            load_plan_select.prompt = "No plans available"
            load_plan_select.refresh() # Explicitly refresh the widget
            self.log(f"No plan directories found in {plans_base_path}. 'Load plan' select disabled.")
            
            if current_value_before_clear is not Select.BLANK:
                # If a plan was selected, and now there are no plans, its value will become BLANK.
                # Setting .value to BLANK explicitly ensures on_select_changed is triggered.
                load_plan_select.value = Select.BLANK

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
                with Collapsible(title="Controls", collapsed=False, id="controls_collapsible"):
                    yield Button("Start Aider", id="btn_start_aider", variant="success")
                    yield Button("Generate plan", id="btn_generate_plan") # Default variant
                    yield Button("Refresh plans", id="btn_refresh_plans") # New button
                    yield Button("Detach Session", id="btn_detach_session", variant="primary")
                    yield Button("Destroy Session", id="btn_quit_session", variant="error")
                with Collapsible(title="Plan", collapsed=True, id="plan_collapsible"): # New section for Plan
                    yield Select([], id="sel_load_plan", prompt="Load plan...")
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
        # - [a-zA-Z0-9_.-]+       : File extension part
        # Wrapped in `[\s\`'\"\(]` and `[\s\`'\"\,\.\)]?` to avoid capturing these as part of the path
        # and to allow paths to be at the start/end of lines or surrounded by common delimiters.
        # The actual path is in group 1.
        # Adjusted to be less greedy and more specific to typical file path characters.
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
        Parses section content into 'files_md', 'goals', and 'instructions' chunks.
        Chunks are expected to be separated by an empty line.
        """
        parts = section_content.strip().split('\n\n', 2)
        files_md = parts[0] if len(parts) > 0 else ""
        goals = parts[1] if len(parts) > 1 else ""
        instructions = parts[2] if len(parts) > 2 else ""
        return {
            "files_md": files_md,
            "goals": goals,
            "instructions": instructions,
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

            plan_generator_window_name = "tm4aider-plan-gen"
            command_to_run = "python plan_generator.py" # Use top-level script
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

        elif button_id == "btn_refresh_plans":
            self.log.info("Refresh plans button pressed. Refreshing plan list.")
            await self._refresh_plan_list()

        elif button_id and button_id.startswith("plan_sec_"):
            # Example ID: "plan_sec_0_ask"
            parts = button_id.split("_")
            try:
                section_index = int(parts[2])
                action_type = parts[3] # "ask", "code", or "arch"
                self.log(f"Plan section button: Index {section_index}, Action: {action_type}")

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
                goals_chunk = content_chunks["goals"]
                instructions_chunk = content_chunks["instructions"]

                # For debug purposes, write each chunk to a separate file
                try:
                    debug_dir = Path(".tm4aider") / "debug_chunks"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    plan_name_for_file = self.current_selected_plan_name or "unknown_plan"
                    base_filename = f"plan_{plan_name_for_file}_sec_{section_index}_{action_type}"

                    files_debug_path = debug_dir / f"{base_filename}_files.md"
                    goals_debug_path = debug_dir / f"{base_filename}_goals.txt"
                    instructions_debug_path = debug_dir / f"{base_filename}_instructions.txt"

                    files_debug_path.write_text(files_md_chunk, encoding="utf-8")
                    goals_debug_path.write_text(goals_chunk, encoding="utf-8")
                    instructions_debug_path.write_text(instructions_chunk, encoding="utf-8")
                    self.log(f"Saved content chunks for sec {section_index} to {debug_dir}")
                except Exception as e:
                    self.log.error(f"Error saving debug chunk files: {e}")

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

                # Send the section content prefixed with the command
                # Ensure the content is sent as a single block, handling newlines appropriately.
                # tmux send-keys will interpret newlines in the string as separate "Enter" presses
                # if not handled. However, for Aider, we usually want to paste the whole block.
                # Aider's /ask, /code, etc. usually take the rest of the line as input.
                # If the section_content has newlines, it might be better to send it in a way
                # that Aider can consume it, e.g. by replacing newlines with spaces for a single-line prompt,
                # or by ensuring Aider is in a state to accept multi-line input if that's how it works.
                # For now, let's assume Aider's /ask, /code, /architect commands can handle the content as is,
                # and newlines within the content will be part of the prompt.
                # Aider typically expects the prompt on a single line after the command.
                # Let's replace newlines with spaces to make it a single line prompt.
                # This might lose formatting, but is safer for Aider's command parsing.
                # Alternatively, one could send the command, then paste the content, then send Enter.
                # For simplicity, let's try sending it as one line first.

                # To send multi-line content to Aider, it's often better to use /edit or rely on
                # Aider's ability to read from a temp file or clipboard.
                # Sending raw newlines via send-keys can be problematic.
                # Let's send the command and then the content separately, allowing tmux to handle it.
                # This is still tricky. Aider's /ask, /code, /architect are single-line.
                # The best approach for multi-line content with these commands is often to instruct the user
                # to paste it, or to use a different Aider feature.
                # Given the request, we will send the command and then the content.
                # This implies the content should be on the same "line" as the command for Aider.
                # So, we should probably make section_content a single line.

                # Let's reconsider: Aider's /ask, /code, /architect commands take the rest of the line as the prompt.
                # If section_content has newlines, it will break.
                # The most straightforward way is to make section_content a single line.
                # However, the user asked to "send the rest of the markdown content of the section".
                # This implies preserving it.
                # A common pattern for sending multi-line text to a CLI via tmux is to use a heredoc or paste.
                # Aider doesn't directly support heredocs for these commands.
                #
                # Let's assume for now that the user wants the raw section content sent, and will deal with
                # Aider's interpretation. We will send the command, then the content, then Enter.
                # This means the content will appear on a new line after the command in the terminal.
                # This is NOT how /ask, /code, /architect work. They expect the prompt on the same line.
                #
                # The request: "Then send the rest of the markdown content of the section using /ask /code or /architect as a prefix according to the button."
                # This strongly implies: `/ask <content_here>`
                # So, the content MUST be on one line or escaped.
                # Let's replace newlines with a space for the prompt.
                # Construct the full prompt content from goals and instructions
                full_prompt_parts = []
                stripped_goals = goals_chunk.strip()
                stripped_instructions = instructions_chunk.strip()

                if stripped_goals:
                    full_prompt_parts.append(stripped_goals)
                if stripped_instructions:
                    full_prompt_parts.append(stripped_instructions)

                full_prompt_content = "\n\n".join(full_prompt_parts)

                try:
                    if not full_prompt_content.strip(): # Check if combined content is empty
                        self.log.warning(f"Both goals and instructions for section {section_index} are empty. Sending command prefix '{aider_command_prefix.strip()}' only.")
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, aider_command_prefix.strip())
                        tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                        return

                    prompt_lines = full_prompt_content.split('\n')

                    # Send the command prefix and the first line of the combined prompt
                    first_prompt_line = prompt_lines[0]
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, f"{aider_command_prefix}{first_prompt_line}")
                    self.log(f"Sent to Aider (first prompt line): {aider_command_prefix.strip()} {first_prompt_line[:50]}...")

                    # Send subsequent prompt lines with M-Enter
                    for i, line in enumerate(prompt_lines[1:]):
                        if line.strip():
                            tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "M-Enter") # Alt+Enter for newline in prompt
                            tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, f" {line}")
                        self.log(f"Sent to Aider (prompt line {i+2}): {line[:50]}...")

                    # Finally, send Enter to submit the whole command
                    tmux_utils.send_keys_to_pane(self.TMUX_TARGET_PANE, "Enter")
                    self.log(f"Submitted multi-line command to Aider for section {section_index} ({action_type}) using combined goals and instructions.")

                except Exception as e:
                    self.log.error(f"Error sending multi-line prompt (goals/instructions) to tmux: {e}")

            except (IndexError, ValueError) as e:
                self.log.error(f"Error parsing plan section button ID '{button_id}': {e}")


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
                    from tm4aider import config as app_config_module # late import
                    app_config_module.update_session_active_plan_name(self.TMUX_SESSION_NAME, self.current_selected_plan_name)
                    self.log(f"Saved active plan '{self.current_selected_plan_name}' for session '{self.TMUX_SESSION_NAME}' to config.")
                else:
                    self.log.warning("TMUX_SESSION_NAME not set. Cannot save active plan to config.")

                tm4aider_dir_name = ".tm4aider"
                plans_subdir_name = "plans"
                plan_dir_path = Path(tm4aider_dir_name) / plans_subdir_name / self.current_selected_plan_name

                # Construct the expected markdown file name based on the plan directory name
                expected_markdown_filename = f"{self.current_selected_plan_name}.md"
                markdown_file_path = plan_dir_path / expected_markdown_filename

                if not markdown_file_path.is_file():
                    self.log.error(f"Markdown file not found: {markdown_file_path}")
                    self.current_plan_markdown_content = None # Clear content if file not found
                    self.current_selected_plan_name = None # Clear name
                    # Mount a message indicating the specific file was not found
                    await plan_sections_container.mount(Label(f"File '{expected_markdown_filename}' not found in '{self.current_selected_plan_name or 'selected plan'}'."))
                    return

                self.log(f"Loading plan from: {markdown_file_path}")

                try:
                    self.current_plan_markdown_content = markdown_file_path.read_text(encoding="utf-8") # Store content
                    section_titles = self._parse_markdown_sections(self.current_plan_markdown_content)

                    if not section_titles:
                        await plan_sections_container.mount(Label("No sections (## Title) found in plan."))
                        # Keep self.current_plan_markdown_content as it's valid, just no sections
                        return

                    for i, title in enumerate(section_titles):
                        section_label = Label(f"{title.strip()}")
                        ask_button = Button("ask", id=f"plan_sec_{i}_ask", classes="plan_action_button")
                        code_button = Button("code", id=f"plan_sec_{i}_code", classes="plan_action_button")
                        arch_button = Button("arch", id=f"plan_sec_{i}_arch", classes="plan_action_button")

                        # Define children when creating the Horizontal container
                        buttons_container = Horizontal(ask_button, code_button, arch_button)

                        # Define children when creating the Vertical container for the section item
                        section_item_container = Vertical(
                            section_label,
                            buttons_container,
                            classes="plan_section_item_container"
                        )

                        # Mount the fully constructed item container into the main plan sections container
                        await plan_sections_container.mount(section_item_container)

                    self.log(f"Displayed {len(section_titles)} sections for plan '{self.current_selected_plan_name}'.")

                except Exception as e:
                    self.log.error(f"Error loading or parsing plan file {markdown_file_path}: {e}")
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
                    from tm4aider import config as app_config_module # late import
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

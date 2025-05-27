import os
import sys
import yaml

CONFIG_FILENAME = ".lazyaider.conf.yml"

# Configuration Keys
KEY_SIDEPANE_PERCENT_WIDTH = "sidepane_percent_width"
KEY_MANAGED_SESSIONS = "managed_sessions"
KEY_THEME_NAME = "theme_name"
KEY_LLM_MODEL = "llm_model"
KEY_LLM_API_KEY = "llm_api_key"
KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH = "plan_generation_prompt_override_path" # Can be global or per-session
KEY_SESSION_ACTIVE_PLAN_NAME = "active_plan_name" # Stores the active plan directory name for a session
KEY_SESSION_PLAN_PROGRESS = "plan_progress" # Stores progress for each plan within a session
KEY_LAST_AIDER_STEP = "last_aider_step" # Stores the index of the last step sent to Aider for a plan
KEY_TEXT_EDITOR = "text_editor" # Command to launch the external text editor

DEFAULT_SIDEPANE_PERCENT_WIDTH = 20
DEFAULT_THEME_NAME = "light" # Textual's default theme
DEFAULT_LLM_MODEL = "gpt-3.5-turbo" # Default LLM model
DEFAULT_LLM_API_KEY = None # Default LLM API key
DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH = None # Default global path for prompt override file
DEFAULT_TEXT_EDITOR = "nano" # Default external text editor command

def find_config_file() -> str | None:
    """
    Searches for the config file in the current directory and then in the home directory.
    Returns the path to the config file if found, otherwise None.
    """
    # Check current directory
    current_dir_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if os.path.exists(current_dir_path):
        return current_dir_path

    # Check home directory
    home_dir_path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
    if os.path.exists(home_dir_path):
        return home_dir_path

    return None

def load_config() -> dict:
    """
    Loads configuration from the YAML file.
    Returns a dictionary with configuration values.
    """
    config_path = find_config_file()
    config = {}

    if config_path:
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load or parse config file {config_path}: {e}", file=sys.stderr)
            config = {} # Reset to empty dict on error

    # Apply defaults
    if not isinstance(config.get(KEY_SIDEPANE_PERCENT_WIDTH), int):
        if KEY_SIDEPANE_PERCENT_WIDTH in config: # Value exists but is not an int
             print(f"Warning: '{KEY_SIDEPANE_PERCENT_WIDTH}' in {config_path or 'config'} is not an integer. Using default value.", file=sys.stderr)
        config[KEY_SIDEPANE_PERCENT_WIDTH] = DEFAULT_SIDEPANE_PERCENT_WIDTH

    # Handle KEY_MANAGED_SESSIONS: ensure it's a dict, migrate from list if necessary
    managed_sessions_data = config.get(KEY_MANAGED_SESSIONS)
    if isinstance(managed_sessions_data, list):
        # Migrate from old list format
        print(f"Info: Migrating '{KEY_MANAGED_SESSIONS}' from list to dictionary format in configuration at {config_path or 'memory'}.", file=sys.stderr)
        config[KEY_MANAGED_SESSIONS] = {name: {} for name in managed_sessions_data}
    elif not isinstance(managed_sessions_data, dict):
        if KEY_MANAGED_SESSIONS in config: # Value exists but is not a dict (and wasn't a list)
            print(f"Warning: '{KEY_MANAGED_SESSIONS}' in {config_path or 'config'} is not a dictionary. Initializing as empty dictionary.", file=sys.stderr)
        config[KEY_MANAGED_SESSIONS] = {}
    # Ensure all session entries are dictionaries
    for session_name, session_settings in config[KEY_MANAGED_SESSIONS].items():
        if not isinstance(session_settings, dict):
            print(f"Warning: Settings for session '{session_name}' in '{KEY_MANAGED_SESSIONS}' is not a dictionary. Resetting to empty.", file=sys.stderr)
            config[KEY_MANAGED_SESSIONS][session_name] = {}
            session_settings = config[KEY_MANAGED_SESSIONS][session_name] # Re-assign after reset

        # Ensure plan_progress exists and is a dictionary
        plan_progress_dict = session_settings.get(KEY_SESSION_PLAN_PROGRESS)
        if not isinstance(plan_progress_dict, dict):
            if KEY_SESSION_PLAN_PROGRESS in session_settings:
                print(f"Warning: '{KEY_SESSION_PLAN_PROGRESS}' for session '{session_name}' is not a dictionary. Initializing.", file=sys.stderr)
            session_settings[KEY_SESSION_PLAN_PROGRESS] = {}
            plan_progress_dict = session_settings[KEY_SESSION_PLAN_PROGRESS]

        # Validate entries within plan_progress
        for plan_name, progress_data in list(plan_progress_dict.items()): # Use list for safe iteration if modifying
            if not isinstance(progress_data, dict):
                print(f"Warning: Progress data for plan '{plan_name}' in session '{session_name}' is not a dictionary. Removing.", file=sys.stderr)
                del plan_progress_dict[plan_name]
                continue
            
            last_step = progress_data.get(KEY_LAST_AIDER_STEP)
            if last_step is not None and not isinstance(last_step, int):
                print(f"Warning: '{KEY_LAST_AIDER_STEP}' for plan '{plan_name}' in session '{session_name}' is not an integer. Resetting.", file=sys.stderr)
                progress_data[KEY_LAST_AIDER_STEP] = None # Or del progress_data[KEY_LAST_AIDER_STEP]


    if not isinstance(config.get(KEY_THEME_NAME), str):
        if KEY_THEME_NAME in config: # Value exists but is not a str
            print(f"Warning: '{KEY_THEME_NAME}' in {config_path or 'config'} is not a string. Using default value.", file=sys.stderr)
        config[KEY_THEME_NAME] = DEFAULT_THEME_NAME

    if not isinstance(config.get(KEY_LLM_MODEL), str) or not config.get(KEY_LLM_MODEL, "").strip():
        if KEY_LLM_MODEL in config and config.get(KEY_LLM_MODEL) is not None : # Value exists but is not a non-empty str
            print(f"Warning: '{KEY_LLM_MODEL}' in {config_path or 'config'} is not a valid non-empty string. Using default value.", file=sys.stderr)
        config[KEY_LLM_MODEL] = DEFAULT_LLM_MODEL

    # Ensure llm_api_key is a string or None
    if KEY_LLM_API_KEY in config and not (isinstance(config.get(KEY_LLM_API_KEY), str) or config.get(KEY_LLM_API_KEY) is None):
        print(f"Warning: '{KEY_LLM_API_KEY}' in {config_path or 'config'} is not a string or null. Using default value.", file=sys.stderr)
        config[KEY_LLM_API_KEY] = DEFAULT_LLM_API_KEY
    elif KEY_LLM_API_KEY not in config:
        config[KEY_LLM_API_KEY] = DEFAULT_LLM_API_KEY

    # Ensure global plan_generation_prompt_override_path is a string or None and process it
    global_prompt_path = config.get(KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH)
    if global_prompt_path is not None and not isinstance(global_prompt_path, str):
        print(f"Warning: Global '{KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH}' in {config_path or 'config'} is not a string or null. Using default value (None).", file=sys.stderr)
        config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH
    elif KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH not in config: # Not present at all
        config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH

    if isinstance(config.get(KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH), str):
        path_val = config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH]
        expanded_path = os.path.expanduser(path_val)
        if not os.path.isabs(expanded_path) and path_val: # only if not empty string
            if config_path:
                config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = os.path.abspath(os.path.join(os.path.dirname(config_path), expanded_path))
            else:
                config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = os.path.abspath(expanded_path)
        else:
            config[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = expanded_path

    # Process session-specific plan_generation_prompt_override_path
    for session_name, session_settings in config.get(KEY_MANAGED_SESSIONS, {}).items():
        if not isinstance(session_settings, dict): # Should have been handled already, but defensive
            continue

        session_prompt_path = session_settings.get(KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH)
        if session_prompt_path is not None and not isinstance(session_prompt_path, str):
            print(f"Warning: Session '{session_name}' '{KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH}' in {config_path or 'config'} is not a string or null. Ignoring session override.", file=sys.stderr)
            if KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH in session_settings:
                 del session_settings[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] # Remove invalid entry
        elif isinstance(session_prompt_path, str):
            expanded_path = os.path.expanduser(session_prompt_path)
            if not os.path.isabs(expanded_path) and session_prompt_path: # only if not empty string
                if config_path:
                    session_settings[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = os.path.abspath(os.path.join(os.path.dirname(config_path), expanded_path))
                else:
                    session_settings[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = os.path.abspath(expanded_path)
            else:
                session_settings[KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH] = expanded_path
            # No default for session-specific, it's either there and valid, or not used.

    # Ensure text_editor is a string or None
    text_editor_val = config.get(KEY_TEXT_EDITOR)
    if text_editor_val is not None and not isinstance(text_editor_val, str):
        print(f"Warning: '{KEY_TEXT_EDITOR}' in {config_path or 'config'} is not a string. Using default (None).", file=sys.stderr)
        config[KEY_TEXT_EDITOR] = DEFAULT_TEXT_EDITOR
    elif text_editor_val == "": # Treat empty string as not configured (effectively None)
        config[KEY_TEXT_EDITOR] = None
    elif KEY_TEXT_EDITOR not in config: # Not present at all
        config[KEY_TEXT_EDITOR] = DEFAULT_TEXT_EDITOR

    return config

def save_config(current_config: dict) -> None:
    """
    Saves the given configuration dictionary to the config file.
    Uses the same search path as find_config_file, defaulting to home directory if not found.
    """
    config_path = find_config_file()
    if not config_path:
        # If no config file exists, create one in the home directory
        config_path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
        print(f"Creating new config file at: {config_path}", file=sys.stderr)

    try:
        with open(config_path, 'w') as f:
            yaml.dump(current_config, f, sort_keys=False)
    except Exception as e:
        print(f"Error: Could not save config file {config_path}: {e}", file=sys.stderr)

# Load configuration when the module is imported
settings = load_config()


def add_session_to_config(session_name: str) -> None:
    """Adds a session name to the managed_sessions dict in config and saves."""
    managed_sessions_dict = settings.setdefault(KEY_MANAGED_SESSIONS, {})
    if session_name not in managed_sessions_dict:
        managed_sessions_dict[session_name] = {} # Add session with empty settings
        save_config(settings)

def remove_session_from_config(session_name: str) -> None:
    """Removes a session name from the managed_sessions dict in config and saves."""
    managed_sessions_dict = settings.get(KEY_MANAGED_SESSIONS, {})
    if session_name in managed_sessions_dict:
        del managed_sessions_dict[session_name]
        save_config(settings)

def get_plan_prompt_override_path(session_name: str | None = None) -> str | None:
    """
    Retrieves the plan generation prompt override path.
    Checks session-specific config first, then global config.
    Paths are assumed to be processed (absolute, expanded) by load_config.
    """
    if session_name:
        session_config = settings.get(KEY_MANAGED_SESSIONS, {}).get(session_name)
        if session_config and isinstance(session_config, dict):
            # Path should already be processed by load_config if it exists
            session_prompt_path = session_config.get(KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH)
            if session_prompt_path is not None: # Can be empty string or a path
                return session_prompt_path

    # Fallback to global setting (also already processed by load_config)
    return settings.get(KEY_PLAN_GENERATION_PROMPT_OVERRIDE_PATH)

def update_theme_in_config(theme_name: str) -> None:
    """Updates the theme name in config and saves."""
    current_theme = settings.get(KEY_THEME_NAME)
    if current_theme != theme_name:
        settings[KEY_THEME_NAME] = theme_name
        save_config(settings)

def update_session_active_plan_name(session_name: str, plan_name: str | None) -> None:
    """Updates the active plan name for a specific session in config and saves."""
    if not session_name:
        print("Warning: Attempted to update active plan for an unspecified session name.", file=sys.stderr)
        return

    managed_sessions = settings.setdefault(KEY_MANAGED_SESSIONS, {})
    session_settings = managed_sessions.setdefault(session_name, {})

    current_plan_name = session_settings.get(KEY_SESSION_ACTIVE_PLAN_NAME)

    if current_plan_name != plan_name:
        if plan_name is None:
            if KEY_SESSION_ACTIVE_PLAN_NAME in session_settings:
                del session_settings[KEY_SESSION_ACTIVE_PLAN_NAME]
                save_config(settings)
        else:
            session_settings[KEY_SESSION_ACTIVE_PLAN_NAME] = plan_name
            save_config(settings)

def update_llm_model_in_config(model_name: str) -> None:
    """Updates the LLM model name in config and saves."""
    current_model = settings.get(KEY_LLM_MODEL)
    if current_model != model_name:
        settings[KEY_LLM_MODEL] = model_name
        save_config(settings)

def update_llm_api_key_in_config(api_key: str | None) -> None:
    """Updates the LLM API key in config and saves."""
    current_api_key = settings.get(KEY_LLM_API_KEY)
    if current_api_key != api_key:
        settings[KEY_LLM_API_KEY] = api_key
        save_config(settings)

def update_session_last_aider_step(session_name: str, plan_name: str, step_index: int | None) -> None:
    """Updates the last Aider step index for a specific plan within a session and saves."""
    if not session_name or not plan_name:
        print("Warning: Session name or plan name not provided for updating last Aider step.", file=sys.stderr)
        return

    managed_sessions = settings.setdefault(KEY_MANAGED_SESSIONS, {})
    session_settings = managed_sessions.setdefault(session_name, {})
    plan_progress_dict = session_settings.setdefault(KEY_SESSION_PLAN_PROGRESS, {})
    plan_specific_progress = plan_progress_dict.setdefault(plan_name, {})

    current_step = plan_specific_progress.get(KEY_LAST_AIDER_STEP)

    if current_step != step_index:
        if step_index is None:
            if KEY_LAST_AIDER_STEP in plan_specific_progress:
                del plan_specific_progress[KEY_LAST_AIDER_STEP]
        else:
            plan_specific_progress[KEY_LAST_AIDER_STEP] = step_index
        save_config(settings)

def get_session_last_aider_step(session_name: str, plan_name: str) -> int | None:
    """Retrieves the last Aider step index for a specific plan within a session."""
    if not session_name or not plan_name:
        return None
    
    try:
        step = settings[KEY_MANAGED_SESSIONS][session_name][KEY_SESSION_PLAN_PROGRESS][plan_name][KEY_LAST_AIDER_STEP]
        return int(step) if isinstance(step, int) else None
    except KeyError:
        return None

import os
import sys
import yaml

CONFIG_FILENAME = ".tm4aider.conf.yml"
DEFAULT_SIDEPANE_PERCENT_WIDTH = 20
DEFAULT_THEME_NAME = "light" # Textual's default theme
DEFAULT_LLM_MODEL = "gpt-3.5-turbo" # Default LLM model
DEFAULT_LLM_API_KEY = None # Default LLM API key
DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH = None # Default path for prompt override file

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
    if not isinstance(config.get("sidepane_percent_width"), int):
        if "sidepane_percent_width" in config: # Value exists but is not an int
             print(f"Warning: 'sidepane_percent_width' in {config_path or 'config'} is not an integer. Using default value.", file=sys.stderr)
        config["sidepane_percent_width"] = DEFAULT_SIDEPANE_PERCENT_WIDTH

    if not isinstance(config.get("managed_sessions"), list):
        if "managed_sessions" in config: # Value exists but is not a list
            print(f"Warning: 'managed_sessions' in {config_path or 'config'} is not a list. Initializing as empty list.", file=sys.stderr)
        config["managed_sessions"] = []

    if not isinstance(config.get("theme_name"), str):
        if "theme_name" in config: # Value exists but is not a str
            print(f"Warning: 'theme_name' in {config_path or 'config'} is not a string. Using default value.", file=sys.stderr)
        config["theme_name"] = DEFAULT_THEME_NAME
    
    if not isinstance(config.get("llm_model"), str) or not config.get("llm_model", "").strip():
        if "llm_model" in config and config.get("llm_model") is not None : # Value exists but is not a non-empty str
            print(f"Warning: 'llm_model' in {config_path or 'config'} is not a valid non-empty string. Using default value.", file=sys.stderr)
        config["llm_model"] = DEFAULT_LLM_MODEL

    # Ensure llm_api_key is a string or None
    if "llm_api_key" in config and not (isinstance(config.get("llm_api_key"), str) or config.get("llm_api_key") is None):
        print(f"Warning: 'llm_api_key' in {config_path or 'config'} is not a string or null. Using default value.", file=sys.stderr)
        config["llm_api_key"] = DEFAULT_LLM_API_KEY
    elif "llm_api_key" not in config:
        config["llm_api_key"] = DEFAULT_LLM_API_KEY

    # Ensure plan_generation_prompt_override_path is a string or None
    if "plan_generation_prompt_override_path" in config and \
       not (isinstance(config.get("plan_generation_prompt_override_path"), str) or \
            config.get("plan_generation_prompt_override_path") is None):
        print(f"Warning: 'plan_generation_prompt_override_path' in {config_path or 'config'} is not a string or null. Using default value.", file=sys.stderr)
        config["plan_generation_prompt_override_path"] = DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH
    elif "plan_generation_prompt_override_path" not in config:
        config["plan_generation_prompt_override_path"] = DEFAULT_PLAN_GENERATION_PROMPT_OVERRIDE_PATH
    
    # Ensure the path is absolute if provided, or None
    if isinstance(config["plan_generation_prompt_override_path"], str):
        # Expand ~ and make absolute. If path is invalid, it will be handled by the consuming code.
        expanded_path = os.path.expanduser(config["plan_generation_prompt_override_path"])
        if not os.path.isabs(expanded_path) and config["plan_generation_prompt_override_path"]: # only if not empty string
             # if not absolute, make it relative to the config file's directory if possible, else CWD
            if config_path:
                config["plan_generation_prompt_override_path"] = os.path.abspath(os.path.join(os.path.dirname(config_path), expanded_path))
            else: # if no config file, relative to CWD
                config["plan_generation_prompt_override_path"] = os.path.abspath(expanded_path)
        else: # it was already absolute or an empty string
            config["plan_generation_prompt_override_path"] = expanded_path


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
    """Adds a session name to the managed_sessions list in config and saves."""
    if session_name not in settings.get("managed_sessions", []):
        settings.setdefault("managed_sessions", []).append(session_name)
        save_config(settings)

def remove_session_from_config(session_name: str) -> None:
    """Removes a session name from the managed_sessions list in config and saves."""
    if session_name in settings.get("managed_sessions", []):
        settings["managed_sessions"].remove(session_name)
        save_config(settings)

def update_theme_in_config(theme_name: str) -> None:
    """Updates the theme name in config and saves."""
    current_theme = settings.get("theme_name")
    if current_theme != theme_name:
        settings["theme_name"] = theme_name
        save_config(settings)

def update_llm_model_in_config(model_name: str) -> None:
    """Updates the LLM model name in config and saves."""
    current_model = settings.get("llm_model")
    if current_model != model_name:
        settings["llm_model"] = model_name
        save_config(settings)

def update_llm_api_key_in_config(api_key: str | None) -> None:
    """Updates the LLM API key in config and saves."""
    current_api_key = settings.get("llm_api_key")
    if current_api_key != api_key:
        settings["llm_api_key"] = api_key
        save_config(settings)

import os
import sys
import yaml

CONFIG_FILENAME = ".tm4aider.conf.yml"
DEFAULT_SIDEPANE_PERCENT_WIDTH = 20
DEFAULT_THEME_NAME = "light" # Textual's default theme

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

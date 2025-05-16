import os
import sys
import yaml

CONFIG_FILENAME = ".tm4aider.conf.yml"
DEFAULT_SIDEPANE_PERCENT_WIDTH = 20

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
    
    return config

# Load configuration when the module is imported
settings = load_config()

import os
import sys
from pathlib import Path

def get_venv_activation_prefix() -> str:
    """
    Determines the shell command prefix to activate a virtual environment, if active.
    Checks for VIRTUAL_ENV environment variable first, then sys.prefix.
    Returns the command prefix (e.g., '. "/path/to/venv/bin/activate" && ') or an empty string.
    """
    venv_path_str = os.environ.get("VIRTUAL_ENV")
    activate_script_path_to_use = None
    # The following variables are for potential logging by the caller, not used in this function directly.
    # detection_method_message = "" 

    if venv_path_str:
        venv_path = Path(venv_path_str)
        script_path = venv_path / "bin" / "activate"
        if script_path.exists():
            activate_script_path_to_use = script_path
            # detection_method_message = f"Virtual environment detected via VIRTUAL_ENV: {venv_path_str}" # For caller to log
    
    if not activate_script_path_to_use and sys.prefix != sys.base_prefix:
        venv_path = Path(sys.prefix)
        script_path = venv_path / "bin" / "activate"
        if script_path.exists():
            activate_script_path_to_use = script_path
            # detection_method_message = f"Virtual environment detected via sys.prefix: {sys.prefix}" # For caller to log

    if activate_script_path_to_use:
        # Caller can log detection_method_message and the activate_script_path_to_use if desired.
        return f". \"{activate_script_path_to_use.resolve()}\" && "
    
    return ""

import subprocess

def get_aider_repo_map() -> str:
    """
    Runs 'aider --show-repo-map' and captures its output,
    returning only the content after the first empty line.
    An empty line is defined as a line containing only whitespace characters (or no characters)
    followed by a newline.

    If the command fails, it returns a string containing the error message.
    If the command succeeds but no empty line is found, or if there's no content 
    after the first empty line, it returns an empty string.
    """
    command = ["aider", "--show-repo-map"]
    try:
        # Set encoding to utf-8 to handle potential special characters in file paths
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False, # We will check returncode manually
            encoding='utf-8' 
        )

        if result.returncode != 0:
            error_message = f"Error running '{' '.join(command)}':\n"
            error_message += f"Return code: {result.returncode}\n"
            if result.stdout:
                error_message += f"Stdout:\n{result.stdout.strip()}\n"
            if result.stderr:
                error_message += f"Stderr:\n{result.stderr.strip()}\n"
            return error_message.strip()

        stdout_content = result.stdout
        
        lines = stdout_content.splitlines(True) # Keep newlines to preserve original structure
        current_char_offset = 0
        
        for line_with_newline in lines:
            # Content of the line, excluding its own trailing newline character(s)
            line_content_stripped_of_newline = line_with_newline.rstrip('\r\n')
            
            # Calculate the starting position of the *next* line's content
            offset_after_this_line = current_char_offset + len(line_with_newline)

            # Check if the current line (when stripped of its own newline and then whitespace) is empty
            if line_content_stripped_of_newline.strip() == "":
                # This is an empty line. We want the content that starts *after* this entire line.
                if offset_after_this_line >= len(stdout_content):
                    # The empty line was the last part of the output, or output ends with it.
                    # Thus, there is no content after it.
                    return "" 
                return stdout_content[offset_after_this_line:]
            
            current_char_offset = offset_after_this_line
            
        # No empty line was found in the output
        return ""

    except FileNotFoundError:
        return f"Error: '{command[0]}' command not found. Please ensure Aider is installed and in your PATH."
    except Exception as e:
        # Catch any other unexpected exceptions during subprocess execution.
        return f"An unexpected error occurred while running '{' '.join(command)}': {type(e).__name__} - {e}"

if __name__ == '__main__':
    # Example usage for testing
    print("Attempting to get Aider repo map...")
    repo_map_data = get_aider_repo_map()
    
    if repo_map_data.startswith("Error:") or repo_map_data.startswith("An unexpected error occurred:"):
        print("\n--- Error ---")
        print(repo_map_data)
    elif not repo_map_data:
        print("\n--- Repo Map (content after first empty line) ---")
        print("No empty line found in 'aider --show-repo-map' output, or no content after it.")
    else:
        print("\n--- Repo Map (content after first line) ---")
        print(repo_map_data)

    # Test case: Simulate aider not found (this requires 'aider' not to be 'non_existent_command')
    # To test this, you might temporarily rename the function or change the command
    # For example:
    # get_aider_repo_map_original = get_aider_repo_map
    # def get_aider_repo_map_test_notfound():
    #     global command # if command is module level, or pass it
    #     original_command = command
    #     command = ["non_existent_command_for_testing_aider_utils", "--show-repo-map"]
    #     try:
    #         return get_aider_repo_map_original() # This won't work directly as command is local
    #     finally:
    #         command = original_command 
    # print("\nTesting with a non-existent command (simulated):")
    # # This part is tricky to inject for a direct test in __main__ without modifying the function
    # # or making `command` a global or parameter.
    # # The current FileNotFoundError handling is standard.
    # print("Please test 'aider' not found manually if needed by ensuring 'aider' is not in PATH.")

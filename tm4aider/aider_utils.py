import subprocess

def get_aider_repo_map() -> str:
    """
    Runs 'aider --show-repo-map' and captures its output,
    returning only the content after the first newline.

    If the command fails, it returns a string containing the error message.
    If the command succeeds but there's no newline, or no content after 
    the first newline, it returns an empty string.
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
        first_newline_index = stdout_content.find('\n')

        if first_newline_index == -1:
            # No newline found, so there is no content "after" the first newline.
            return ""
        
        # Return the part of the string after the first newline character.
        # If the newline is the last character, this will correctly return an empty string.
        return stdout_content[first_newline_index + 1:]

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
        print("\n--- Repo Map (or part after first line) ---")
        print("No content found after the first line of 'aider --show-repo-map' output, or the output was empty after the first line.")
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

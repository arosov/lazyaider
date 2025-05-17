import litellm
import os
import sys
from . import config # Use relative import for config within the same package
from .prompt import PLAN_GENERATION_PROMPT_TEMPLATE as DEFAULT_PLAN_GENERATION_PROMPT_TEMPLATE # Import and alias

def generate_plan(feature_description: str, session_name: str | None = None) -> tuple[str, str, int | None] | str:
    """
    Generates a development plan in Markdown format using an LLM.
    Uses session-specific prompt override if available, else global, else default.
    The model is determined by the 'llm_model' setting in the configuration.

    Args:
        feature_description: The user's description of the feature to implement.

    Returns:
        On success, a tuple: (plan_content: str, model_name: str, total_tokens: int | None).
        On failure, an error message string.
    """
    # Ensure config is loaded. `config.settings` should be available.
    # If config.py hasn't set up `DEFAULT_LLM_MODEL` or if it's missing,
    # litellm might default or error. It's better to ensure a default here too.
    model_from_config = config.settings.get(config.KEY_LLM_MODEL)
    api_key_from_config = config.settings.get(config.KEY_LLM_API_KEY)

    if not model_from_config:
        # Fallback if 'llm_model' is not in config or is empty.
        # This default should ideally match or be consistent with config.py's DEFAULT_LLM_MODEL
        model = "gpt-3.5-turbo"
        print(f"Warning: 'llm_model' not found or empty in config. Using default: {model}", file=sys.stderr)
    else:
        model = model_from_config

    # Determine the API key to use
    api_key_to_use = api_key_from_config

    # Check for API keys if using common providers, as litellm might not give clear errors.
    # This is a helper and not exhaustive.
    # Priority: 1. Config file, 2. Environment variable
    if "gpt" in model:
        if not api_key_to_use and not os.getenv("OPENAI_API_KEY"):
            print("Warning: OpenAI API key not found in config ('llm_api_key') or OPENAI_API_KEY environment variable. LLM call to OpenAI model might fail.", file=sys.stderr)
        elif not api_key_to_use: # Use env var if config key is not set
            api_key_to_use = os.getenv("OPENAI_API_KEY")
    elif "claude" in model:
        if not api_key_to_use and not os.getenv("ANTHROPIC_API_KEY"):
            print("Warning: Anthropic API key not found in config ('llm_api_key') or ANTHROPIC_API_KEY environment variable. LLM call to Anthropic model might fail.", file=sys.stderr)
        elif not api_key_to_use: # Use env var if config key is not set
            api_key_to_use = os.getenv("ANTHROPIC_API_KEY")
    # Add more checks for other providers as needed, following the same pattern

    prompt_override_path = config.get_plan_prompt_override_path(session_name)
    actual_prompt_template = DEFAULT_PLAN_GENERATION_PROMPT_TEMPLATE
    using_custom_prompt = False
    if prompt_override_path:
        try:
            # Ensure path is not empty before trying to open
            if prompt_override_path.strip():
                with open(prompt_override_path, 'r', encoding='utf-8') as f:
                    actual_prompt_template = f.read()
                print(f"Using custom prompt template from: {prompt_override_path}", file=sys.stderr)
                using_custom_prompt = True
            else: # Path is an empty string, treat as no override
                print(f"Info: Plan generation prompt override path is empty. Using default template.", file=sys.stderr)

        except FileNotFoundError:
            print(f"Warning: Prompt template file not found at {prompt_override_path}. Using default template.", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not load prompt template from {prompt_override_path}: {e}. Using default template.", file=sys.stderr)
    
    try:
        prompt = actual_prompt_template.format(feature_description=feature_description)
    except KeyError as e:
        # This happens if the custom prompt doesn't have {feature_description}
        error_message = f"Error: The prompt template is missing the required placeholder {{feature_description}}. Offending key: {e}."
        if using_custom_prompt:
            error_message += f" Please check the custom prompt file: {prompt_override_path}"
        else:
            error_message += " This might be an issue with the default prompt template." # Should not happen with default
        print(error_message, file=sys.stderr)
        return f"# Error Generating Plan\n\n{error_message}"


    messages = [{"role": "user", "content": prompt}]

    try:
        print(f"Attempting to call LLM model: {model}...", file=sys.stderr)
        # Set a timeout for the API call (e.g., 120 seconds)
        response = litellm.completion(
            model=model,
            messages=messages,
            api_key=api_key_to_use, # Pass the API key to litellm
            timeout=120 # seconds
        )
        # Accessing content according to litellm's current typical response structure
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            plan_content = response.choices[0].message.content.strip()

            total_tokens: int | None = None
            if response.usage and hasattr(response.usage, 'total_tokens'):
                total_tokens = response.usage.total_tokens

            # Log to stderr for debugging/logging, UI will display it too
            token_msg = f"{total_tokens} tokens" if total_tokens is not None else "token usage N/A"
            print(f"LLM ({model}) response received. Usage: {token_msg}.", file=sys.stderr)

            return plan_content, model, total_tokens
        else:
            error_message = "Error: LLM response structure was unexpected or content was empty."
            print(error_message, file=sys.stderr)
            if response:
                print(f"Full response object: {response}", file=sys.stderr)
            return f"# Error Generating Plan\n\n{error_message}\n\nReview LLM provider logs and ensure the model is accessible and configured correctly."

    except litellm.exceptions.APIConnectionError as e:
        error_message = f"Error connecting to LLM API ({model}): {e}"
        print(error_message, file=sys.stderr)
        return f"# Error Generating Plan\n\n{error_message}\n\nPlease check your network connection and API key."
    except litellm.exceptions.Timeout as e:
        error_message = f"LLM API call timed out ({model}): {e}"
        print(error_message, file=sys.stderr)
        return f"# Error Generating Plan\n\n{error_message}\n\nThe model took too long to respond. You might try a different model or check the LLM provider status."
    except litellm.exceptions.APIError as e: # Catch more specific litellm API errors
        error_message = f"LLM API error ({model}): {e.status_code} - {e.message}"
        print(error_message, file=sys.stderr)
        return f"# Error Generating Plan\n\n{error_message}\n\nPlease check your API key, model name, and provider quotas."
    except Exception as e:
        # Catch-all for other unexpected errors during the litellm call
        error_message = f"An unexpected error occurred while calling LLM ({model}): {type(e).__name__} - {e}"
        print(error_message, file=sys.stderr)
        # Include traceback for unexpected errors for better debugging
        import traceback
        traceback.print_exc(file=sys.stderr)
        return f"# Error Generating Plan\n\n{error_message}"

if __name__ == '__main__':
    # This part is for testing the module directly.
    # It requires that the `tm4aider` package (and its config) is discoverable.
    # You might need to run this from the project root or adjust PYTHONPATH.
    # Example: python -m tm4aider.llm_planner

    print("Testing LLM Planner Module...")
    # Ensure API key is set for the default or configured model
    # For example, for OpenAI, set OPENAI_API_KEY.
    # The generate_plan function itself will print warnings if keys are missing for common models.

    # A default model for testing if config isn't fully set up or accessible here
    test_model_name = config.settings.get(config.KEY_LLM_MODEL) if 'config' in globals() and hasattr(config, 'settings') else "gpt-3.5-turbo"

    print(f"Using model: {test_model_name} (from config or default for test)")

    sample_feature = "Implement a basic CLI tool that takes a filename as input and counts the number of lines in that file. The tool should be robust and handle file not found errors."
    print(f"Generating plan for: \"{sample_feature}\"\n", file=sys.stderr)

    # Test with no session (uses global or default prompt)
    print("Testing with no session context (global/default prompt):")
    plan_data_global = generate_plan(sample_feature) # session_name is None by default

    print("\n--- Generated Plan (Global/Default Prompt) ---")
    if isinstance(plan_data_global, tuple):
        plan_content, _, _ = plan_data_global
        print(plan_content)
        if not plan_content.startswith("# Error Generating Plan"):
            try:
                with open("test_plan_global.md", "w", encoding="utf-8") as f:
                    f.write(plan_content)
                print("\nTest plan (global/default) saved to test_plan_global.md")
            except IOError as e:
                print(f"\nError saving test_plan_global.md: {e}", file=sys.stderr)
        else:
            print("\nPlan generation (global/default) failed. See error message above.", file=sys.stderr)

    else: # Error string
        print(plan_data_global)
        print("\nPlan generation (global/default) failed. See error message above.", file=sys.stderr)
    print("------------------------------------------")

    # Example of how to test with a session-specific prompt (requires config setup)
    # You would need to:
    # 1. Create/modify .tm4aider.conf.yml to have a session, e.g., "test-session"
    #    managed_sessions:
    #      test-session:
    #        plan_generation_prompt_override_path: /path/to/your/test_session_prompt.md
    # 2. Create /path/to/your/test_session_prompt.md with content like "Session plan for {feature_description}"
    # Then you could call:
    # print("\nTesting with 'test-session' context (session-specific prompt if configured):")
    # config.settings = config.load_config() # Reload config to pick up changes if made manually
    # plan_data_session = generate_plan(sample_feature, session_name="test-session")
    # print("\n--- Generated Plan (Session-Specific Prompt) ---")
    # if isinstance(plan_data_session, tuple):
    #     plan_content_session, _, _ = plan_data_session
    #     print(plan_content_session)
    # else:
    #     print(plan_data_session)
    # print("----------------------------------------------")

    # For the current test, we'll just print the global one.
    # The user needs to set up config for session-specific test.

    # Original print for the first result (plan_data_global)
    # print("\n--- Generated Plan ---")
    # print(plan_data_global[0] if isinstance(plan_data_global, tuple) else plan_data_global) # Print content or error
    print("----------------------")

    # Define 'plan' based on 'plan_data_global' for the following block
    if isinstance(plan_data_global, tuple):
        plan = plan_data_global[0]  # This is the plan content
    else:
        plan = plan_data_global  # This is the error string

    if not plan.startswith("# Error Generating Plan"):
        try:
            # Save to a test plan file in the current directory
            with open("test_plan.md", "w", encoding="utf-8") as f:
                f.write(plan)
            print("\nTest plan saved to test_plan.md")
        except IOError as e:
            print(f"\nError saving test_plan.md: {e}", file=sys.stderr)
    else:
        print("\nPlan generation failed. See error message above.", file=sys.stderr)

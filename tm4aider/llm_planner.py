import litellm
import os
import sys
from . import config # Use relative import for config within the same package
from .prompt import PLAN_GENERATION_PROMPT_TEMPLATE # Import the template

def generate_plan(feature_description: str) -> str:
    """
    Generates a development plan in Markdown format using an LLM.
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
    model_from_config = config.settings.get("llm_model")
    api_key_from_config = config.settings.get("llm_api_key")

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

    prompt = PLAN_GENERATION_PROMPT_TEMPLATE.format(feature_description=feature_description)
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
    test_model_name = config.settings.get("llm_model") if 'config' in globals() and hasattr(config, 'settings') else "gpt-3.5-turbo"

    print(f"Using model: {test_model_name} (from config or default for test)")

    sample_feature = "Implement a basic CLI tool that takes a filename as input and counts the number of lines in that file. The tool should be robust and handle file not found errors."
    print(f"Generating plan for: \"{sample_feature}\"\n", file=sys.stderr)

    plan = generate_plan(sample_feature)

    print("\n--- Generated Plan ---")
    print(plan)
    print("----------------------")

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

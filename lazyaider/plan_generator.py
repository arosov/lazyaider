import sys
import os
import re
import argparse # Added for CLI argument parsing
from .feature_input_app import FeatureInputApp # Changed to relative import
from .llm_planner import generate_plan # Changed to relative import

# Define global constants for directory names
lazyaider_DIR_NAME = ".lazyaider"
PLANS_SUBDIR_NAME = "plans"

def _extract_plan_title(markdown_content: str) -> str:
    """Extracts the plan title from the first H1 header in markdown."""
    lines = markdown_content.splitlines()
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("# "):
            title = stripped_line[2:].strip()
            if title: # Ensure title is not empty after stripping '# '
                return title
    return "untitled-plan"

def _sanitize_for_path(text: str) -> str:
    """Converts a string into a slug suitable for file/directory names."""
    text = text.lower()
    text = re.sub(r'\s+', '-', text)  # Replace whitespace with hyphens
    text = re.sub(r'[^a-z0-9\-]', '', text)  # Keep only lowercase letters, digits, and hyphens
    text = re.sub(r'-+', '-', text)  # Replace multiple hyphens with a single hyphen
    text = text.strip('-')  # Remove leading/trailing hyphens
    if not text:
        return "default-plan-title"
    return text

def _process_and_save_plan(plan_content: str, feature_description: str, session_name: str | None = None) -> None:
    """
    Processes the generated plan content, saves it along with the feature description.
    """
    # The plan_content might already start with "# Error" if LLM call failed
    if plan_content.startswith("# Error"):
        print("\nPlan generation resulted in an error (see details below or in plan files if saved):", file=sys.stderr)
    else:
        print("\n--- Plan Generation Successful ---", file=sys.stderr)

    print(plan_content) # Print the plan content (plan or error message)

    # Determine save path based on plan title (extracted from plan_content)
    plan_title = _extract_plan_title(plan_content)
    sanitized_title = _sanitize_for_path(plan_title)

    # TODO: Consider incorporating session_name into the path if provided and relevant for organization
    plan_dir = os.path.join(lazyaider_DIR_NAME, PLANS_SUBDIR_NAME, sanitized_title)

    try:
        os.makedirs(plan_dir, exist_ok=True)

        # Save the generated plan
        plan_filename = f"{sanitized_title}.md"
        full_plan_path = os.path.join(plan_dir, plan_filename)
        with open(full_plan_path, "w", encoding="utf-8") as f_plan:
            f_plan.write(plan_content)
        print(f"\nPlan saved to {full_plan_path}", file=sys.stderr)

        # Save the feature description
        feature_desc_filename = "feature_description.md"
        full_feature_desc_path = os.path.join(plan_dir, feature_desc_filename)
        with open(full_feature_desc_path, "w", encoding="utf-8") as f_desc:
            f_desc.write(feature_description)
        print(f"Feature description saved to {full_feature_desc_path}", file=sys.stderr)

    except IOError as e:
        print(f"\nError saving files to {plan_dir}: {e}", file=sys.stderr)
        # No sys.exit here, let the caller decide

def main(): # Wrap existing __main__ block in a main() function
    parser = argparse.ArgumentParser(description="Generate a development plan.")
    parser.add_argument(
        "--plan-file",
        type=str,
        help="Path to a text file containing the feature description for non-interactive plan generation."
    )
    parser.add_argument(
        "--dump-prompt",
        type=str,
        help="Path to a file where the LLM prompt should be saved. Only used in non-interactive mode."
    )
    parser.add_argument(
        "--use-repomix",
        action="store_true",
        help="Use 'repomix' to generate the repository map instead of Aider's internal method. Only used in non-interactive mode."
    )
    # TODO: Add --session-name argument if we want to specify session for non-interactive mode
    # For now, non-interactive mode will use global/default prompt settings from config.

    args = parser.parse_args()

    if args.plan_file:
        # Non-interactive mode
        try:
            with open(args.plan_file, "r", encoding="utf-8") as f:
                feature_description_cli = f.read()
            if not feature_description_cli.strip():
                print(f"Error: The plan file '{args.plan_file}' is empty.", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError:
            print(f"Error: The plan file '{args.plan_file}' was not found.", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error reading the plan file '{args.plan_file}': {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Generating plan non-interactively from: {args.plan_file}", file=sys.stderr)

        repomap_method_cli = "repomix" if args.use_repomix else "aider"
        if args.use_repomix:
            print("Using repomix for repository map generation.", file=sys.stderr)

        # In non-interactive mode, session_name is None, so global/default prompt is used.
        plan_result = generate_plan(
            feature_description_cli,
            session_name=None,
            repomap_method=repomap_method_cli, # Pass the chosen repomap method
            prompt_dump_file=args.dump_prompt
        )

        if isinstance(plan_result, tuple):
            plan_content_cli, model_name_cli, p_tokens_cli, c_tokens_cli, t_tokens_cli = plan_result
            token_msg = (
                f"Input: {p_tokens_cli if p_tokens_cli is not None else 'N/A'}, "
                f"Output: {c_tokens_cli if c_tokens_cli is not None else 'N/A'}, "
                f"Total: {t_tokens_cli if t_tokens_cli is not None else 'N/A'} tokens."
            )
            print(f"Plan generated using {model_name_cli}. Usage: {token_msg}", file=sys.stderr)
            _process_and_save_plan(plan_content_cli, feature_description_cli)
            sys.exit(0)
        else: # Error string
            print(plan_result, file=sys.stderr) # Print the error message from generate_plan
            # Attempt to save the error output as a plan as well
            _process_and_save_plan(plan_result, feature_description_cli)
            sys.exit(1) # Exit with error

    else:
        # Interactive mode
        feature_app = FeatureInputApp()
        app_exit_result = feature_app.run() # This blocks until FeatureInputApp exits

        if app_exit_result:
            plan_content_app, feature_description_app = app_exit_result # Unpack tuple
            # The FeatureInputApp already calls generate_plan, so plan_content_app is the direct result.
            # It also handles session_name internally for prompt selection.
            _process_and_save_plan(plan_content_app, feature_description_app)
            sys.exit(0) # Exit after handling the plan
        else:
            # If app_exit_result is None, it means the user cancelled or discarded the plan.
            print("Plan generation cancelled or discarded by the user. Exiting.", file=sys.stderr)
            sys.exit(0) # Exit even if plan generation was cancelled

if __name__ == "__main__":
    main()

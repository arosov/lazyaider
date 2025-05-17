import sys
import os
import re
from tm4aider.feature_input_app import FeatureInputApp

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

if __name__ == "__main__":
    feature_app = FeatureInputApp()
    plan_markdown = feature_app.run() # This blocks until FeatureInputApp exits

    if plan_markdown:
        # The plan_markdown might already start with "# Error" if LLM call failed inside app
        if plan_markdown.startswith("# Error"):
            print("\nPlan generation resulted in an error (see details below or in plan.md if saved):", file=sys.stderr)
        else:
            print("\n--- Plan Generation Successful ---", file=sys.stderr)

        print(plan_markdown) # Print the returned content (plan or error message)

        # Determine save path based on plan title
        plan_title = _extract_plan_title(plan_markdown)
        sanitized_title = _sanitize_for_path(plan_title)

        plan_dir = os.path.join(".tm4aider", "plans", sanitized_title)
        plan_filename = f"{sanitized_title}.md"
        full_plan_path = os.path.join(plan_dir, plan_filename)

        try:
            os.makedirs(plan_dir, exist_ok=True)
            with open(full_plan_path, "w", encoding="utf-8") as f:
                f.write(plan_markdown)
            print(f"\nOutput saved to {full_plan_path}", file=sys.stderr)
        except IOError as e:
            print(f"\nError saving plan to {full_plan_path}: {e}", file=sys.stderr)
        sys.exit(0) # Exit after handling the plan
    else:
        # If plan_markdown is None, it means the user cancelled or discarded the plan.
        print("Plan generation cancelled or discarded by the user. Exiting.", file=sys.stderr)
        sys.exit(0) # Exit even if plan generation was cancelled

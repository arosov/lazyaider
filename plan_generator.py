import sys
from tm4aider.feature_input_app import FeatureInputApp

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

        try:
            with open("plan.md", "w", encoding="utf-8") as f:
                f.write(plan_markdown)
            print("\nOutput saved to plan.md", file=sys.stderr)
        except IOError as e:
            print(f"\nError saving plan.md: {e}", file=sys.stderr)
        sys.exit(0) # Exit after handling the plan
    else:
        # If plan_markdown is None, it means the user cancelled or discarded the plan.
        print("Plan generation cancelled or discarded by the user. Exiting.", file=sys.stderr)
        sys.exit(0) # Exit even if plan generation was cancelled

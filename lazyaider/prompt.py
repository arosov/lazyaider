# The core prompt for generating the plan
PLAN_GENERATION_PROMPT_TEMPLATE = """
You are an expert software development assistant. Your task is to take a user's feature description
and break it down into a detailed, step-by-step plan. This plan will be used with a coding assistant
like Aider. Each step in the plan should be actionable and largely independent. It is not necessary to
include code in the instrutions.

**Important Guidelines for each step:**
- **Independence:** Each step should be as self-contained as possible. Assume Aider's context is reset (e.g., with `/clear`) before each step, and only the specified files are added for that step.
- **Clarity:** Instructions must be unambiguous.
- **Aider-Friendly:** Phrase instructions as if you are talking to Aider.
- **File Specificity:** Be accurate about filenames and paths. Account for files created in previous steps.

The output MUST be a Markdown document with the following structure:

# [Short feature title from user description]


## 1: [Descriptive Title for Step 1]

- **Files to add to Aider:** List the specific file paths that should be added to Aider for this step (e.g., `/add path/to/file.py new_file.py`). Use a Markdown bullet list.

- **Goal:** Briefly state the objective of this step.

- **Instructions:** Provide clear, concise instructions for the LLM coding assistant (Aider) to implement this step. Be specific about the changes, functions, classes, or logic to be added or modified.

## 2: [Descriptive Title for Step 2]

- **Files to add to Aider:** ...

- **Goal:** ...
- **Instructions:** ...

... (Repeat for as many steps as necessary) ...

User's Repository map:
---
{repository_map}
---

User's Feature Description:
---
{feature_description}
---

Now, generate the plan in Markdown format.
"""

import argparse
import sys
from pathlib import Path
import re

# Add the project root to sys.path to allow for absolute imports.
# This assumes section_editor.py is in tm4aider/ and the project root is its parent.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tm4aider.feature_input_app import FeatureInputApp

# Config is loaded when tm4aider.config is imported (e.g., by FeatureInputApp or other modules).
# This ensures FeatureInputApp can access theme settings.

def extract_section_from_markdown(markdown_content: str, section_index: int) -> tuple[str | None, int, int]:
    """
    Extracts a specific section from markdown content, including its header.
    A section is defined by a "## Title" header.
    Returns the section text (including the header line and trailing newline if present),
    start position (inclusive), and end position (exclusive) in the original content.
    """
    headers = list(re.finditer(r"^## .*", markdown_content, re.MULTILINE))

    if not 0 <= section_index < len(headers):
        return None, -1, -1

    section_header_match = headers[section_index]
    content_start_pos = section_header_match.start() # Start of the "## Title" line

    if section_index + 1 < len(headers):
        next_header_match = headers[section_index + 1]
        content_end_pos = next_header_match.start() # End is start of next "## Title" line
    else:
        content_end_pos = len(markdown_content) # End is EOF

    section_text = markdown_content[content_start_pos:content_end_pos]
    return section_text, content_start_pos, content_end_pos

def main():
    parser = argparse.ArgumentParser(description="Edit a specific section of a markdown plan file.")
    parser.add_argument("--file-path", required=True, type=str, help="Full path to the 'current-<plan_name>.md' file.")
    parser.add_argument("--section-index", required=True, type=int, help="0-based index of the section to edit.")

    args = parser.parse_args()

    markdown_file_path = Path(args.file_path)
    section_idx = args.section_index

    if not markdown_file_path.is_file():
        print(f"Error: File not found: {markdown_file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        original_content = markdown_file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file {markdown_file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    section_text, start_pos, end_pos = extract_section_from_markdown(original_content, section_idx)

    if section_text is None:
        print(f"Error: Section index {section_idx} not found in {markdown_file_path}.", file=sys.stderr)
        sys.exit(1)

    plan_name_for_title = markdown_file_path.stem
    if plan_name_for_title.startswith("current-"):
        plan_name_for_title = plan_name_for_title[len("current-"):]

    app = FeatureInputApp(
        mode="edit_section",
        initial_text=section_text, # Pass the full section text including header
        window_title=f"Edit Section {section_idx + 1} of '{plan_name_for_title}'"
    )
    edited_text_result = app.run() # Returns edited string or None

    if edited_text_result is not None:
        # The edited_text_result is the new full content for this section.
        # We need to ensure it fits well when reinserted.
        # Markdown sections are typically separated by newlines.
        # The user's exact input from the editor will be used.
        # The previous normalization logic for trailing newlines has been removed
        # to ensure that the content saved is exactly what was in the editor.
        # This gives the user full control but also responsibility for maintaining
        # correct section separation if they edit trailing newlines.

        processed_edited_text = edited_text_result
        
        # If the new text IS empty, but the original section was not the very end of the file,
        # we might want to ensure there's at least one newline to separate from subsequent content,
        # or to remove multiple newlines if the original section had them.
        # For simplicity, if new text is empty, we insert it as is. If it causes syntax issues,
        # the user can re-edit. A common case: deleting a section.
        # If processed_edited_text is now empty, it will effectively delete the section.
        # If it was followed by another section, the `original_content[end_pos:]` will handle that.

        new_content = original_content[:start_pos] + processed_edited_text + original_content[end_pos:]
        
        try:
            markdown_file_path.write_text(new_content, encoding="utf-8")
            # Output to stdout can be captured by tmux if needed (e.g., for status messages)
            print(f"Section {section_idx + 1} saved to {markdown_file_path.name}", file=sys.stdout)
        except Exception as e:
            print(f"Error writing updated content to {markdown_file_path}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Edit cancelled for section {section_idx + 1} of {markdown_file_path.name}.", file=sys.stdout)

if __name__ == "__main__":
    # This allows running `python -m tm4aider.section_editor ...`
    main()

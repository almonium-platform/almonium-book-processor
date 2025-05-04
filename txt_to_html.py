#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys

# --- Configuration ---
INPUT_TXT_FILE = 'data/input.txt'
OUTPUT_HTML_FILE = 'data/output.html'

# !!! EDIT THESE CONSTANTS FOR EACH BOOK !!!
AUTHOR = "Erich Maria Remarque"  # Example
TITLE = "IM WESTEN NICHTS NEUES"  # Example


# !!! END OF EDITABLE CONSTANTS !!!


# --- Main Function ---
def convert_txt_to_html(input_path, output_path):
    """
    Reads a plain text file, converts lines to <p> tags,
    detects chapter markers (e.g., "12."), converts them to
    <h2> tags with IDs, wraps chapters in <div class="chapter">,
    prepends a title/author header, appends 'THE END',
    skips "***" lines, and wraps the whole output in <div class="book">.
    """
    print(f"--- Starting TXT to HTML Conversion ---")
    print(f"Input TXT:  '{input_path}'")
    print(f"Output HTML: '{output_path}'")

    try:
        with open(input_path, 'r', encoding='utf-8') as f_in:
            lines = f_in.readlines()
        print(f"Successfully read input file.")
    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{input_path}': {e}")
        sys.exit(1)

    all_html_fragments = []  # Will store strings like "<p>...</p>" or "<h2>..."
    chapter_start_indices = {}  # Will store {chapter_num: index_in_fragments}

    # --- First Pass: Convert lines to HTML fragments and find chapter starts ---
    print("Step 1: Processing lines and identifying chapters...")
    current_chapter_num = 0  # Use 0 for potential preface content
    processed_lines = 0
    chapter_markers_found = 0

    for line in lines:
        stripped_line = line.strip()

        if not stripped_line:
            continue  # Skip empty lines

        # Check for chapter marker (digits followed by dot)
        chapter_match = re.match(r"^\s*(\d+)\.\s*$", stripped_line)
        # Check for "***" separator
        separator_match = re.match(r"^\s*\*+\s*\*+\s*\*+\s*$", stripped_line)

        if chapter_match:
            chapter_number_text = chapter_match.group(1)
            current_chapter_num += 1
            chapter_id = f"chap{current_chapter_num}"
            chapter_start_indices[current_chapter_num] = len(all_html_fragments)
            h2_tag_str = f'<h2 id="{chapter_id}">{stripped_line}</h2>'
            all_html_fragments.append(h2_tag_str)
            chapter_markers_found += 1
        elif separator_match:
            # Skip "***" lines
            pass
        else:
            # Regular line, convert to <p>
            p_tag_str = f'<p>{stripped_line}</p>'
            all_html_fragments.append(p_tag_str)

        processed_lines += 1

    print(f"Processed {processed_lines} non-empty lines.")
    print(f"Found {chapter_markers_found} chapter markers.")

    # --- Second Pass: Group fragments into chapter divs ---
    print("Step 2: Grouping content into chapter divs...")
    final_chapter_divs = []
    last_fragment_index = len(all_html_fragments)

    # Handle content *before* the first chapter (Preface/Intro)
    first_chapter_index = chapter_start_indices.get(1, last_fragment_index)
    preface_fragments = all_html_fragments[0:first_chapter_index]
    if preface_fragments:
        preface_content = "\n".join(preface_fragments)
        preface_div_str = f'<div class="chapter" id="chap0">\n{preface_content}\n</div>'
        final_chapter_divs.append(preface_div_str)
        print("  Created preface chapter div (chap0).")

    # Handle actual numbered chapters
    sorted_chapter_nums = sorted(chapter_start_indices.keys())
    for i, chap_num in enumerate(sorted_chapter_nums):
        start_index = chapter_start_indices[chap_num]
        if i + 1 < len(sorted_chapter_nums):
            next_chap_num = sorted_chapter_nums[i + 1]
            end_index = chapter_start_indices[next_chap_num]
        else:
            end_index = last_fragment_index

        chapter_fragments = all_html_fragments[start_index:end_index]
        if chapter_fragments:
            chapter_content = "\n".join(chapter_fragments)
            chapter_div_str = f'<div class="chapter">\n{chapter_content}\n</div>'
            final_chapter_divs.append(chapter_div_str)

    print(f"Created {len(final_chapter_divs)} total chapter divs.")

    # --- Final Assembly ---
    print("Step 3: Assembling final HTML with header and footer...")

    # Create Header String
    header_html = ""
    if AUTHOR and TITLE:
        header_html = f"""<div class="header">
<h1>{TITLE}</h1>
<h3>By {AUTHOR}</h3>
</div>"""
        print(f"  Generated header for '{TITLE}' by '{AUTHOR}'.")
    else:
        print("  Skipping header generation: AUTHOR or TITLE constant is empty.")

    # Create "THE END" String
    the_end_html = """<div class="the-end">
<h3>THE END</h3>
</div>"""
    print("  Generated 'THE END' block.")

    # Join all completed chapter divs
    all_chapters_html = "\n\n".join(final_chapter_divs)  # Add extra newline for readability

    # Combine header, chapters, and the end block
    combined_content = f"{header_html}\n\n{all_chapters_html}\n\n{the_end_html}"

    # Wrap everything in the final book div
    final_output_html = f'<div class="book">\n{combined_content.strip()}\n</div>'  # Strip intermediate whitespace before final wrap

    # --- Write Output File ---
    print(f"Step 4: Writing final HTML to '{output_path}'...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f_out:
            f_out.write(final_output_html)
        print(f"Successfully wrote output HTML file.")
    except Exception as e:
        print(f"Error writing file '{output_path}': {e}")
        sys.exit(1)


# --- Main Execution Block ---
if __name__ == "__main__":
    convert_txt_to_html(INPUT_TXT_FILE, OUTPUT_HTML_FILE)
    print("--- Script Complete ---")

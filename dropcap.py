#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys

from bs4 import BeautifulSoup, NavigableString

# --- Configuration ---
INPUT_HTML_FILE = 'data/input.html'
OUTPUT_HTML_FILE = 'data/output.html'
APPLY_DROPCAPS = True  # Set to True to enable drop caps, False to disable


def add_dropcaps(input_path, output_path):
    """
    Reads a pre-formatted HTML file (with class="book", class="chapter", etc.)
    and adds the 'pfirst' class and <span class="dropcap"> to the first
    paragraph of each chapter, if enabled.
    """
    print(f"--- Applying Drop Caps ---")
    print(f"Input HTML:  '{input_path}'")
    print(f"Output HTML: '{output_path}'")
    print(f"Apply Drop Caps: {APPLY_DROPCAPS}")

    if not APPLY_DROPCAPS:
        print("Drop cap application is disabled. Copying input to output.")
        try:
            with open(input_path, 'r', encoding='utf-8') as f_in, \
                    open(output_path, 'w', encoding='utf-8') as f_out:
                f_out.write(f_in.read())
            print(f"Successfully copied input to '{output_path}'")
        except FileNotFoundError:
            print(f"Error: Input file '{input_path}' not found.")
            sys.exit(1)
        except Exception as e:
            print(f"Error during file copy: {e}")
            sys.exit(1)
        return  # Exit the function

    # --- Read Input File ---
    try:
        with open(input_path, 'r', encoding='utf-8') as f_in:
            html_content = f_in.read()
        print(f"Successfully read input file.")
    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{input_path}': {e}")
        sys.exit(1)

    # --- Parse HTML ---
    print("Parsing HTML...")
    soup = BeautifulSoup(html_content, 'html.parser')

    # --- Apply Drop Caps Logic ---
    print("Applying drop caps logic...")
    dropcaps_applied = 0
    # Find all chapter divs
    all_chapter_divs = soup.find_all('div', class_='chapter')

    for chapter_div in all_chapter_divs:
        # Find the first H2 within this chapter div
        h2 = chapter_div.find('h2')
        if not h2: continue  # Skip if no H2 found (e.g., maybe preface div without H2)

        # Find the first 'p' tag that is a sibling following the H2 *within the chapter div*
        first_p = h2.find_next_sibling('p')

        if first_p:
            # Add 'pfirst' class if it doesn't exist
            current_classes = first_p.get('class', [])
            if 'pfirst' not in current_classes:
                current_classes.append('pfirst')
                first_p['class'] = current_classes

            # Find the first actual text content node within the paragraph
            first_text_node = first_p.find(string=lambda t: isinstance(t, NavigableString) and t.strip())

            if first_text_node:
                text = first_text_node.string
                # Regex to capture optional leading whitespace/quote and the first letter
                # Includes common European accented chars
                match = re.match(r'^(\s*["“”‘’]?\s*[A-Za-zÀ-ÖØ-öø-ÿ])(.*)', text, re.DOTALL)

                if match:
                    drop_cap_text = match.group(1).strip()  # The char(s) for the drop cap
                    remaining_text = match.group(2)  # The rest of the text node

                    if drop_cap_text:  # Ensure we captured something
                        # Create the new span
                        dropcap_span = soup.new_tag("span")
                        dropcap_span['class'] = 'dropcap'
                        dropcap_span.string = drop_cap_text

                        # Replace the original text node with the span
                        first_text_node.replace_with(dropcap_span)

                        # Insert the remaining text *after* the new span, if any
                        if remaining_text:
                            dropcap_span.insert_after(NavigableString(remaining_text))

                        dropcaps_applied += 1

    print(f"Applied drop caps to {dropcaps_applied} paragraphs.")

    # --- Generate Output HTML ---
    # Use str(soup) to avoid prettify adding extra whitespace
    final_output_html = str(soup)

    # --- Write Output File ---
    print(f"Writing final HTML to '{output_path}'...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f_out:
            f_out.write(final_output_html)
        print(f"Successfully wrote output HTML file.")
    except Exception as e:
        print(f"Error writing file '{output_path}': {e}")
        sys.exit(1)


# --- Main Execution Block ---
if __name__ == "__main__":
    add_dropcaps(INPUT_HTML_FILE, OUTPUT_HTML_FILE)
    print("--- Script Complete ---")

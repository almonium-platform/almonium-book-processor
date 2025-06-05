#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

# --- Configuration ---
INPUT_HTML_FILE = 'data/input.html'
OUTPUT_TXT_FILE = 'data/output.txt'


def normalize_whitespace(text):
    """
    Collapse all inner whitespace into single spaces and strip leading/trailing whitespace.
    """
    return re.sub(r'\s+', ' ', text).strip()


def html_to_text(input_path, output_path):
    print(f"--- Starting HTML to TXT Conversion ---")
    print(f"Input HTML:  '{input_path}'")
    print(f"Output TXT: '{output_path}'")

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

    print("Parsing HTML...")
    soup = BeautifulSoup(html_content, 'html.parser')

    print("Processing dropcaps to merge with following text...")
    # Iterate over a list copy because we are modifying the soup
    for dropcap_span in list(soup.select('span.dropcap')):
        dc_text = dropcap_span.get_text()  # Get text, might be "T", "L.", etc.

        # Important: strip the dropcap text itself in case it has spaces,
        # but only if it's not *just* a period or similar punctuation.
        # A more robust way is to ensure it's actual alphanumeric content.
        # For now, simple strip for typical letter dropcaps.
        processed_dc_text = dc_text.strip()

        if not processed_dc_text:  # Empty or whitespace-only dropcap
            dropcap_span.decompose()
            continue

        merged_successfully = False
        # We need to iterate through siblings, potentially modifying them or the list of siblings
        current_sibling = dropcap_span.next_sibling

        while current_sibling:
            next_sibling_for_iteration = current_sibling.next_sibling  # Get next before potential modification

            if isinstance(current_sibling, NavigableString):
                if current_sibling.string.strip():  # It's a non-whitespace text node
                    # Merge dc_text with the lstripped version of this text node
                    current_sibling.string.replace_with(processed_dc_text + current_sibling.string.lstrip())
                    dropcap_span.decompose()  # Remove original dropcap span
                    merged_successfully = True
                    break  # Merged, stop processing siblings for this dropcap
                else:
                    # It's a whitespace-only text node, remove it and continue
                    current_sibling.decompose()
                    # current_sibling will be advanced by the loop to next_sibling_for_iteration
            elif isinstance(current_sibling, Tag):
                # Try to find the first piece of actual text within this tag
                first_text_in_tag = current_sibling.find(string=True)
                if first_text_in_tag and first_text_in_tag.string.strip():
                    # Merge with the lstripped version of this first text
                    first_text_in_tag.string.replace_with(processed_dc_text + first_text_in_tag.string.lstrip())
                    dropcap_span.decompose()  # Remove original dropcap span
                    merged_successfully = True
                    break  # Merged, stop processing siblings for this dropcap
                else:
                    # This tag is empty, or contains only whitespace, or is not text-based (e.g. <br>, <img>)
                    # This tag acts as a separator. Stop trying to merge past it.
                    # The dropcap will be unwrapped by the fallback.
                    break  # Stop processing siblings, will lead to unwrap

            current_sibling = next_sibling_for_iteration

        if not merged_successfully:
            # Fallback: If no merge happened (e.g., dropcap at end of <p>, or followed by non-text tag)
            dropcap_span.unwrap()

    print("Removing 'THE END' block...")
    the_end_div = soup.select_one('div.the-end')
    if the_end_div:
        the_end_div.decompose()

    # The <i> tag handling you mentioned was already correct in your original script's
    # text extraction logic using `elem.stripped_strings`.
    # We don't need a special pre-processing for <i> if `stripped_strings` is used.

    print("Extracting and normalizing text from paragraphs, headings, and list items...")
    paragraphs = []
    main_text_elements = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
    for elem in soup.find_all(main_text_elements):
        # ' '.join(elem.stripped_strings) is the key:
        # - stripped_strings gets all text pieces, individually stripped.
        # - ' '.join puts a single space between these pieces.
        # This correctly handles spaces around <i> tags and now also merged dropcaps.
        text_segments = elem.stripped_strings
        joined_text = ' '.join(text_segments)

        normalized = normalize_whitespace(joined_text)  # Final cleanup

        if normalized:
            paragraphs.append(normalized)

    cleaned_text = '\n'.join(paragraphs)

    print(f"Writing plain text to '{output_path}'...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f_out:
            f_out.write(cleaned_text)
        print(f"Successfully wrote plain text output file.")
    except Exception as e:
        print(f"Error writing file '{output_path}': {e}")
        sys.exit(1)


if __name__ == "__main__":
    html_to_text(INPUT_HTML_FILE, OUTPUT_TXT_FILE)
    print("--- Script Complete ---")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys

from bs4 import BeautifulSoup

# --- Configuration ---
INPUT_HTML_FILE = 'data/input.html'  # Input HTML file path
OUTPUT_TXT_FILE = 'data/output.txt'  # Output plain text file path


def html_to_text(input_path, output_path):
    """
    Reads an HTML file, extracts all text content removing tags,
    cleans up excessive whitespace, and writes to a plain text file.
    """
    print(f"--- Starting HTML to TXT Conversion ---")
    print(f"Input HTML:  '{input_path}'")
    print(f"Output TXT: '{output_path}'")

    # --- Read Input HTML File ---
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

    # --- Extract Text ---
    # soup.get_text() extracts all text nodes and concatenates them
    # separator=" " can optionally add spaces between text blocks from different tags
    # strip=True removes leading/trailing whitespace from individual text nodes before joining
    print("Extracting text content...")
    raw_text = soup.get_text(separator='\n',
                             strip=True)  # Using newline separator often gives better results than default

    # --- Clean Whitespace ---
    # Remove excessive blank lines created during text extraction
    print("Cleaning up whitespace...")
    # Replace sequences of 2 or more newlines (with optional space between) with a single newline
    cleaned_text = re.sub(r'\n\s*\n+', '\n', raw_text)
    # Remove leading/trailing whitespace from the whole result
    cleaned_text = cleaned_text.strip()

    # --- Write Output TXT File ---
    print(f"Writing plain text to '{output_path}'...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f_out:
            f_out.write(cleaned_text)
        print(f"Successfully wrote plain text output file.")
    except Exception as e:
        print(f"Error writing file '{output_path}': {e}")
        sys.exit(1)


# --- Main Execution Block ---
if __name__ == "__main__":
    html_to_text(INPUT_HTML_FILE, OUTPUT_TXT_FILE)
    print("--- Script Complete ---")

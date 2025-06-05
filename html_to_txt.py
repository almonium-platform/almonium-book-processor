#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
from bs4 import BeautifulSoup

# --- Configuration ---
INPUT_HTML_FILE = 'data/input.html'
OUTPUT_TXT_FILE = 'data/output.txt'


def normalize_whitespace(text):
    """
    Collapse all inner whitespace into single spaces.
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

    print("Unwrapping dropcaps...")
    for dropcap in soup.select('span.dropcap'):
        dropcap.unwrap()

    print("Removing 'THE END' block...")
    the_end_div = soup.select_one('div.the-end')
    if the_end_div:
        the_end_div.decompose()

    print("Extracting and normalizing text...")
    paragraphs = []
    for elem in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
        text = elem.get_text(separator='', strip=True)
        normalized = normalize_whitespace(text)
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

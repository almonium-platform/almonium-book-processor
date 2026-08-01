#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from bs4 import BeautifulSoup

# --- Configuration: Mapping old classes to new lang codes ---
LANG_MAP = {
    'eng': 'en',
    'ukr': 'uk',
    # 'fre': 'fr', # Example: add more mappings here
    # 'ger': 'de', # Example: add more mappings here
}


def transform_html(input_path: str, output_path: str, remove_seg_ids: bool):
    """
    Reads an HTML file with hardcoded language classes (.eng, .ukr) and
    transforms it into a semantic, future-proof format using a generic
    .segment class and standard 'lang' attributes.
    """
    print("--- Starting HTML Transformation ---")
    print(f"Input file: '{input_path}'")
    print(f"Output file: '{output_path}'")
    print(f"Remove data-seg-id attributes: {remove_seg_ids}")

    try:
        with open(input_path, 'r', encoding='utf-8') as f_in:
            html_content = f_in.read()
    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(html_content, 'lxml')
    spans_transformed = 0

    # --- Step 1: Find and transform all language-specific spans ---
    for old_class, lang_code in LANG_MAP.items():
        spans_to_transform = soup.find_all('span', class_=old_class)

        for span in spans_to_transform:
            span['class'] = ['segment']
            span['lang'] = lang_code

            # *** THIS IS THE CORRECTED PART ***
            # Standardize the boolean 'hidden' attribute.
            # If the attribute exists (in any form), this ensures the HTML5
            # formatter will output just the word 'hidden'.
            if span.has_attr('hidden'):
                span['hidden'] = ""  # Set to an empty string

            spans_transformed += 1

    print(f"Transformed {spans_transformed} language-specific spans.")

    # --- Step 2: Optionally remove data-seg-id attributes ---
    if remove_seg_ids:
        seg_pairs = soup.find_all('span', class_='seg-pair')
        for pair in seg_pairs:
            if pair.has_attr('data-seg-id'):
                del pair['data-seg-id']
        print(f"Removed 'data-seg-id' from {len(seg_pairs)} seg-pair elements.")
    else:
        print("Kept 'data-seg-id' attributes.")

    # --- Step 3: Write the transformed HTML to the output file ---
    try:
        with open(output_path, 'w', encoding='utf-8') as f_out:
            # Use the 'html5' formatter to correctly handle boolean attributes
            f_out.write(soup.body.decode_contents(formatter="html5"))
        print(f"Successfully wrote transformed HTML to '{output_path}'.")
    except Exception as e:
        print(f"Error writing to file '{output_path}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transform legacy parallel book HTML to a modern, semantic format."
    )
    parser.add_argument(
        '-i', '--input',
        default='data/input.html',
        help="Path to the input HTML file (default: data/input.html)"
    )
    parser.add_argument(
        '-o', '--output',
        default='data/output.html',
        help="Path to the output HTML file (default: data/output.html)"
    )
    parser.add_argument(
        '--remove-seg-ids',
        action='store_true',
        help="Include this flag to remove all 'data-seg-id' attributes from seg-pairs."
    )

    args = parser.parse_args()
    transform_html(args.input, args.output, args.remove_seg_ids)
    print("--- Process Complete ---")
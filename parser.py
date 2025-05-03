#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re  # For cleaning up blank lines
import sys

# --- Imports ---
from bs4 import BeautifulSoup, NavigableString, Comment

# --- Configuration ---
INPUT_HTML_PATH = 'data/input.html'  # Input file name
OUTPUT_HTML_PATH = 'data/output.html'  # Output file name

AUTHOR = "Charles Dickens"
TITLE = "A TALE OF TWO CITIES"

# Indentation mapping for the OLD .poem .iX structure
POEM_IX_INDENT_SPACES = {'i0': 0, 'i1': 1, 'i2': 2, 'i3': 3, 'i4': 4}
# Indentation mapping for the NEW .poetry .indentX structure
POETRY_INDENT_SPACES = {'indent1': 1, 'indent2': 2, 'indent3': 3, 'indent4': 4}  # Add more if needed

# Define the Non-Breaking Space character to use (U+00A0)
NBSP = " "


def clean_and_modify_html(input_html_path, output_html_path):
    """
    Reads an HTML file (e.g., from Project Gutenberg), processes only the
    content within the <body> tag, performs numerous cleaning and restructuring
    steps, and writes the cleaned body content to a new file.

    Steps include:
    - Removing Gutenberg header/footer boilerplate.
    - Removing all inline style attributes.
    - Converting specific classes ('center', 'smcap') to inline styles.
    - Removing specific elements ('figcenter' divs, footnote anchors, tables, hrs).
    - Processing two different types of poem structures to use NBSP for indentation
      and <br> for line breaks, standardizing on <div class="poem">.
    - Ensuring all <h2> tags have a unique ID directly on the tag.
    - Removing excessive blank lines from the final output.
    - Writing only the processed content of the <body> tag.
    """
    print(f"--- Starting HTML Cleaning and Modification ---")
    print(f"Input file: '{input_html_path}'")
    print(f"Output file: '{output_html_path}'")

    # --- Read Input File ---
    try:
        with open(input_html_path, 'r', encoding='utf-8') as f_in:
            html_content = f_in.read()
            print(f"Successfully read '{input_html_path}'")
    except FileNotFoundError:
        print(f"Error: Input file '{input_html_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{input_html_path}': {e}")
        sys.exit(1)

    # --- Parse HTML and Find Body ---
    print("Parsing HTML and locating <body> tag...")
    soup = BeautifulSoup(html_content, 'html.parser')
    body_tag = soup.find('body')

    if not body_tag:
        print("Error: Could not find the <body> tag in the input HTML. Cannot proceed.")
        sys.exit(1)
    else:
        print("Found <body> tag. Processing will be limited to its contents.")
    # Step 0 - Prepend Header (New Step)
    print("Step 0: Prepending book header...")
    if AUTHOR and TITLE:  # Only add if constants are not empty
        # Create the necessary tags using the main 'soup' object's factory
        header_div = soup.new_tag('div')
        header_div['class'] = 'header'  # Assign the class

        title_h1 = soup.new_tag('h1')
        title_h1.string = TITLE  # Set H1 text from constant

        author_h3 = soup.new_tag('h3')
        author_h3.string = f"By {AUTHOR}"  # Set H3 text using f-string

        # Append H1 and H3 to the header div
        header_div.append(title_h1)
        header_div.append(author_h3)

        # Insert the new header div at the very beginning of the body tag's content
        body_tag.insert(0, header_div)
        print(f"  Prepended header for '{TITLE}' by '{AUTHOR}'.")
    else:
        print("  Skipping header prepend: AUTHOR or TITLE constant is empty.")

    # ================================================================
    # --- Start Cleaning Steps (Applied only within the body_tag) ---
    # ================================================================

    # Step 0a: Remove Gutenberg Header Boilerplate (within body)
    print("Step 0a: Removing Gutenberg header boilerplate from body...")
    header_section = body_tag.find('section', id='pg-header')
    if header_section:
        header_section.decompose()
        print("  Removed pg-header section found within body.")
    else:
        print("  Info: Did not find <section id='pg-header'> within body.")

    # Step 0b: Remove Gutenberg Footer Boilerplate (within body)
    print("Step 0b: Removing Gutenberg footer boilerplate from body...")
    footer_separator = body_tag.find('div', id='pg-end-separator')
    if footer_separator:
        elements_to_remove = list(footer_separator.find_next_siblings())  # Get siblings *after*
        elements_to_remove.append(footer_separator)  # Include the separator itself
        for element in elements_to_remove:
            if element.name:  # Check if it's a tag, not just text
                element.decompose()
        print("  Removed pg-end-separator div and subsequent elements found within body.")
    else:
        print("  Info: Did not find <div id='pg-end-separator'> within body.")

    # Step 0c: Remove HTML comments (within body) (New Step)
    print("Step 0c: Removing HTML comments from body...")
    comment_count = 0
    # Find all comment objects within the body_tag
    comments = body_tag.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        comment.decompose()
        comment_count += 1
    print(f"Removed {comment_count} HTML comments within body.")

    # Step 0d: Remove all <section> and <table> elements (within body) (New Step)
    print("Step 0d: Removing all <section> and <table> elements from body...")
    removed_count = 0
    # Find all 'section' and 'table' tags within the body_tag
    tags_to_remove = body_tag.find_all(['section', 'table'])
    for tag in tags_to_remove:
        # --- Optional Guard ---
        # You *could* add checks here if you wanted to preserve specific sections/tables
        # Example: if tag.name == 'section' and tag.get('id') == 'keep_this_section': continue
        # --- End Optional Guard ---

        tag.decompose()  # Remove the tag and all its contents
        removed_count += 1
    print(f"Removed {removed_count} <section> or <table> elements within body.")

    # Step 1: Remove existing inline styles (within body)
    print("Step 1: Removing existing inline styles from body...")
    style_count = 0
    for tag in body_tag.find_all(True):  # Find all tags within body
        if tag.has_attr('style'):
            del tag['style']
            style_count += 1
    print(f"Removed {style_count} existing inline style attributes within body.")

    # Step 2: Replace class='center' with inline style (within body)
    print("Step 2: Replacing class='center' with style='text-align: center;' in body...")
    center_class_count = 0
    for tag in body_tag.find_all(class_='center'):
        if tag.has_attr('class'): del tag['class']
        tag['style'] = 'text-align: center;'
        center_class_count += 1
    print(f"Replaced class='center' on {center_class_count} tags within body.")

    # Step 3: Replace class='smcap' with inline style (within body)
    print("Step 3: Replacing class='smcap' with style='font-variant: small-caps;' in body...")
    smcap_count = 0
    for tag in body_tag.find_all(class_='smcap'):
        if tag.has_attr('class'): del tag['class']
        tag['style'] = 'font-variant: small-caps;'
        smcap_count += 1
    print(f"Replaced class='smcap' on {smcap_count} tags within body.")

    # Step 4: Remove <div class="figcenter"> elements (within body)
    print("Step 4: Removing <div class='figcenter'> elements from body...")
    figcenter_count = 0
    for div_tag in body_tag.find_all('div', class_='figcenter'):
        div_tag.decompose()
        figcenter_count += 1
    print(f"Removed {figcenter_count} <div class='figcenter'> elements within body.")

    # Step 5: Remove footnote anchor tags (within body)
    print("Step 5: Removing footnote anchor tags from body...")
    footnote_anchor_count = 0
    # Use body_tag.select to limit scope
    footnote_anchors = body_tag.select('a[id^="FNanchor_"], a.fnanchor')
    for anchor in footnote_anchors:
        anchor.decompose()
        footnote_anchor_count += 1
    print(f"Removed {footnote_anchor_count} footnote anchor tags within body.")

    # Step 6: Remove <table> elements (within body)
    print("Step 6: Removing <table> elements from body...")
    table_count = 0
    for table_tag in body_tag.find_all('table'):
        table_tag.decompose()
        table_count += 1
    print(f"Removed {table_count} <table> elements within body.")

    # Step 7: Process NEW '.poetry > .stanza > .verse.indentX' structure
    print("Step 7: Processing '.poetry .verse' structure...")
    poetry_blocks_processed = 0
    verses_processed = 0
    for poetry_div in body_tag.find_all('div', class_='poetry'):
        poetry_blocks_processed += 1
        for verse_div in poetry_div.find_all('div', class_='verse'):
            # Unwrap inner formatting tags like <i>
            inner_format_tags = verse_div.find_all(['i', 'b', 'em', 'strong'])  # Add more if needed
            for inner_tag in inner_format_tags:
                if inner_tag.parent == verse_div:  # Avoid unwrapping deeply nested tags if any
                    inner_tag.unwrap()

            # Determine indentation level from 'indentX' class
            indent_level = 0
            verse_classes = verse_div.get('class', [])
            for cls in verse_classes:
                if cls in POETRY_INDENT_SPACES:
                    indent_level = POETRY_INDENT_SPACES[cls]
                    break

            # Prepend NBSP based on indent level (apply factor of 2)
            if indent_level > 0:
                leading_spaces = NBSP * (indent_level * 2)
                if verse_div.contents:
                    verse_div.insert(0, NavigableString(leading_spaces))
                else:
                    verse_div.append(NavigableString(leading_spaces))

            # Append a <br> tag to ensure line break
            verse_div.append(soup.new_tag('br'))

            # Unwrap the verse div itself, promoting its content
            verse_div.unwrap()
            verses_processed += 1

        # After processing all verses, unwrap the stanza divs within this poetry block
        for stanza_div in poetry_div.find_all('div', class_='stanza'):
            stanza_div.unwrap()

        # Rename the outer div class from 'poetry' to 'poem' for consistency
        current_classes = poetry_div.get('class', [])
        new_classes = [c for c in current_classes if c != 'poetry'] + ['poem']
        poetry_div['class'] = new_classes

    print(f"Processed {verses_processed} verses in {poetry_blocks_processed} '.poetry' blocks.")

    # Step 8: Process OLD '.poem .stanza span.iX' structure
    print("Step 8: Processing OLD '.poem .stanza span.iX' structure...")
    span_processed_count = 0
    processed_parents_step7 = set(body_tag.find_all('div', class_='poem'))  # Get parents potentially modified by step 7

    # Iterate through divs that might still have the old structure
    # Need to re-find elements as the structure might have changed
    possible_old_poem_divs = body_tag.find_all('div', class_='poem')  # Includes those renamed in step 7

    for poem_div in possible_old_poem_divs:
        # Check if this div *wasn't* one originally named 'poetry' (handled above)
        # This check is imperfect but tries to avoid reprocessing
        original_poetry = any(cls == 'poetry' for cls in poem_div.get('class', []))  # Recheck needed
        if not original_poetry:  # Or find a better way to track processed elements if needed
            # Select spans within stanzas, only if stanza exists
            stanzas_in_poem = poem_div.find_all('div', class_='stanza',
                                                recursive=False)  # Look for direct stanza children
            for stanza in stanzas_in_poem:
                spans_in_stanza = stanza.find_all('span')  # Find spans within this stanza
                for span in spans_in_stanza:
                    # Process only if it has an iX class
                    indent_level = 0
                    span_classes = span.get('class', [])
                    has_ix_class = False
                    for cls in span_classes:
                        if cls in POEM_IX_INDENT_SPACES:
                            indent_level = POEM_IX_INDENT_SPACES[cls]
                            has_ix_class = True
                            break

                    if has_ix_class:  # Only process spans that match the iX pattern
                        if indent_level > 0:
                            leading_spaces = NBSP * (indent_level * 2)
                            span.insert(0, NavigableString(leading_spaces))

                        # Add <br> if missing? Assume existing <br> is correct.

                        # Unwrap the span
                        if span.parent:  # Check if still attached
                            if span.contents:
                                span.unwrap();
                                span_processed_count += 1
                            else:
                                span.decompose()

    print(f"Processed {span_processed_count} spans in potential OLD '.poem .stanza span.iX' structure.")

    # Step 9: Unwrap remaining OLD '.poem .stanza' divs
    print("Step 9: Unwrapping remaining OLD '.poem .stanza' divs...")
    stanza_unwrap_count = 0
    # Use list() to safely iterate while modifying
    for stanza in list(body_tag.select('.poem > .stanza')):  # Direct children only
        if stanza.parent:  # Check if still attached
            if stanza.contents:
                stanza.unwrap();
                stanza_unwrap_count += 1
            else:
                stanza.decompose()
    print(f"Unwrapped {stanza_unwrap_count} remaining OLD stanza divs.")

    # Step 10: Ensure all H2 tags have an ID directly on the H2
    print("Step 10: Ensuring all <h2> tags have an ID directly...")
    h2_id_added_count = 0
    generated_id_counter = 1
    for h2_tag in body_tag.find_all('h2'):
        if not h2_tag.get('id'):
            inner_anchor_id = None
            inner_anchor = h2_tag.find('a', id=True)  # Find first inner anchor with any ID
            if inner_anchor:
                inner_anchor_id = inner_anchor.get('id')
                # Clean up anchor: Remove if empty, otherwise remove ID
                if not inner_anchor.get_text(strip=True) and not inner_anchor.has_attr('href'):
                    inner_anchor.decompose()
                else:
                    del inner_anchor['id']  # Remove ID from non-empty anchor

            if inner_anchor_id:
                # Move ID from inner anchor to H2
                h2_tag['id'] = inner_anchor_id
                h2_id_added_count += 1
            else:
                # Generate new ID for H2
                h2_tag['id'] = f"chap{generated_id_counter}"
                h2_id_added_count += 1
                generated_id_counter += 1
    print(f"Ensured IDs directly on relevant <h2> tags (added/moved: {h2_id_added_count}).")

    # Step 11: Remove <hr> tags
    print("Step 11: Removing <hr> tags...")
    hr_count = 0
    for hr_tag in body_tag.find_all('hr'):
        hr_tag.decompose()
        hr_count += 1
    print(f"Removed {hr_count} <hr> tags.")

    # Step 12: Remove empty <p> and <div> tags (New Step)
    print("Step 12: Removing empty <p> and <div> tags...")
    empty_tag_count = 0
    # Find all potentially empty tags within the body
    # Iterate multiple times or use list() to handle nested emptying, but start simple
    tags_to_check = body_tag.find_all(['p', 'div'])

    for tag in tags_to_check:
        # Check if tag still exists (might have been decomposed as child of another)
        if tag.parent:
            # Check if the tag contains only whitespace or is truly empty
            # get_text(strip=True) is effective for this check
            if not tag.get_text(strip=True):
                # Further check: ensure it doesn't contain significant non-text content like <img>
                has_significant_child = False
                for child in tag.children:
                    # Check for tag names that signify non-emptiness even without text
                    if child.name in ['img', 'hr', 'input', 'video', 'audio',
                                      'br']:  # Added 'br' - keep <p><br></p>? Decide.
                        has_significant_child = True
                        break
                if not has_significant_child:
                    # print(f"    Removing empty tag: <{tag.name}>") # Debug print
                    tag.decompose()
                    empty_tag_count += 1

    print(f"Removed {empty_tag_count} empty <p> or <div> tags (based on text content).")
    # Step 13: Append "THE END" block (New Step)
    print("Step 13: Appending 'THE END' block...")
    # Create the necessary tags using the main 'soup' object's factory
    the_end_div = soup.new_tag('div')
    the_end_div['class'] = 'the-end'  # Use list if multiple classes needed

    the_end_h3 = soup.new_tag('h3')
    the_end_h3.string = "THE END"  # Add text content

    the_end_div.append(the_end_h3)  # Put H3 inside the DIV

    # Append the whole new block to the end of the body tag's content
    body_tag.append(the_end_div)
    print("  Appended block.")

    # Step 14: Extract body content, clean blank lines, and wrap in <div class="book"> (Renumbered & Modified)
    print("Step 14: Extracting, cleaning, and wrapping final content...")
    # Decode contents first
    cleaned_body_content_raw = body_tag.decode_contents()

    # Clean blank lines with Regex
    cleaned_body_content = re.sub(r'\n\s*\n+', '\n', cleaned_body_content_raw).strip()

    # Wrap the cleaned content in the final div
    final_output_html = f'<div class="book">\n{cleaned_body_content}\n</div>'  # Using f-string for wrapping
    print("  Content extracted, cleaned, and wrapped in <div class=\"book\">.")

    # Step 15: Write final wrapped content to file (Renumbered)
    print("Step 15: Writing final wrapped content to output file...")
    try:
        with open(output_html_path, 'w', encoding='utf-8') as f_out:
            # Write the variable containing the wrapped content
            f_out.write(final_output_html)
        print(f"Successfully wrote final content to '{output_html_path}'")
    except Exception as e:
        print(f"Error writing to file '{output_html_path}': {e}")
        sys.exit(1)


# --- Main Execution Block ---
if __name__ == "__main__":
    clean_and_modify_html(INPUT_HTML_PATH, OUTPUT_HTML_PATH)
    print("--- Process Complete ---")
    print()

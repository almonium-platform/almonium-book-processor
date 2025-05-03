import os
import re

from bs4 import BeautifulSoup

# Define the input file path relative to the script location
# Assumes 'data/input.html' exists in the same directory structure
input_file = os.path.join('data', 'input.html')

try:
    # --- 1. Read the HTML file ---
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # --- 2. Parse the HTML ---
    # 'html.parser' is a built-in Python parser
    soup = BeautifulSoup(html_content, 'html.parser')

    # --- 3. Extract Text Content ---
    # soup.get_text() effectively strips all HTML tags and gets the text
    text_content = soup.get_text()

    # --- 4. Find and Count Words ---
    # Use regex to find sequences of alphabetic characters (words).
    # \b ensures we match whole words (word boundaries).
    # [a-zA-Z]+ matches one or more letters (case-insensitive).
    # This method ignores numbers and punctuation attached to words.
    words = re.findall(r'\b[a-zA-Z]+\b', text_content)

    # Count the number of words found
    word_count = len(words)

    # --- 5. Print the Result ---
    print(f"Found {word_count} actual words in '{input_file}'.")

except FileNotFoundError:
    print(f"Error: Input file not found at '{input_file}'")
    print("Please ensure the 'data' directory exists and contains 'input.html'.")
except Exception as e:
    print(f"An error occurred: {e}")

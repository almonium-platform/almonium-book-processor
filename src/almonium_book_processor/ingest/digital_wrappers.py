"""Recognize publisher-independent digital wrapper text."""

import re

_PATTERN = re.compile(
    r"^(?:"
    r"There are several editions of this ebook in the Project Gutenberg collection\."
    r"\s+Various characteristics of each ebook are listed to aid in selecting the preferred file\."
    r"|This eBook is for the use of anyone anywhere at no cost and with almost no restrictions"
    r"\s+whatsoever\..*under the terms of the Project Gutenberg License"
    r"|This eBook (?:is|was) produced by (?:the Online Distributed Proofreading Team"
    r"\b|[\w.'’ -]{1,90}\.$)"
    r"|a source file at Project Gutenberg of DE created by [\w.'’ -]{1,90} for PG-DE\.$"
    r"|(?:Produced by )?This eBook was prepared by [\w.'’ -]{1,90} from$"
    r"|(?:Character set encoding|Encoding):\s*(?:ISO-8859-\d+|UTF-8|US-ASCII)\.?$"
    r"|We thank the Biblioth[eè]que Nationale de France that has made available the image files "
    r"at www\.gallica\.bnf\.fr\b"
    r"|Nous remercions la Biblioth[eè]que Nationale de France qui a mis [aà] disposition "
    r"les images dans www\.gallica\.bnf\.fr\b"
    r"|This e-text was produced from Project Runeberg['’]s digital facsimile edition of\s"
    r"|Project Runeberg publishes free digital editions of Nordic literature\.\s"
    r"Learn more at https?://(?:www\.)?runeberg\.org/?$"
    r")",
    re.I,
)


def is_digital_wrapper(text: str) -> bool:
    return bool(_PATTERN.match(text.strip()))

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

SOURCE_QA_SCHEMA_VERSION = 1
SOURCE_QA_PROCESSOR_VERSION = "source-qa-v2"

WORD_PAIR = re.compile(
    r"(?=(\b(?P<left>[^\W\d_]{2,})[ \t]+(?P<right>[^\W\d_]{2,})\b))",
    re.UNICODE,
)
DETACHED_INITIAL = re.compile(
    r"^(?:[\"'\u2018\u201c])?(?P<left>[^\W\d_])[ \t]+(?P<right>[^\W\d_]{2,})\b",
    re.UNICODE,
)
BROKEN_HYPHEN = re.compile(
    r"\b(?P<left>[^\W\d_]{2,})-[ \t\r\n]+(?P<right>[^\W\d_]{2,})\b",
    re.UNICODE,
)
GUTENBERG_MARKERS = (
    "project gutenberg",
    "start of the project gutenberg",
    "end of the project gutenberg",
    "gutenberg-tm",
)


@dataclass(frozen=True, slots=True)
class SourceQABlock:
    id: str
    block_id: str
    chapter: int
    text: str


@dataclass(frozen=True, slots=True)
class SourceQAFinding:
    block_id: str | None
    stable_block_id: str
    code: str
    start_offset: int | None
    end_offset: int | None
    original_text: str
    suggested_text: str
    confidence: float
    message: str
    evidence: dict[str, Any]

    def fingerprint(self) -> str:
        value = "\0".join(
            [
                self.stable_block_id,
                self.code,
                str(self.start_offset),
                str(self.end_offset),
                self.original_text,
                self.suggested_text,
            ]
        )
        return hashlib.sha256(value.encode()).hexdigest()

    def payload(self) -> dict[str, Any]:
        return {**asdict(self), "fingerprint": self.fingerprint()}


def _word_frequency(text: str, language: str) -> float:
    try:
        from wordfreq import zipf_frequency
    except ImportError as error:
        message = "Install the worker dependency group to scan source text"
        raise RuntimeError(message) from error
    return float(zipf_frequency(text, language))


def _join_finding(
    block: SourceQABlock,
    match: re.Match[str],
    language: str,
    frequency_lookup: Callable[[str, str], float],
    *,
    code: str,
    minimum_gain: float,
    minimum_combined_frequency: float = 3.0,
) -> SourceQAFinding | None:
    left, right = match.group("left"), match.group("right")
    combined = left + right
    combined_zipf = frequency_lookup(combined.casefold(), language)
    separated_zipf = frequency_lookup(f"{left} {right}".casefold(), language)
    left_zipf = frequency_lookup(left.casefold(), language)
    right_zipf = frequency_lookup(right.casefold(), language)
    gain = combined_zipf - separated_zipf
    suspicious_fragments = [
        zipf for value, zipf in ((left, left_zipf), (right, right_zipf)) if len(value) <= 3
    ]
    if (
        combined_zipf < minimum_combined_frequency
        or gain < minimum_gain
        or (
            code == "probable_split_word"
            and (not suspicious_fragments or min(suspicious_fragments) > 4.2)
        )
    ):
        return None
    start = match.start("left")
    end = match.end("right")
    original = block.text[start:end]
    return SourceQAFinding(
        block_id=block.id,
        stable_block_id=block.block_id,
        code=code,
        start_offset=start,
        end_offset=end,
        original_text=original,
        suggested_text=combined,
        confidence=round(min(0.98, 0.7 + gain / 2), 3),
        message=f"“{original}” may be the joined word “{combined}”.",
        evidence={
            "combined_zipf": round(combined_zipf, 3),
            "separated_zipf": round(separated_zipf, 3),
            "left_zipf": round(left_zipf, 3),
            "right_zipf": round(right_zipf, 3),
            "zipf_gain": round(gain, 3),
        },
    )


def analyze_source_quality(
    blocks: Iterable[SourceQABlock],
    language: str,
    *,
    frequency_lookup: Callable[[str, str], float] = _word_frequency,
) -> list[SourceQAFinding]:
    """Return conservative deterministic findings without changing book text."""

    blocks = list(blocks)
    findings: list[SourceQAFinding] = []
    duplicate_blocks: dict[str, SourceQABlock] = {}
    for block in blocks:
        lowered = block.text.casefold()
        if any(marker in lowered for marker in GUTENBERG_MARKERS):
            findings.append(
                SourceQAFinding(
                    block_id=block.id,
                    stable_block_id=block.block_id,
                    code="gutenberg_boilerplate",
                    start_offset=None,
                    end_offset=None,
                    original_text="",
                    suggested_text="",
                    confidence=0.99,
                    message="This block appears to contain Project Gutenberg boilerplate.",
                    evidence={},
                )
            )

        for index, character in enumerate(block.text):
            category = unicodedata.category(character)
            if character == "\ufffd" or (category == "Cf" and character != "\u00ad"):
                findings.append(
                    SourceQAFinding(
                        block_id=block.id,
                        stable_block_id=block.block_id,
                        code="malformed_unicode",
                        start_offset=index,
                        end_offset=index + 1,
                        original_text=character,
                        suggested_text="",
                        confidence=0.98,
                        message=f"Unexpected Unicode character U+{ord(character):04X}.",
                        evidence={"unicode_name": unicodedata.name(character, "UNKNOWN")},
                    )
                )

        for match in BROKEN_HYPHEN.finditer(block.text):
            finding = _join_finding(
                block,
                match,
                language,
                frequency_lookup,
                code="broken_hyphenation",
                minimum_gain=0.0,
            )
            if finding:
                findings.append(finding)
        detached_initial = DETACHED_INITIAL.match(block.text)
        if detached_initial:
            left = detached_initial.group("left")
            right = detached_initial.group("right")
            if left.isupper() and right.islower():
                finding = _join_finding(
                    block,
                    detached_initial,
                    language,
                    frequency_lookup,
                    code="detached_initial",
                    minimum_gain=0.5,
                    minimum_combined_frequency=2.0,
                )
                if finding:
                    findings.append(finding)
        for match in WORD_PAIR.finditer(block.text):
            finding = _join_finding(
                block,
                match,
                language,
                frequency_lookup,
                code="probable_split_word",
                minimum_gain=0.2,
            )
            if finding:
                findings.append(finding)

        normalized = " ".join(block.text.casefold().split())
        if len(normalized) >= 100:
            earlier = duplicate_blocks.get(normalized)
            if earlier:
                findings.append(
                    SourceQAFinding(
                        block_id=block.id,
                        stable_block_id=block.block_id,
                        code="duplicate_block",
                        start_offset=None,
                        end_offset=None,
                        original_text="",
                        suggested_text="",
                        confidence=0.95,
                        message=f"This block duplicates {earlier.block_id}.",
                        evidence={"earlier_block_id": earlier.block_id},
                    )
                )
            else:
                duplicate_blocks[normalized] = block
    return findings

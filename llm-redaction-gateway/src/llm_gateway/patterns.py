"""PII Patterns: regex + Max Pattern Length, per ADR-0001/0002.

Written tight enough that real overlaps between patterns aren't expected
(ADR-0002) -- exact digit/dash/space grouping per pattern, not loose
digit-run matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIPattern:
    name: str
    regex: re.Pattern[str]
    max_length: int  # L


PATTERNS: list[PIIPattern] = [
    PIIPattern("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), max_length=11),
    PIIPattern(
        "credit_card",
        re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
        max_length=19,
    ),
    PIIPattern(
        "email",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        max_length=60,
    ),
]

HOLDBACK_WINDOW = max(p.max_length for p in PATTERNS) - 1


def redact(text: str, counts: dict[str, int] | None = None) -> str:
    # Collect every match from every pattern first -- redacting one
    # pattern at a time, in list order, would make whichever pattern is
    # checked last silently win any overlap (ADR-0002 exists specifically
    # to prevent that).
    spans: list[tuple[int, int, str]] = []
    for pattern in PATTERNS:
        for m in pattern.regex.finditer(text):
            spans.append((m.start(), m.end(), pattern.name))
    spans.sort(key=lambda span: (span[0], -(span[1] - span[0])))

    kept: list[tuple[int, int, str]] = []
    for start, end, name in spans:
        if kept and start < kept[-1][1]:
            # Overlaps the previously kept match -- the longer one wins,
            # never whichever pattern happened to be checked first.
            prev_start, prev_end, _ = kept[-1]
            if (end - start) > (prev_end - prev_start):
                kept[-1] = (start, end, name)
            continue
        kept.append((start, end, name))

    if counts is not None:
        # Caller-supplied dict, e.g. for observability -- never the
        # matched text itself, only which pattern fired and how often.
        for _, _, name in kept:
            counts[name] = counts.get(name, 0) + 1

    pieces = []
    cursor = 0
    for start, end, _ in kept:
        pieces.append(text[cursor:start])
        pieces.append("[REDACTED]")
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)

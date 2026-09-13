from llm_gateway import patterns
from llm_gateway.patterns import redact


def test_overlapping_matches_resolve_to_the_longest():
    # A 16-digit local part makes this string match BOTH credit_card (the
    # digits alone) and email (the whole string) -- overlapping spans,
    # email strictly the longer one. The longer match must win, not
    # whichever pattern happens to be checked first (ADR-0002).
    text = "contact 4111111111111111@example.com for details"
    assert redact(text) == "contact [REDACTED] for details"


def test_redaction_is_order_independent():
    text = "contact 4111111111111111@example.com for details"
    original_order = list(patterns.PATTERNS)
    try:
        forward = redact(text)
        patterns.PATTERNS.reverse()
        reversed_order = redact(text)
    finally:
        patterns.PATTERNS[:] = original_order
    assert forward == reversed_order

---
status: accepted
---

# Length-bounded holdback buffer for streaming PII redaction

Redacting PII in a streamed LLM response can't scan each chunk in
isolation — patterns like an email address regularly split across chunk
boundaries chosen by the provider's tokenizer, not by anything PII-aware
(observed directly: `sumanth@gmail.com` arrived as `sumant` / `h@gmail` /
`.com` across three real deltas). We buffer a small, bounded tail of text
and only flush what's confirmed clear of any in-progress pattern.

## Considered Options

An earlier version defined "confirmed clear" as "up to the last
whitespace character," reasoning that PII tokens don't contain internal
whitespace. This is wrong in general: a formatted credit card number
(`4111 1111 1111 1111`) contains internal spaces, and the whitespace rule
would flush it one group at a time.

## Decision detail

Each tracked PII Pattern gets a fixed Max Pattern Length (`L`): SSN 11,
formatted credit card ~19, email capped at 60 (email has no true fixed
maximum; 60 comfortably covers realistic addresses without holding back
arbitrarily). The buffer always retains at least `max(L) - 1` characters
— currently 59 — regardless of their content, and is re-scanned for
complete matches on every append.

## Consequences

An email address longer than 60 characters could still leak in pieces —
an accepted limitation, not an oversight. Adding a new pattern type later
means picking its `L`, which extends the holdback window for every
pattern, not just the new one.

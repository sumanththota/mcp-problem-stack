# Spec — LLM Gateway Streaming Guardrail (PII Redaction)

Synthesized from the grilling session captured in `CONTEXT.md` (glossary)
and `docs/adr/0001`–`0005` (decisions). Consult those directly for full
rationale — this is a summary, not a replacement.

## Problem Statement

An engineer operating an LLM gateway needs to stream a model's
text-generation response back to a caller in real time, but the model's
output may contain PII (emails, SSNs, credit card numbers) that must
never reach the caller unredacted — including when a PII pattern happens
to be split across two or more stream chunks by the provider's own
chunking, which is not PII-aware. The response can't be buffered in full
before checking it, because that would defeat the point of streaming:
memory use would grow with response length, and the caller would wait for
the entire response before seeing anything.

## Solution

A proxy endpoint that streams the response back to the caller
incrementally, redacting PII as it goes, using a bounded Holdback Buffer
that only ever retains a small, fixed-size tail of "not yet confirmed
safe" text — never the whole response — regardless of how long the
stream runs.

## User Stories

1. As a calling client, I want to receive the model's response as a live
   stream, so that I see output incrementally instead of waiting for the
   full generation to finish.
2. As a calling client, I want any email address in the response replaced
   with `[REDACTED]`, so that sensitive personal data never reaches me in
   the clear.
3. As a calling client, I want any SSN in the response replaced with
   `[REDACTED]`, so that sensitive personal data never reaches me in the
   clear.
4. As a calling client, I want any credit card number replaced with
   `[REDACTED]` even when it's formatted with internal spaces, so that
   formatting doesn't defeat redaction.
5. As a calling client, I want PII that happens to be split across two or
   more stream chunks to still be fully redacted, so that an unlucky
   chunk boundary can't be used to leak sensitive data.
6. As a calling client, I want the response text and its ordering
   otherwise unchanged apart from redacted spans, so that redaction
   doesn't corrupt or reorder real content.
7. As a calling client, I want the stream's "finished" signal to arrive
   only after every piece of content has actually been sent to me, so
   that my client library doesn't stop listening early and silently drop
   the tail of the response.
8. As a calling client, I want time-to-first-token to stay low, so that
   redaction doesn't make the gateway feel meaningfully slower than
   talking to the provider directly.
9. As the engineer operating the gateway, I want the gateway to never
   buffer the full response in memory, so that memory use stays bounded
   regardless of response length.
10. As the engineer operating the gateway, I want the amount of held-back
    text bounded by the longest tracked PII pattern, not by response
    length, so that memory use is predictable under load.
11. As the engineer operating the gateway, I want each PII pattern's
    maximum realistic length to be an explicit, documented choice, so
    that the holdback window's size is reviewable, not accidental.
12. As the engineer operating the gateway, I want pattern-match outcomes
    to never depend on the order patterns are checked in, so redaction
    behavior can't silently change if the pattern list is reordered.
13. As the engineer operating the gateway, when two patterns could match
    overlapping text, I want the longest match to win, so overlap
    resolution is a stated rule, not an accident of check order.
14. As the developer testing this gateway, I want to construct an exact,
    chosen sequence of stream chunks — including deliberately split PII —
    so I can assert on specific boundary cases deterministically and
    repeatably in CI.
15. As the developer testing this gateway, I want a separate smoke test
    against the real upstream provider, so I have confidence the
    gateway's parsing matches genuine wire behavior, independent of the
    deterministic correctness tests.
16. As the engineer operating the gateway, I want upstream disconnects,
    client backpressure, and API-key/cost/rate-limit handling explicitly
    marked out of scope, so no one mistakes an unhandled case for an
    oversight.
17. As a future maintainer, I want the project's vocabulary (delta,
    chunk, holdback buffer, safe-to-flush boundary, PII pattern, max
    pattern length, TTFT) defined in one place, so discussions and code
    use consistent, precise terms.
18. As a future maintainer, I want the reasoning behind non-obvious
    decisions (length-bounded vs. whitespace-bounded flushing,
    control-signal holdback, the testing seam choice) recorded, so I
    don't "fix" something that was deliberate.

## Implementation Decisions

- The gateway maintains a **Holdback Buffer**: a small, bounded span of
  recently-arrived text not yet confirmed safe to release.
- Safe-to-flush is determined by **position, not content**: after every
  buffer append and match-and-redact pass, everything except the last
  `L - 1` characters is released, where `L` is the largest Max Pattern
  Length across all tracked patterns. An earlier whitespace-based rule
  was considered and rejected — it leaks a formatted credit card one
  group at a time, since that pattern legitimately contains internal
  whitespace.
- **Max Pattern Length per pattern**: SSN = 11, formatted credit card ≈
  19, email capped at 60 (a deliberate practical ceiling — email has no
  true fixed maximum, and the cost of the cap being slightly too small is
  worse than the cost of it being generous).
- **Pattern check order carries no semantic weight.** Patterns are
  written precisely enough that overlapping matches between them are not
  expected; if an overlap ever occurs anyway, the longest match wins.
  This is a stated rule, independent of list order.
- **Outgoing chunk shape mirrors the upstream provider's own delta
  envelope.** Constant fields (id, model, created) are captured once and
  copied onto every emitted chunk, synthesized or not.
- **`finish_reason: "stop"` is held back the same way buffered text is.**
  It is only attached to the chunk the gateway emits last, after its own
  final buffer flush completes — never relayed on the upstream chunk it
  originally arrived on, since a client that treats `"stop"` as "stop
  listening" would otherwise silently drop the final flush.
- **On stream end**, the buffer receives one final match-and-redact pass
  before being flushed, regardless of whether a natural safe-to-flush
  point was ever reached.
- **Upstream provider**: an OpenAI-compatible streaming chat-completion
  endpoint. This choice does not carry meaningful lock-in and was
  evaluated as not warranting a formal ADR.

## Testing Decisions

- A good test here asserts on the gateway's **actual externally-observed
  output stream** — redacted content landing in the right places, correct
  chunk ordering, `finish_reason` arriving at the right moment — not on
  internal buffer state read directly.
- **Primary seam**: the gateway's own public streaming endpoint, exercised
  end-to-end, with the upstream provider replaced by a fully-controlled
  mock streaming server that emits an exact, test-specified sequence of
  deltas. This is the one seam correctness is asserted against, and it's
  what makes deliberate adversarial cases possible: a split mid-`@`, a
  split mid-TLD, a credit-card split at each internal space, a split at
  the exact `L - 1` edge, a split across three or more chunks.
- **Secondary check, kept separate**: one real call against the actual
  upstream provider, used only as a smoke test that genuine wire behavior
  (SSE shape, auth, network plumbing) matches what the gateway assumes.
  Not used to assert boundary correctness, since real chunk boundaries
  aren't controllable on demand.
- **Prior art**: Task 2 (the MCP security gateway) used the same shape —
  a hand-built mock standing in for the downstream system, with tests
  speaking real HTTP to a genuinely running gateway process, rather than
  mocking the gateway's own internals.

## Out of Scope

- Upstream connection resilience (retries, reconnect on drop).
- Client backpressure handling.
- API key management, cost controls, rate limiting.
- Any PII pattern beyond email, SSN, and credit card.
- Multi-choice completions (`n > 1`) or non-text response modalities.

## Further Notes

- Full glossary: `CONTEXT.md`. Full decision rationale:
  `docs/adr/0001` through `0005`.
- No issue tracker was configured for this project, so this spec is saved
  as a file rather than published as a ticket.
- The spec was broken into six tracer-bullet tickets (approved): local
  ticket files live under `.scratch/llm-redaction-gateway/issues/`
  (`01`–`06`, numbered in dependency order). A visual board of the same
  six tickets — dependency diagram, status, acceptance criteria — is
  published at https://claude.ai/code/artifact/2a31d67e-1c94-400e-becd-12cc04dd9227.

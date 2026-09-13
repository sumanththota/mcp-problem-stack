# LLM Gateway Streaming Guardrail

A proxy that streams an LLM's text-generation response back to the caller
while redacting PII patterns (emails, SSNs, credit card numbers) that may
be split across the stream's own chunk boundaries.

## Language

**Delta**:
The piece of new text one streamed message adds — not the running total.
The caller accumulates deltas itself to reconstruct the full response.
_Avoid_: Token, chunk

**Chunk**:
One `data: {...}` message as it arrives over the wire. Its boundary is
chosen by the model's tokenizer and the provider's serving layer, not by
anything PII-aware.
_Avoid_: Packet, frame

**Holdback Buffer**:
The small, bounded span of recently-arrived text kept in memory because
it might still be completing an unfinished PII pattern.
_Avoid_: Cache, queue

**Safe-to-flush Boundary**:
The point in the holdback buffer up to which text is confirmed not to be
part of any unfinished pattern match, and can be released to the caller.
_Avoid_: Word boundary, line boundary

**PII Pattern**:
A regex paired with its Max Pattern Length (see below), together defining
one kind of sensitive data to detect and redact — e.g. email, SSN, credit
card.
_Avoid_: Rule, filter

**Max Pattern Length (L)**:
The longest a single instance of a given PII Pattern can realistically
be. Governs how much of the buffer must be held back at all times.
_Avoid_: Window size

**TTFT (Time To First Token)**:
How long the caller waits before seeing any output at all — the latency
metric the task names directly as something to minimize.

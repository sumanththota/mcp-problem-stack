# 04: Correct finish_reason sequencing on stream end

**What to build:** ADR-0004's rule enforced and proven — a case where PII
sits unflushed right up to stream end, verifying `"stop"` only reaches
the caller after the buffer's final flush completes, never before.

**Blocked by:** 03 (Redact PII across chunk boundaries)

**Status:** ready-for-agent

- [ ] `finish_reason: "stop"` is never relayed on the chunk it arrived on
      if the buffer still holds text
- [ ] A test constructs PII sitting unflushed at the moment the upstream
      stream ends
- [ ] The gateway runs one final match-and-redact pass on the remainder
      before flushing it
- [ ] `"stop"` only appears on the gateway's actual last emitted chunk

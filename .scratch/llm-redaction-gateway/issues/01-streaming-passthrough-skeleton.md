# 01: Streaming passthrough skeleton

**What to build:** A gateway endpoint that accepts a chat-completion
request and relays the real OpenRouter stream back to the caller, chunk
by chunk, completely unmodified. Proves the async streaming plumbing
end-to-end before any redaction logic exists.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Endpoint accepts a chat-completion-style request
- [ ] Forwards to the real OpenRouter upstream and relays its SSE
      response chunk by chunk, unmodified
- [ ] A live curl shows tokens arriving incrementally, not all at once
- [ ] No buffering or redaction logic exists yet — this ticket only
      proves the wire path

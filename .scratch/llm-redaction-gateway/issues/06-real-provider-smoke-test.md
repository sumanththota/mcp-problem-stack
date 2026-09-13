# 06: Real-provider smoke test

**What to build:** One test against the actual OpenRouter endpoint
confirming real wire behavior matches the gateway's assumptions —
separate from and not a substitute for the deterministic tests in
tickets 03–05.

**Blocked by:** 03 (Redact PII across chunk boundaries)

**Status:** ready-for-agent

- [ ] A real request goes through the gateway to actual OpenRouter, not
      the mock
- [ ] Confirms SSE parsing and auth handling work against genuine wire
      behavior
- [ ] Not used to assert specific boundary-split behavior — that stays
      tickets 03–05's job

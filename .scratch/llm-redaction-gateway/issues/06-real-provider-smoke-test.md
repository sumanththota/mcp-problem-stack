# 06: Real-provider smoke test

**What to build:** One test against the actual OpenRouter endpoint
confirming real wire behavior matches the gateway's assumptions —
separate from and not a substitute for the deterministic tests in
tickets 03–05.

**Blocked by:** 03 (Redact PII across chunk boundaries)

**Status:** done

- [x] A real request goes through the gateway to actual OpenRouter, not
      the mock
- [x] Confirms SSE parsing and auth handling work against genuine wire
      behavior
- [x] Not used to assert specific boundary-split behavior — that stays
      tickets 03–05's job

**Verified:**
- Reachability: `tests/test_upstream_connectivity.py::test_gateway_reaches_real_openrouter`
  — fake key against real OpenRouter yields a genuine `401` (proves DNS/TLS/HTTP
  all succeed); a real key was separately confirmed to yield a genuine `429`
  rate-limit response, not a connection failure.
- Live content: a real streaming request through the gateway to real
  OpenRouter, asking the model to echo text containing an email and a
  credit card, came back as `My email is [REDACTED] and my card is
  [REDACTED], thanks.` — HTTP 200, no PII leaked. Script kept at
  `scripts/live_smoke_test.py` (manual/opt-in, not part of the
  deterministic pytest suite, per SPEC.md's testing decisions).

# 03: Redact PII across chunk boundaries

**What to build:** The core feature — the Holdback Buffer (ADR-0001,
ADR-0002) wired into the gateway, redacting email, SSN, and credit card
patterns even when split across chunks. Verified against ticket 02's mock
with a deliberately split case; the mock's own log proves what actually
arrived.

**Blocked by:** 01 (Streaming passthrough skeleton), 02 (Controlled mock
streaming server)

**Status:** ready-for-agent

- [ ] Holdback Buffer withholds only the last `L-1` characters; everything
      else flushes immediately
- [ ] Email, SSN, and credit card each redact correctly arriving whole in
      one chunk
- [ ] Each also redacts correctly when split across 2+ chunks (the 3-way
      `sumanth@gmail.com` case, at minimum)
- [ ] A formatted credit card with internal spaces is not leaked
      group-by-group
- [ ] The gateway's real streamed output reflects redacted content, not
      raw upstream/mock text

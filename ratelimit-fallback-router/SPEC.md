# Spec — Rate-Limiting & Model Fallback Router

Synthesized from the design conversation captured in this session (no separate
CONTEXT.md/ADRs were produced for this project — decisions were grilled
conversationally and are recorded below and in three artifacts, linked under
Further Notes).

## Problem Statement

An engineer operating an LLM gateway needs to accept incoming completion
requests from multiple tenants, each with its own token budget, and route
each request to a model provider — without one tenant's usage crowding out
another's, without a single provider outage or rate limit taking down every
tenant, and without any upstream failure detail leaking to the caller. A
request's true cost (completion tokens generated) isn't known until the
model finishes responding, so admission decisions have to be made against an
estimate and corrected later — and that correction has to happen reliably
even when a request never finishes cleanly.

## Solution

A gateway that enforces a **token-aware sliding-window rate limit** per
tenant API key (50,000 tokens/minute), using a **reserve-then-reconcile**
ledger backed by on-disk SQLite: each request reserves its worst-case cost
(`prompt + max_tokens`) at admission, then the reservation is corrected down
to actual usage once the response completes, with a **TTL backstop**
guaranteeing that correction happens even if the normal completion path
never runs (client disconnect, provider hang, process crash). Separately,
the gateway **fails over** from a primary to a secondary model provider on a
`429` or a `3000ms` timeout, discards any late primary response instead of
double-counting it, and returns a single **standardized, sanitized error
shape** regardless of which upstream or failure mode caused a rejection.

## User Stories

1. As a tenant calling the gateway, I want my token usage measured against
   my own limit, not other tenants', so that another tenant's traffic can't
   exhaust my quota.
2. As a tenant, I want the limiter to account for tokens, not just request
   count, so that a handful of large prompts can't consume the same budget
   as many small ones while looking identical on the ledger.
3. As a tenant, I want my rate limit measured over a rolling 60-second
   window rather than a fixed clock-aligned minute, so I can't be
   under-protected by timing requests around a reset boundary.
4. As a tenant, I want a request admitted or rejected based on the worst
   case it could cost (its full `max_tokens`), so the gateway never lets my
   in-flight requests collectively commit the provider to more than my real
   budget.
5. As a tenant, I want my charged usage corrected down to what a request
   actually used once it completes, so a conservative `max_tokens` setting
   doesn't waste my quota long after the real cost is known.
6. As a tenant, I want an abandoned or crashed request's reservation to
   release automatically, so a single failed request doesn't permanently
   shrink my available budget.
7. As a tenant, I want a legitimately slow (but still running) request to
   keep its reservation until it actually finishes, so the safety mechanism
   for crashes doesn't punish real in-flight usage.
8. As a tenant, when the primary model returns `429` or fails to respond
   within 3000ms, I want the gateway to try a secondary provider
   automatically, so a single provider's outage or throttling doesn't
   become my outage.
9. As a tenant, I want exactly one response per request even when a
   fallback occurs, so I never see a duplicate, partial, or conflicting
   answer from both providers.
10. As a tenant, if the primary's response arrives after the gateway has
    already failed over, I want it discarded rather than counted twice, so
    a race between a timeout and a late response can't corrupt my token
    accounting.
11. As a tenant, I want every error response from the gateway to have the
    same shape regardless of what actually failed upstream, so my client
    code can handle failures without depending on any one provider's error
    format.
12. As a tenant, I want error responses to never contain a raw stack trace,
    internal hostname, or vendor-specific error object, so upstream
    implementation details are never exposed to me.
13. As the engineer operating the gateway, I want rate-limiter state
    persisted to on-disk SQLite, so a gateway restart doesn't reset every
    tenant's usage to zero or wrongly lock everyone out.
14. As the engineer operating the gateway, I want concurrent requests for
    the same tenant admitted/rejected correctly without a race between
    reading and writing the ledger, so the limit holds under real
    concurrent load.
15. As the engineer operating the gateway, I want a reservation's
    time-to-live derived from the system's own call timeouts (primary +
    secondary + margin) rather than an arbitrary new constant, so the
    backstop composes with a decision already made elsewhere in the system.
16. As the engineer operating the gateway, I want the admission/settlement
    logic pure and unit-testable independent of the running server, so
    correctness can be verified without spinning up HTTP.
17. As the developer testing this gateway, I want to force a primary
    provider to return `429` or hang past 3000ms on demand, so fallback and
    timeout-race behavior can be tested deterministically.
18. As the developer testing this gateway, I want to simulate a process
    crash mid-request, so the TTL backstop's recovery behavior can be
    verified rather than assumed.

## Implementation Decisions

- **Rate limiter**: token-aware sliding window, per tenant API key, limit
  50,000 tokens/minute.
- **Admission strategy — reserve-then-reconcile.** At admission, charge
  `prompt_tokens + max_tokens` (the worst case) against the tenant's ledger.
  Once the response completes, correct that same entry down to
  `prompt_tokens + actual_completion_tokens`. Two alternatives were
  considered and rejected:
  - *Prompt-only charging* — blind to real committed load; a burst of
    concurrent requests with large `max_tokens` looks cheap on the ledger
    while the provider is actually committed to generating far more.
  - *Reserve without reconciliation* — permanently overcounts a tenant's
    real usage for up to the full window duration, blocking legitimate
    low-usage traffic behind a defensive `max_tokens` setting.
- **Persistence**: on-disk SQLite ledger, one row per reservation —
  `(tenant_id, request_id, ts, tokens, status)`. Admission checks
  `SUM(tokens)` over rows with `ts` in the trailing 60s and `status` in
  `(pending, settled)`. Window eviction is automatic via that time filter —
  no explicit delete is required for correctness.
- **Settlement backstop — settle + TTL.** A `try`/`finally` settles the
  reservation to actual usage on normal completion; a sweep force-releases
  any reservation still `pending` past a TTL, where
  `TTL = primary_timeout (3000ms) + secondary_timeout + safety margin` —
  not a newly invented constant. Two alternatives were considered and
  rejected:
  - *No backstop* — a crash permanently and silently shrinks a tenant's
    real budget.
  - *Decay-only (short TTL, no explicit settle)* — a legitimately long
    response loses its protective reservation mid-flight, exactly when
    over-commit risk is highest.
  - A *heartbeat-refreshed TTL* was also considered and rejected: it only
    earns its complexity if something can legitimately run unbounded, and
    nothing here does — every model call already has a hard timeout.
- **Fallback**: the primary model is called with a 3000ms timeout. On a
  `429` or timeout expiry, the gateway calls the secondary provider
  instead. A primary response arriving after fallback has already
  triggered is discarded — never returned to the caller, never settled or
  double-counted against the ledger.
- **Error handling**: every gateway-constructed failure (limiter rejection,
  primary failure, secondary failure) is normalized to one JSON error shape
  — a machine-readable code, a caller-safe message, a request id — never a
  raw exception, stack trace, or vendor-specific error object.

## Testing Decisions

- A good test asserts on the gateway's actual externally-observed
  behavior — the HTTP response returned to the caller, and the ledger
  state read back from SQLite — not on internal function call counts.
- **Primary seam**: the gateway's own HTTP endpoint, exercised end-to-end,
  with the primary and secondary model providers replaced by controlled
  mocks configurable on demand to return a `429`, hang past 3000ms, or
  return a normal response with a chosen actual token count. This is the
  seam correctness is asserted against.
- Concurrency and crash-recovery are explicit test categories: parallel
  requests against the same tenant key (no read/write race in admission),
  and a simulated process kill mid-request (TTL sweep recovers the
  orphaned reservation).
- **Prior art**: `mcp-security-gateway`'s standalone mock downstream, and
  `llm-redaction-gateway`'s mock OpenRouter server (configured via
  `POST /configure`) — same shape, adapted here to return `429`/timeout/a
  chosen token count on demand instead of SSE deltas.

## Out of Scope

- Real integration with an actual LLM provider — primary and secondary are
  controlled mocks for this task, same pattern as both sibling projects.
- Cross-process/distributed rate-limiter coordination (multiple gateway
  instances sharing one tenant's budget) — single-process SQLite only.
- Retry/backoff policies beyond the single primary→secondary fallback (no
  retry-the-primary-again, no tertiary provider).
- Authentication/authorization of the tenant API key itself — assumed
  already resolved before reaching the rate limiter (c.f.
  `mcp-security-gateway`'s `auth.py` for that separate concern).
- Heartbeat-based TTL renewal — evaluated and rejected, see Implementation
  Decisions.

## Further Notes

- No issue tracker was configured for this project, so this spec is saved
  as a file rather than published as a ticket, matching
  `llm-redaction-gateway`'s convention.
- Design-session artifacts referenced while reaching these decisions:
  - Requirement walkthrough — https://claude.ai/code/artifact/55c662d7-6e0a-4d36-a1cc-b72c65615452
  - Reserve-then-reconcile, stepped through concretely —
    https://claude.ai/code/artifact/1258aec8-0006-41d8-bfaf-66f98d70cb61
  - Settlement backstop comparison —
    https://claude.ai/code/artifact/4e165c62-a761-41a2-8b5d-aff56dcff5a1
- Architecture references for the two finished sibling projects this
  design borrows patterns from (shared-client/lifespan, tier-1/tier-2
  error split, controlled-mock testing seam) are saved locally at
  `../architecture-reference/*.html` in this worktree.
- Next step: break this spec into tracer-bullet tickets (`to-tickets`).

# A controlled mock streaming server drives correctness tests, not the real provider

A real LLM provider's chunk boundaries are decided by its tokenizer and
serving layer, not by the test — so it can't be made to reproduce a
specific split (e.g. an `@` landing exactly between two deltas) on
demand or repeatably. Correctness tests instead run against a mock
streaming server that emits an exact, test-specified sequence of deltas,
so every adversarial boundary case (mid-`@`, mid-TLD, a credit card split
at each internal space, a split at the exact `L-1` edge) can be
constructed deliberately and asserted on in CI.

## Considered Options

Record-and-replay (capture one real response, replay its bytes
deterministically) was considered. Rejected as the primary mechanism: it
only gives determinism over whatever split happened to occur in the
recording, not a chosen one, so it can't manufacture a specific worst-case
boundary.

## Consequences

A real provider call is still made, separately, as a smoke test that the
SSE parsing and auth/HTTP plumbing work against genuine wire behavior —
but it is not where boundary correctness is asserted.

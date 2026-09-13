# 02: Controlled mock streaming server

**What to build:** A standalone server whose exact delta sequence is
specified per test — the ADR-0003 testing seam. Runs independently of the
gateway in ticket 01, so it can be built in parallel.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Exposes a streaming endpoint whose exact delta sequence is set per
      test
- [ ] Can emit a sequence deliberately split at a chosen character
      boundary (e.g. mid-`@`)
- [ ] Logs every request it receives, so a test can assert on what
      actually arrived
- [ ] Runs independently of the gateway from ticket 01

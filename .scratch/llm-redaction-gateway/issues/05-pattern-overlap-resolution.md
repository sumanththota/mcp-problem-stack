# 05: Pattern-overlap resolution

**What to build:** ADR-0002's tiebreak rule implemented and proven with a
deliberately constructed overlapping-match case, even though real
overlaps aren't expected once patterns are written precisely.

**Blocked by:** 03 (Redact PII across chunk boundaries)

**Status:** ready-for-agent

- [ ] A constructed input where two patterns could match overlapping text
      redacts using the longest match
- [ ] Behavior is unchanged if the internal pattern-check order is
      reversed

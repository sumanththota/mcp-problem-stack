# Pattern check order is not load-bearing; overlaps resolve by longest match

Whether one PII Pattern is checked before another must never determine
the redaction outcome — that would make correctness depend on accidental
list order rather than a stated rule. Patterns are written precise enough
(exact digit/dash/space grouping per pattern) that real overlaps between
email, SSN, and credit card aren't expected to occur; if two patterns
ever do match overlapping text anyway, the longest match wins.

"""The Holdback Buffer (ADR-0001, ADR-0002).

One instance per request -- never shared across requests, the opposite
of the shared httpx.AsyncClient. Safe-to-flush is governed purely by
position (the last HOLDBACK_WINDOW characters are never released),
never by content -- see ADR-0002 for why a whitespace-based rule was
rejected.
"""

from __future__ import annotations

from .patterns import HOLDBACK_WINDOW, redact


class HoldbackBuffer:
    def __init__(self) -> None:
        self._text = ""

    def append(self, new_text: str, counts: dict[str, int] | None = None) -> str:
        """Add text, redact any now-complete matches, and return whatever
        is now confirmed safe to release. May return "" if nothing new
        is safe yet."""
        self._text = redact(self._text + new_text, counts)
        if len(self._text) <= HOLDBACK_WINDOW:
            return ""
        safe, self._text = self._text[:-HOLDBACK_WINDOW], self._text[-HOLDBACK_WINDOW:]
        return safe

    def flush(self, counts: dict[str, int] | None = None) -> str:
        """Call once, on stream end: one final redact pass, then release
        everything left, regardless of length."""
        remaining = redact(self._text, counts)
        self._text = ""
        return remaining

    @property
    def held_length(self) -> int:
        """How many characters are currently retained, not yet released.

        Exposed read-only so callers (e.g. logging) don't need to reach
        into the underscore-prefixed `_text` to observe buffer state.
        """
        return len(self._text)

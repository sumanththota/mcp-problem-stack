"""Token-aware sliding-window admission, pure logic over the SQLite ledger.

admit() reserves the worst case (prompt + max_tokens) up front; settle()
corrects that reservation down to actual usage once a response completes.
See SPEC.md's Implementation Decisions for why (reserve-then-reconcile,
R1) and the two alternatives that were considered and rejected.
"""

from __future__ import annotations

import sqlite3
import time
import uuid

BUDGET_TOKENS = 50_000
WINDOW_SECONDS = 60


def admit(
    conn: sqlite3.Connection,
    tenant_id: str,
    prompt_tokens: int,
    max_tokens: int,
    *,
    now: float | None = None,
    request_id: str | None = None,
) -> tuple[bool, str | None]:
    """Reserve prompt_tokens + max_tokens against tenant_id's trailing window.

    Returns (True, request_id) if admitted, (False, None) if it would push
    the tenant over budget. The check and the insert happen inside one
    BEGIN IMMEDIATE transaction so two concurrent admits for the same
    tenant can't both read the same sum before either has written.

    request_id lets a caller (the endpoint, for T8) supply its own
    correlation id up front -- including for a rejected admission's error
    response -- instead of only learning one after a reservation exists.
    Defaults to a freshly generated one, as before.
    """
    now = time.time() if now is None else now
    reserve = prompt_tokens + max_tokens
    cutoff = now - WINDOW_SECONDS

    conn.execute("BEGIN IMMEDIATE")
    try:
        current = conn.execute(
            """
            SELECT COALESCE(SUM(tokens), 0) FROM ledger
            WHERE tenant_id = ? AND ts > ? AND status IN ('pending', 'settled')
            """,
            (tenant_id, cutoff),
        ).fetchone()[0]

        if current + reserve > BUDGET_TOKENS:
            conn.rollback()
            return False, None

        request_id = request_id or str(uuid.uuid4())
        conn.execute(
            "INSERT INTO ledger (tenant_id, request_id, ts, tokens, status) VALUES (?, ?, ?, ?, 'pending')",
            (tenant_id, request_id, now, reserve),
        )
        conn.commit()
        return True, request_id
    except Exception:
        conn.rollback()
        raise


def settle(conn: sqlite3.Connection, request_id: str, actual_tokens: int) -> bool:
    """Correct a reservation to actual usage once a response completes.

    Only applies if the row is still 'pending'. If the TTL sweep already
    expired it -- a late-arriving completion for what looked abandoned --
    the settle is dropped instead of silently reviving a reservation whose
    budget may already have been handed to someone else. Returns whether
    the settle actually applied.
    """
    cur = conn.execute(
        "UPDATE ledger SET tokens = ?, status = 'settled' WHERE request_id = ? AND status = 'pending'",
        (actual_tokens, request_id),
    )
    conn.commit()
    return cur.rowcount > 0

"""TTL backstop: force-releases a reservation nobody ever settled.

See SPEC.md's Implementation Decisions (R4, settle+TTL) and the
Reservation Backstops comparison for why this exists and why the TTL is
derived from the system's own call timeouts rather than an invented
constant.

PRIMARY_TIMEOUT_S and SECONDARY_TIMEOUT_S live in router.py -- imported
from there instead of duplicated here, so the two can never drift apart.
MARGIN_S was never confirmed in the design session; a provisional default,
deliberately isolated here so it's easy to change later.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time

from .router import PRIMARY_TIMEOUT_S, SECONDARY_TIMEOUT_S

MARGIN_S = 2.0  # provisional -- not yet confirmed
TTL_SECONDS = PRIMARY_TIMEOUT_S + SECONDARY_TIMEOUT_S + MARGIN_S

SWEEP_INTERVAL_S = 2.0


def sweep(conn: sqlite3.Connection, *, now: float | None = None) -> int:
    """Force-release any reservation still pending past TTL.

    Returns the number of rows expired. Only touches 'pending' rows --
    a 'settled' row is done regardless of age, and eviction from the
    rate-limit window itself is handled separately, by admit()'s own
    timestamp filter.
    """
    now = time.time() if now is None else now
    cutoff = now - TTL_SECONDS
    cur = conn.execute(
        "UPDATE ledger SET tokens = 0, status = 'expired' WHERE status = 'pending' AND ts < ?",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


async def run_sweep_loop(conn: sqlite3.Connection, *, interval: float = SWEEP_INTERVAL_S) -> None:
    """Background task: calls sweep() on a timer, independent of any request."""
    while True:
        await asyncio.sleep(interval)
        sweep(conn)

"""Ticket 9 (concurrency & crash-recovery hardening).

Two properties nothing else in this suite proves under real conditions:

1. Concurrent admission for one tenant never overcommits the budget.
   test_limiter.py only calls admit()/settle() sequentially -- here, real
   OS threads hit the *same on-disk ledger* at once. A ":memory:" db can't
   be shared across connections, so this needs a real temp file: each
   thread opens its own connection, the way separate request-handling
   contexts actually would.

2. An abandoned reservation -- the request handler dies between admit()
   and settle(), the closest a test gets to a real process crash --
   recovers on its own once the *real* background sweep loop has had
   time to run. test_ttl_sweep.py already proves sweep() itself is
   correct; this proves run_sweep_loop() -- the actual production task,
   started from lifespan() -- really does call it autonomously.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import sqlite3
import threading

import pytest

from ratelimit_router import db, limiter, ttl_sweep


def test_concurrent_admits_never_overcommit_the_budget(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    db.connect(db_path).close()  # create the schema once, up front

    reserve_per_request = 2_000
    num_requests = 40  # BUDGET_TOKENS // reserve_per_request == 25 can succeed
    results: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        conn = db.connect(db_path)
        try:
            allowed, _ = limiter.admit(
                conn, "acme", prompt_tokens=1_000, max_tokens=1_000
            )
        finally:
            conn.close()
        with lock:
            results.append(allowed)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as pool:
        list(pool.map(lambda _: worker(), range(num_requests)))

    expected_admitted = limiter.BUDGET_TOKENS // reserve_per_request
    assert sum(results) == expected_admitted

    check_conn = db.connect(db_path)
    total = check_conn.execute(
        "SELECT COALESCE(SUM(tokens), 0) FROM ledger WHERE tenant_id = ? AND status = 'pending'",
        ("acme",),
    ).fetchone()[0]
    check_conn.close()
    assert total == expected_admitted * reserve_per_request
    assert total <= limiter.BUDGET_TOKENS


@pytest.mark.anyio
async def test_abandoned_reservation_recovers_via_the_real_sweep_loop(monkeypatch):
    monkeypatch.setattr(ttl_sweep, "TTL_SECONDS", 0.2)

    conn = sqlite3.connect(":memory:")
    conn.execute(db.SCHEMA)
    conn.execute(db.INDEX)
    conn.commit()

    sweep_task = asyncio.create_task(ttl_sweep.run_sweep_loop(conn, interval=0.05))
    try:
        # Admitted, then the "process" abandons it -- settle() never runs.
        allowed, request_id = limiter.admit(
            conn, "acme", prompt_tokens=100, max_tokens=49_800
        )
        assert allowed is True

        # Before TTL elapses, the tenant is still pinned at budget.
        still_blocked, _ = limiter.admit(
            conn, "acme", prompt_tokens=1_000, max_tokens=1_000
        )
        assert still_blocked is False

        await asyncio.sleep(ttl_sweep.TTL_SECONDS + 0.15)

        # The real background loop -- not a direct sweep() call -- freed it.
        recovered, _ = limiter.admit(
            conn, "acme", prompt_tokens=1_000, max_tokens=1_000
        )
        assert recovered is True

        row = conn.execute(
            "SELECT status FROM ledger WHERE request_id = ?", (request_id,)
        ).fetchone()
        assert row == ("expired",)
    finally:
        sweep_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweep_task
        conn.close()

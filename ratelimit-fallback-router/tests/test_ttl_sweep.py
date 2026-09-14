"""Baseline correctness for sweep() -- mirrors test_limiter.py's approach:
deterministic via an injected `now`, no real waiting.
"""

from __future__ import annotations

import sqlite3

import pytest

from ratelimit_router import db, limiter, ttl_sweep


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(db.SCHEMA)
    c.execute(db.INDEX)
    c.commit()
    return c


def test_sweep_expires_a_stale_pending_reservation(conn):
    old_time = 1_000_000.0
    _, request_id = limiter.admit(conn, "acme", prompt_tokens=100, max_tokens=8_000, now=old_time)
    later = old_time + ttl_sweep.TTL_SECONDS + 1
    expired_count = ttl_sweep.sweep(conn, now=later)
    assert expired_count == 1
    row = conn.execute(
        "SELECT tokens, status FROM ledger WHERE request_id = ?", (request_id,)
    ).fetchone()
    assert row == (0, "expired")


def test_sweep_leaves_a_fresh_pending_reservation_alone(conn):
    now = 1_000_000.0
    _, request_id = limiter.admit(conn, "acme", prompt_tokens=100, max_tokens=8_000, now=now)
    just_before_ttl = now + ttl_sweep.TTL_SECONDS - 1
    expired_count = ttl_sweep.sweep(conn, now=just_before_ttl)
    assert expired_count == 0
    row = conn.execute("SELECT status FROM ledger WHERE request_id = ?", (request_id,)).fetchone()
    assert row == ("pending",)


def test_sweep_never_touches_a_settled_reservation(conn):
    old_time = 1_000_000.0
    _, request_id = limiter.admit(conn, "acme", prompt_tokens=100, max_tokens=8_000, now=old_time)
    limiter.settle(conn, request_id, actual_tokens=150)
    later = old_time + ttl_sweep.TTL_SECONDS + 1
    expired_count = ttl_sweep.sweep(conn, now=later)
    assert expired_count == 0
    row = conn.execute(
        "SELECT tokens, status FROM ledger WHERE request_id = ?", (request_id,)
    ).fetchone()
    assert row == (150, "settled")


def test_expired_reservation_frees_the_budget(conn):
    old_time = 1_000_000.0
    limiter.admit(conn, "acme", prompt_tokens=100, max_tokens=49_800, now=old_time)  # reserves 49,900
    later = old_time + ttl_sweep.TTL_SECONDS + 1
    ttl_sweep.sweep(conn, now=later)
    allowed, _ = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=1_000, now=later)
    assert allowed is True


def test_a_late_settle_cannot_revive_an_already_expired_reservation(conn):
    old_time = 1_000_000.0
    _, request_id = limiter.admit(conn, "acme", prompt_tokens=100, max_tokens=8_000, now=old_time)
    later = old_time + ttl_sweep.TTL_SECONDS + 1
    ttl_sweep.sweep(conn, now=later)  # sweep gives up on it first

    applied = limiter.settle(conn, request_id, actual_tokens=150)  # then the "abandoned" request finishes anyway

    assert applied is False
    row = conn.execute(
        "SELECT tokens, status FROM ledger WHERE request_id = ?", (request_id,)
    ).fetchone()
    assert row == (0, "expired")  # still expired -- the late settle was dropped, not applied

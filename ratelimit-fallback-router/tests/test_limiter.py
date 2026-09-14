"""Baseline correctness for admit()/settle() -- the obvious cases only.

Deliberately not adversarial/exhaustive: which edge cases matter here is a
call worth making explicitly, not baking in silently.
"""

from __future__ import annotations

import sqlite3

import pytest

from ratelimit_router import db, limiter


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(db.SCHEMA)
    c.execute(db.INDEX)
    c.commit()
    return c


def test_admits_when_under_budget(conn):
    allowed, request_id = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=2_000)
    assert allowed is True
    assert request_id is not None


def test_rejects_when_over_budget(conn):
    limiter.admit(conn, "acme", prompt_tokens=40_000, max_tokens=9_000)  # reserves 49,000
    allowed, request_id = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=1_000)  # would be 51,000
    assert allowed is False
    assert request_id is None


def test_settle_corrects_the_reservation(conn):
    allowed, request_id = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=10_000)
    assert allowed
    limiter.settle(conn, request_id, actual_tokens=1_200)
    row = conn.execute(
        "SELECT tokens, status FROM ledger WHERE request_id = ?", (request_id,)
    ).fetchone()
    assert row == (1_200, "settled")


def test_settlement_frees_budget_for_the_next_request(conn):
    _, request_id = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=48_000)  # reserves 49,000
    limiter.settle(conn, request_id, actual_tokens=2_000)  # releases 47,000 back
    allowed, _ = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=1_000)
    assert allowed is True


def test_tenants_are_isolated(conn):
    limiter.admit(conn, "acme", prompt_tokens=49_000, max_tokens=0)
    allowed, _ = limiter.admit(conn, "globex", prompt_tokens=1_000, max_tokens=1_000)
    assert allowed is True


def test_old_reservations_age_out_of_the_window(conn):
    old_time = 1_000_000.0
    limiter.admit(conn, "acme", prompt_tokens=49_000, max_tokens=0, now=old_time)
    later = old_time + limiter.WINDOW_SECONDS + 1
    allowed, _ = limiter.admit(conn, "acme", prompt_tokens=1_000, max_tokens=1_000, now=later)
    assert allowed is True

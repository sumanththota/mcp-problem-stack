"""SQLite ledger: the one table every admission/settlement decision reads and writes.

See SPEC.md and the Router Blueprint for why this table has exactly this
shape -- one row per reservation, corrected in place once real usage is
known, with window eviction handled entirely by a timestamp filter at read
time rather than an explicit delete.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    tenant_id  TEXT    NOT NULL,
    request_id TEXT    NOT NULL PRIMARY KEY,
    ts         REAL    NOT NULL,
    tokens     INTEGER NOT NULL,
    status     TEXT    NOT NULL
);
"""

INDEX = """
CREATE INDEX IF NOT EXISTS idx_ledger_tenant_ts ON ledger (tenant_id, ts);
"""


def connect(path: str = "ledger.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(SCHEMA)
    conn.execute(INDEX)
    conn.commit()
    return conn

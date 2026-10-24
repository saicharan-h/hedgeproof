"""SQLite store for trusted state. Owner: Lohith (gate, simulator, dashboard).

Only the trusted service writes here. Rules enforced by the database itself:

* ``events`` and ``artifacts`` are append-only (triggers reject UPDATE/DELETE).
* ``orders.idempotency_key`` and ``orders.intent_hash`` are unique, so a second
  order for the same intent cannot be inserted; approvals are unique per
  (intent hash, ledger version).
* Candidate ordinals are limited to 1..6 per lineage and repairs to 0..2.
* ``holdout_lock`` has one row per lineage; consuming it is a conditional update
  inside one transaction, so it can only happen once and survives restarts.

A local SQLite file helps detect changes; it is not tamper-proof or certified.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from hedgeproof.records import Record, canonical_json, hash_value, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    lineage_id TEXT,
    sha256 TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS artifacts_no_update BEFORE UPDATE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS artifacts_no_delete BEFORE DELETE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    lineage_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 6),
    repair_count INTEGER NOT NULL DEFAULT 0 CHECK (repair_count BETWEEN 0 AND 2),
    revision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (lineage_id, ordinal)
);

CREATE TABLE IF NOT EXISTS holdout_lock (
    lineage_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('sealed', 'consumed')),
    consumed_at TEXT,
    report_id TEXT
);

CREATE TABLE IF NOT EXISTS intents (
    intent_hash TEXT PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    intent_hash TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    ledger_version INTEGER NOT NULL,
    approver TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    replay_date TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0, 1)),
    body TEXT NOT NULL,
    UNIQUE (intent_hash, ledger_version)
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    intent_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ACCEPTED', 'FILLED', 'REJECTED', 'UNKNOWN')),
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    delivery_month TEXT PRIMARY KEY,
    contracts INTEGER NOT NULL CHECK (contracts >= 0),
    opened_hedge_month TEXT,
    entry_price REAL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    refs TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('ledger_version', '0')")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One write transaction (serialized; BEGIN IMMEDIATE takes the write lock)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, args))

    # --- meta -----------------------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        rows = self.query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_meta(self, key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
        sql = "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        if conn is not None:
            conn.execute(sql, (key, value))
        else:
            with self.tx() as c:
                c.execute(sql, (key, value))

    def ledger_version(self) -> int:
        return int(self.get_meta("ledger_version", "0") or 0)

    # --- events ---------------------------------------------------------------

    def log(self, actor: str, kind: str, refs: list[str] | None = None, payload: dict[str, Any] | None = None,
            conn: sqlite3.Connection | None = None) -> int:
        payload = payload or {}
        args = (utc_now(), actor, kind, json.dumps(refs or []), canonical_json(payload).decode("utf-8"), hash_value(payload))
        sql = "INSERT INTO events (ts, actor, kind, refs, payload, payload_sha256) VALUES (?, ?, ?, ?, ?, ?)"
        if conn is not None:
            return int(conn.execute(sql, args).lastrowid)
        with self.tx() as c:
            return int(c.execute(sql, args).lastrowid)

    def events(self, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (after, limit))
        return [
            {"seq": r["seq"], "ts": r["ts"], "actor": r["actor"], "kind": r["kind"], "refs": json.loads(r["refs"]),
             "payload": json.loads(r["payload"]), "payload_sha256": r["payload_sha256"]}
            for r in rows
        ]

    # --- artifacts (evidence registry) ------------------------------------------

    def put(self, record: Record, lineage_id: str | None = None, conn: sqlite3.Connection | None = None) -> str:
        if not record.sha256:
            record.seal()
        body = canonical_json(record.model_dump(mode="json")).decode("utf-8")
        args = (record.id, type(record).__name__, lineage_id, record.sha256, body, record.created_at)
        sql = "INSERT INTO artifacts (id, kind, lineage_id, sha256, body, created_at) VALUES (?, ?, ?, ?, ?, ?)"
        if conn is not None:
            conn.execute(sql, args)
        else:
            with self.tx() as c:
                c.execute(sql, args)
        return record.id

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        rows = self.query("SELECT body FROM artifacts WHERE id = ?", (artifact_id,))
        return json.loads(rows[0]["body"]) if rows else None

    def artifact_row(self, artifact_id: str) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        return rows[0] if rows else None

    def recompute_hash(self, artifact_id: str) -> str | None:
        """Recompute an artifact's hash from its stored body (excluding the sha256 field)."""
        body = self.get(artifact_id)
        if body is None:
            return None
        body = dict(body)
        body.pop("sha256", None)
        return hash_value(body)

    def list_artifacts(self, kind: str | None = None, lineage_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT body FROM artifacts WHERE 1=1", []
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        if lineage_id:
            sql += " AND lineage_id = ?"
            args.append(lineage_id)
        sql += " ORDER BY created_at, rowid"
        return [json.loads(r["body"]) for r in self.query(sql, tuple(args))]

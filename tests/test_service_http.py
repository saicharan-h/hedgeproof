"""HTTP boundary tests for the trusted service (SYNTHETIC data, temporary database)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from hedgeproof.evals.cases import CODE, Env
from hedgeproof.trusted.service import create_app


def _client(tmp: Path) -> tuple[TestClient, Env]:
    env = Env(tmp)
    return TestClient(create_app(env.core)), env


def test_health_reports_policy_and_sealed_holdout():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, env = _client(Path(d))
        h = c.get("/health").json()
        assert h["policy_sha256"] == env.settings.policy.sha256
        assert h["holdout_state"] == "sealed"
        assert h["mode"] == "test"


def test_approval_requires_operator_code_and_agent_cannot_self_approve():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, env = _client(Path(d))
        pkt = env.packet()
        t = env.terms(pkt, 5)
        r = c.post("/intents", json={"terms": t.model_dump(mode="json"), "requested_by": "risk"}).json()
        ih = r["intent"]["intent_hash"]
        no_code = c.post("/approvals", json={"intent_hash": ih, "approver": "agent"})
        assert no_code.status_code == 403 and no_code.json()["code"] == "APPROVAL_TOKEN_INVALID"
        wrong = c.post("/approvals", json={"intent_hash": ih, "approver": "agent"}, headers={"X-Operator-Code": "BAD000"})
        assert wrong.status_code == 403
        assert env.core.store.query("SELECT id FROM approvals") == []
        blocked = c.post("/orders", json={"intent_hash": ih, "idempotency_key": "http-key-0001"})
        assert blocked.status_code == 409 and "APPROVAL_MISSING_OR_STALE" in blocked.json()["reasons"]
        ok = c.post("/approvals", json={"intent_hash": ih, "approver": "Saicharan"}, headers={"X-Operator-Code": CODE})
        assert ok.status_code == 200


def test_ack_timeout_returns_504_then_status_query_reconciles():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, env = _client(Path(d))
        t = env.terms(env.packet(), 5)
        ih = c.post("/intents", json={"terms": t.model_dump(mode="json"), "requested_by": "risk"}).json()["intent"]["intent_hash"]
        c.post("/approvals", json={"intent_hash": ih, "approver": "Saicharan"}, headers={"X-Operator-Code": CODE})
        assert c.post("/simulator/arm-ack-timeout").status_code == 403  # human-only control
        c.post("/simulator/arm-ack-timeout", headers={"X-Operator-Code": CODE})
        r = c.post("/orders", json={"intent_hash": ih, "idempotency_key": "http-key-0002"})
        assert r.status_code == 504 and r.json()["code"] == "ACK_TIMEOUT"
        status = c.get("/orders/http-key-0002").json()
        assert status["status"] == "FILLED"
        again = c.post("/orders", json={"intent_hash": ih, "idempotency_key": "http-key-0002"}).json()
        assert again["replayed"] is True
        assert len(c.get("/ledger").json()["orders"]) == 1


def test_validation_rows_are_withheld_and_holdout_split_refused():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, env = _client(Path(d))
        r = c.post("/backtests", json={"lineage_id": "TEST-HTTP", "split": "validation", "template": "ols36"}).json()
        assert r["rows"] == [] and r["metrics"]["adaptive"]["n_positions"] == 23
        art = c.get(f"/artifacts/{r['id']}").json()
        assert art["rows"] == [] and art["hash_recomputes"] is True
        h = c.post("/backtests", json={"lineage_id": "TEST-HTTP", "split": "holdout", "template": "ols36"})
        assert h.status_code == 403 and h.json()["code"] == "SPLIT_NOT_ALLOWED"
        f = c.get("/data/window", params={"as_of": "2020-06-01", "window": 36})
        assert f.status_code == 403 and f.json()["code"] == "SEALED_PERIOD"


def test_operator_code_locks_after_repeated_failures():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, env = _client(Path(d))
        for _ in range(10):
            c.post("/simulator/arm-ack-timeout", headers={"X-Operator-Code": "NOPE00"})
        r = c.post("/simulator/arm-ack-timeout", headers={"X-Operator-Code": CODE})
        assert r.status_code == 403 and r.json()["code"] == "OPERATOR_CODE_LOCKED"


def test_events_and_artifacts_are_append_only():
    import sqlite3

    import pytest

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        _, env = _client(Path(d))
        env.packet()
        with pytest.raises(sqlite3.DatabaseError):
            with env.core.store.tx() as conn:
                conn.execute("UPDATE events SET kind = 'x'")
        with pytest.raises(sqlite3.DatabaseError):
            with env.core.store.tx() as conn:
                conn.execute("DELETE FROM artifacts")

"""HTTP boundary tests for the Indian scenario trusted service (SYNTHETIC-INDIA data)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from hedgeproof.cli import build_core
from hedgeproof.evals.cases import CODE, Env


def _client(tmp: Path) -> tuple[TestClient, object]:
    core = build_core("test", synthetic=True, scenario="india", db=str(tmp / "india.db"))
    return TestClient(__import__("hedgeproof.trusted.service", fromlist=["create_app"]).create_app(core)), core


def test_india_health_reports_policy_and_sealed_holdout():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, core = _client(Path(d))
        h = c.get("/health").json()
        assert h["policy_sha256"] == core.settings.policy.sha256
        assert h["holdout_state"] == "sealed"
        assert h["mode"] == "test"
        assert h["data_label"] == "SYNTHETIC-INDIA TEST FIXTURE"


def test_india_policy_currency_and_contract():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, core = _client(Path(d))
        p = c.get("/policy").json()
        assert p["policy"]["currency"] == "INR"
        assert p["forecast_gallons"] == 1500000
        assert p["n_cap"] == 75
        assert p["agency"]["currency_symbol"] == "₹"


def test_india_splits_counts():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, core = _client(Path(d))
        s = c.get("/splits").json()
        assert s["counts"].get("development") == 10
        assert s["counts"].get("validation") == 23
        assert s["counts"].get("holdout") == 49


def test_india_backtest_validation_withheld():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        c, core = _client(Path(d))
        r = c.post("/backtests", json={"lineage_id": "TEST-INDIA-HTTP", "split": "validation", "template": "ols36"}).json()
        assert r["rows"] == [] and r["metrics"]["adaptive"]["n_positions"] == 23
        h = c.post("/backtests", json={"lineage_id": "TEST-INDIA-HTTP", "split": "holdout", "template": "ols36"})
        assert h.status_code == 403 and h.json()["code"] == "SPLIT_NOT_ALLOWED"
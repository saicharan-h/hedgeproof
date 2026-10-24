"""HTTP boundary tests for the Indian scenario trusted service (SYNTHETIC-INDIA data)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from hedgeproof.cli import build_core
from hedgeproof.trusted.service import create_app


def _client(tmp: Path):
    core = build_core("test", synthetic=True, scenario="india", db=str(tmp / "india.db"), operator_code="TEST01")
    return TestClient(create_app(core)), core


def test_india_health_reports_policy_and_sealed_holdout():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        c, core = _client(tmp)
        try:
            h = c.get("/health").json()
            assert h["data_label"] == "SYNTHETIC-INDIA TEST FIXTURE"
            assert h["holdout_state"] == "sealed"
            assert h["mode"] == "test"
        finally:
            core.close()


def test_india_policy_currency_and_contract():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        c, core = _client(tmp)
        try:
            p = c.get("/policy").json()
            assert p["policy"]["currency"] == "INR"
            assert p["forecast_gallons"] == 1500000
            assert p["n_cap"] == 75
            assert p["agency"]["currency_symbol"] == "₹"
        finally:
            core.close()


def test_india_splits_counts():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        c, core = _client(tmp)
        try:
            s = c.get("/splits").json()
            assert s["counts"].get("development") == 10
            assert s["counts"].get("validation") == 23
            assert s["counts"].get("holdout") == 49
        finally:
            core.close()


def test_india_backtest_validation_withheld():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        c, core = _client(tmp)
        try:
            r = c.post("/backtests", json={"lineage_id": "TEST-INDIA-HTTP", "split": "validation", "template": "ols36"}).json()
            assert r["rows"] == [] and r["metrics"]["adaptive"]["n_positions"] == 23
            h = c.post("/backtests", json={"lineage_id": "TEST-INDIA-HTTP", "split": "holdout", "template": "ols36"})
            assert h.status_code == 403 and h.json()["code"] == "SPLIT_NOT_ALLOWED"
        finally:
            core.close()
"""Indian scenario: a compact set of deterministic cases mirroring the U.S. suite.

SYNTHETIC-INDIA data, temporary databases, TEST lineages, no model calls.
The full 16-case suite is U.S.-specific; these cases exercise the same gate
rules on the Indian scenario (MCX crude proxy, INR, litres).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hedgeproof.cli import build_core
from hedgeproof.evals.cases import CODE
from hedgeproof.trusted.core import TrustedCore, TrustedError
from hedgeproof.trusted.service import create_app
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
CFG_INDIA = REPO / "config" / "india"


def _core(tmp: Path) -> TrustedCore:
    return build_core("test", synthetic=True, scenario="india", db=str(tmp / "india_case.db"), operator_code=CODE)


def _client(tmp: Path) -> TestClient:
    return TestClient(create_app(_core(tmp)))


# --- I1: compliant open ------------------------------------------------------

def test_i1_compliant_open():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        # build evidence
        core.run_backtest("TEST-I1", "development", template="ols36", actor="trusted")
        pkt = core.build_evidence_packet("TEST-I1", "RUN-I1")
        rd = core.settings.replay_date
        from hedgeproof.data import add_months
        from hedgeproof.records import IntentTerms
        terms = IntentTerms(
            evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"],
            replay_date=rd, hedge_month=rd[:7], side="BUY_OPEN", instrument="MCX-CRUDE",
            delivery_month=add_months(rd[:7], 2), contracts=5,
            forecast_gallons=core.settings.forecast_gallons, policy_sha256=core.settings.policy.sha256,
        )
        r = core.register_intent(terms, "test")
        assert "APPROVAL_MISSING_OR_STALE" in [o["reason_code"] for o in r["gate"]["outcomes"] if not o["passed"]]
        core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
        res = core.submit_order(r["intent"]["intent_hash"], "i1-key-0001")
        assert res["order"]["status"] == "FILLED"
        assert res["order"]["contracts"] == 5


# --- I2: oversizing blocked --------------------------------------------------

def test_i2_oversizing_blocked():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        core.run_backtest("TEST-I2", "development", template="ols36", actor="trusted")
        pkt = core.build_evidence_packet("TEST-I2", "RUN-I2")
        rd = core.settings.replay_date
        from hedgeproof.data import add_months
        from hedgeproof.records import IntentTerms
        terms = IntentTerms(
            evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"],
            replay_date=rd, hedge_month=rd[:7], side="BUY_OPEN", instrument="MCX-CRUDE",
            delivery_month=add_months(rd[:7], 2), contracts=100,
            forecast_gallons=core.settings.forecast_gallons, policy_sha256=core.settings.policy.sha256,
        )
        r = core.register_intent(terms, "test")
        assert r["gate"]["verdict"] == "BLOCKED"
        assert "EXPOSURE_CAP" in [o["reason_code"] for o in r["gate"]["outcomes"] if not o["passed"]]
        assert len(core.store.query("SELECT id FROM orders")) == 0


# --- I3: net short blocked ---------------------------------------------------

def test_i3_net_short_blocked():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        core.run_backtest("TEST-I3", "development", template="ols36", actor="trusted")
        pkt = core.build_evidence_packet("TEST-I3", "RUN-I3")
        rd = core.settings.replay_date
        from hedgeproof.data import add_months
        from hedgeproof.records import IntentTerms
        terms = IntentTerms(
            evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"],
            replay_date=rd, hedge_month=rd[:7], side="BUY_OPEN", instrument="MCX-CRUDE",
            delivery_month=add_months(rd[:7], 2), contracts=5,
            forecast_gallons=core.settings.forecast_gallons, policy_sha256=core.settings.policy.sha256,
        )
        r = core.register_intent(terms, "test")
        core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
        core.submit_order(r["intent"]["intent_hash"], "i3-open-0001")
        # now a SELL_CLOSE that would make position negative
        pkt2 = core.build_evidence_packet("TEST-I3", "RUN-I3b") if False else pkt
        terms2 = IntentTerms(
            evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"],
            replay_date=rd, hedge_month=rd[:7], side="SELL_CLOSE", instrument="MCX-CRUDE",
            delivery_month=add_months(rd[:7], 2), contracts=10,
            forecast_gallons=core.settings.forecast_gallons, policy_sha256=core.settings.policy.sha256,
        )
        r2 = core.register_intent(terms2, "test")
        assert r2["gate"]["verdict"] == "BLOCKED"
        assert "NET_SHORT" in [o["reason_code"] for o in r2["gate"]["outcomes"] if not o["passed"]]


# --- I4: currency and units present -----------------------------------------

def test_i4_policy_currency_inr():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        assert core.settings.policy.currency == "INR"
        assert core.settings.policy.contract_size == 15000
        assert core.settings.forecast_gallons == 1500000


# --- I5: holdout sealed ------------------------------------------------------

def test_i5_holdout_sealed():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        assert core.health()["holdout_state"] == "sealed"


# --- I6: approval requires operator code -------------------------------------

def test_i6_approval_requires_code():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        c = _client(tmp)
        core = _core(tmp) if False else None
        # use a fresh core via client's env is not exposed; rebuild
    # simpler: direct core
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        core = _core(tmp)
        core.run_backtest("TEST-I6", "development", template="ols36", actor="trusted")
        pkt = core.build_evidence_packet("TEST-I6", "RUN-I6")
        rd = core.settings.replay_date
        from hedgeproof.data import add_months
        from hedgeproof.records import IntentTerms
        terms = IntentTerms(
            evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"],
            replay_date=rd, hedge_month=rd[:7], side="BUY_OPEN", instrument="MCX-CRUDE",
            delivery_month=add_months(rd[:7], 2), contracts=5,
            forecast_gallons=core.settings.forecast_gallons, policy_sha256=core.settings.policy.sha256,
        )
        r = core.register_intent(terms, "test")
        ih = r["intent"]["intent_hash"]
        with pytest.raises(TrustedError):
            core.approve(ih, "agent", "BADCODE")
        assert core.store.query("SELECT id FROM approvals") == []


# --- I7: http health ---------------------------------------------------------

def test_i7_http_health():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        c = _client(tmp)
        h = c.get("/health").json()
        assert h["data_label"] == "SYNTHETIC-INDIA TEST FIXTURE"
        assert h["mode"] == "test"


# --- I8: http splits ---------------------------------------------------------

def test_i8_http_splits():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        c = _client(tmp)
        s = c.get("/splits").json()
        assert s["counts"].get("development") == 10
        assert s["counts"].get("validation") == 23
        assert s["counts"].get("holdout") == 49
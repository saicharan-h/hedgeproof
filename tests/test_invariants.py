"""Financial invariants (interface contract section 10.2), on SYNTHETIC data.

Invariant 6 (holdout lock survives restart) lives in tests/test_trusted.py and
invariant 9 (repository hygiene) in tests/test_hygiene.py.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from hedgeproof import engine
from hedgeproof.data import add_months, build_period_table, table_records, training_window


def _split_rows(table, split):
    return [r for r in table_records(table) if r["split"] == split and r["status"] == "ok"]


def _ols_estimates(table, rows, window=36):
    return {r["hedge_month"]: engine.ols_hedge_ratio(training_window(table, r["hedge_month"], window)) for r in rows}


def test_1_hedge_pnl_sign(settings):
    """With dF > 0 and n > 0, net cost is lower than unhedged by exactly 42,000 * n * dF."""
    row = {"S_budget": 2.0, "S_exit": 2.3, "dS": 0.3, "dF": 0.25, "F_ref": 2.1}
    q, cpc = settings.forecast_gallons, 0.0
    unhedged = engine.position_cashflows(row, 0, q, cpc, settings.policy)
    hedged = engine.position_cashflows(row, 5, q, cpc, settings.policy)
    assert hedged["net_cost"] < unhedged["net_cost"]
    assert unhedged["net_cost"] - hedged["net_cost"] == pytest.approx(42_000 * 5 * 0.25, abs=1e-9)


def test_2_contract_identity(table):
    """Entry and exit legs are the same delivery month, which is hedge month + 2."""
    for r in table_records(table):
        assert r["delivery_month"] == r["exit_delivery_month"] == add_months(r["hedge_month"], 2)


def test_3_integer_cap(settings, table):
    policy, q = settings.policy, settings.forecast_gallons
    assert policy.n_cap(q) == 7
    assert engine.size_position(0.5, q, 2.0, policy).n == 5
    assert engine.size_position(1.5, q, 2.0, policy).n == 7  # strategy path never exceeds the cap
    # Every adaptive decision in the backtest respects the cap.
    rows = _split_rows(table, "validation")
    est = {hm: 2.0 for hm in (r["hedge_month"] for r in rows)}  # the most aggressive plausible estimate
    bt = engine.backtest(rows, est, settings, with_bootstrap=False)
    assert max(r["n"] for r in bt["rows"]["adaptive"]) <= 7
    assert bt["metrics"]["adaptive"]["policy_breaches"] == 0


def test_cash_cap_examples(settings):
    """Fixture sizing examples from the contract: ~6 contracts at $3.50 and 5 at $4.00."""
    assert engine.n_cash_limit(settings.policy, 3.50) == 6
    assert engine.n_cash_limit(settings.policy, 4.00) == 5


def test_4_future_perturbation(settings, market):
    """Multiplying all data after X by 1.5 leaves decisions and cash flows before X unchanged."""
    cutoff = pd.Timestamp("2018-06-15")
    base = build_period_table(market, settings.experiment)
    shocked = build_period_table(market.scaled_after(cutoff, 1.5), settings.experiment)
    closed_before = [r for r in table_records(base) if pd.Timestamp(r["exit_date"]) <= cutoff and r["status"] == "ok"]
    shocked_by_month = {r["hedge_month"]: r for r in table_records(shocked)}
    for r in closed_before:
        s = shocked_by_month[r["hedge_month"]]
        for k in ("S_budget", "S_exit", "F_entry", "F_exit", "F_ref", "dS", "dF"):
            assert s[k] == r[k], (r["hedge_month"], k)
    # Decisions (estimates) for positions closed before X are unchanged too.
    dev_val = [r for r in closed_before if r["split"] in ("development", "validation")]
    assert dev_val, "need positions before the cutoff"
    assert _ols_estimates(base, dev_val) == _ols_estimates(shocked, dev_val)


def test_5_recomputation_reproduces_metrics(settings, table):
    rows = _split_rows(table, "development")
    est = _ols_estimates(table, rows)
    a = engine.backtest(rows, est, settings)
    b = engine.backtest(rows, est, settings)
    assert a["metrics"] == b["metrics"]
    assert a["bootstrap"] == b["bootstrap"]
    # Recompute adaptive metrics directly from the stored per-position cash flows.
    stored = a["rows"]["adaptive"]
    again = engine.strategy_metrics(stored, settings.forecast_gallons, settings.policy)
    assert again == a["metrics"]["adaptive"]


def test_7_accounting_identity(settings, table):
    rows = _split_rows(table, "validation")
    est = _ols_estimates(table, rows)
    bt = engine.backtest(rows, est, settings, with_bootstrap=False)
    q = settings.forecast_gallons
    by_month = {r["hedge_month"]: r for r in rows}
    for s in engine.STRATEGIES:
        for r in bt["rows"][s]:
            src = by_month[r["hedge_month"]]
            expected = q * src["dS"] - 42_000 * r["n"] * src["dF"] + r["n"] * settings.cost_per_contract
            assert math.isclose(r["error"], expected, rel_tol=0, abs_tol=1e-6)


def test_8_training_purge(table):
    """The window for decision p never contains position p - 1 or later."""
    for r in table_records(table):
        if r["split"] not in ("development", "validation", "holdout"):
            continue
        w = training_window(table, r["hedge_month"], 24)
        assert max(x["hedge_month"] for x in w) <= add_months(r["hedge_month"], -2)


def test_split_counts(table):
    counts = table["split"].value_counts().to_dict()
    assert counts["development"] == 10
    assert counts["validation"] == 23
    assert counts["holdout"] == 49
    purged = sorted(table[table["split"] == "purged"]["hedge_month"])
    assert purged == ["2017-12", "2019-12", "2020-01", "2024-03"]


def test_holiday_and_session_rules(market):
    sessions = market.sessions
    assert all(s.weekday() < 5 for s in sessions)
    i = sessions.index(pd.Timestamp("2024-04-01"))
    assert sessions[i - 1] == pd.Timestamp("2024-03-28")  # Good Friday absent


def test_missing_exit_spot_rejected_not_interpolated(settings):
    from hedgeproof.synthetic import synthetic_market

    md = synthetic_market(drop_spot=("2018-03-01",))
    t = build_period_table(md, settings.experiment)
    row = t[t["hedge_month"] == "2018-02"].iloc[0]
    assert row["status"].startswith("rejected: missing exit spot")
    assert row["dS"] is None or (isinstance(row["dS"], float) and math.isnan(row["dS"]))


def test_zero_variance_window_rejected():
    from hedgeproof.data import WindowError

    flat = pd.DataFrame(
        [
            {"hedge_month": f"2015-{m:02d}", "entry_date": "", "exit_date": "", "S_budget": 2.0, "S_exit": 2.0,
             "F_entry": 2.0, "F_exit": 2.0, "dS": 0.0, "dF": 0.0, "status": "ok"}
            for m in range(1, 13)
        ]
    )
    with pytest.raises(WindowError):
        training_window(flat, "2016-03", 12)


def test_bootstrap_is_paired_and_seeded(settings, table):
    rows = _split_rows(table, "validation")
    est = _ols_estimates(table, rows)
    bt = engine.backtest(rows, est, settings)
    boot = bt["bootstrap"]
    assert boot["available"] and boot["resamples"] == 2000 and boot["seed"] == 20261024
    lo, hi = boot["intervals"]["dvar_vs_unhedged"]
    assert lo <= hi


def test_implausible_estimate_rejected(settings, table):
    rows = _split_rows(table, "development")
    with pytest.raises(ValueError, match="implausible"):
        engine.backtest(rows, {r["hedge_month"]: 3.0 for r in rows}, settings)


def test_vetted_sources_match_templates(table):
    """The sandbox source text of the vetted OLS template equals the in-process template."""
    ns: dict = {}
    exec(engine.VETTED_SOURCES["ols"], ns)  # trusted template text, not generated code
    w = training_window(table, "2017-05", 36)
    assert ns["estimate"](w, {}) == pytest.approx(engine.ols_hedge_ratio(w), abs=1e-12)
    np.testing.assert_allclose(engine.ols_hedge_ratio(w), engine.ols_hedge_ratio(list(w)))

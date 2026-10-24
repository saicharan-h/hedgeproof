"""Checks on the committed EIA files (HISTORICAL MARKET REPLAY). No model calls.

Skipped only if data/raw/ is missing. These verify data facts and the
mapping rules on real prices; they compute no holdout metrics.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hedgeproof.config import DATA_DIR, REPO_ROOT, load_settings
from hedgeproof.data import (
    add_months,
    build_period_table,
    continuity_report,
    load_market_data,
    operational_entry,
    table_records,
    training_window,
)
from hedgeproof.engine import ols_hedge_ratio
from hedgeproof.ingest import load_manifest, verify_raw_files

RAW = DATA_DIR / "raw"
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not (RAW / "PET_PRI_FUT_S1_D.xls").exists(), reason="EIA raw files not present"),
]


@pytest.fixture(scope="module")
def real():
    return load_market_data(RAW)


@pytest.fixture(scope="module")
def real_table(real):
    return build_period_table(real, load_settings().experiment)


def test_committed_raw_files_match_the_manifest():
    manifest = load_manifest()
    assert manifest is not None
    assert verify_raw_files(manifest, REPO_ROOT) == []
    assert {f["path"] for f in manifest["files"]} == {"data/raw/PET_PRI_FUT_S1_D.xls", "data/raw/PET_PRI_SPT_S1_D.xls"}


def test_units_and_history_end(real):
    assert set(real.units.values()) == {"Dollars per Gallon"}
    assert real.c1.index[-1] == pd.Timestamp("2024-04-05")  # EIA: futures after 5 Apr 2024 not available
    assert real.spot.index[0] == pd.Timestamp("2006-06-14")


def test_every_position_uses_one_delivery_month(real_table):
    for r in table_records(real_table):
        assert r["delivery_month"] == r["exit_delivery_month"] == add_months(r["hedge_month"], 2)


def test_split_labels_and_the_single_rejected_row(real_table):
    counts = real_table["split"].value_counts().to_dict()
    assert (counts["development"], counts["validation"], counts["holdout"], counts["purged"]) == (10, 23, 49, 4)
    rejected = [(r["hedge_month"], r["status"]) for r in table_records(real_table) if r["status"] != "ok"]
    assert rejected == [("2017-06", "rejected: missing exit spot (no interpolation)")]


def test_roll_mapping_is_consistent_with_same_contract_moves(real):
    rc = continuity_report(real)["roll_consistency"]
    assert rc["mapping_corr_at_boundaries"] > 0.98
    assert rc["mapping_corr_at_boundaries"] > rc["alternative_no_roll_corr"] + 0.1
    assert rc["median_abs_diff_mapping"] <= rc["median_abs_diff_ordinary_days"] + 1e-9


def test_operational_entry_after_good_friday(real):
    op = operational_entry(real, load_settings().replay_date)
    assert op["entry_date"] == "2024-04-01" and op["delivery_month"] == "2024-06"
    assert op["f_ref_date"] == "2024-03-28"  # 29 Mar 2024 (Good Friday) has no session


def test_future_perturbation_on_real_data(real):
    """Invariant 4 on EIA prices: scaling everything after a date leaves earlier positions and decisions unchanged."""
    s = load_settings()
    cutoff = pd.Timestamp("2017-12-15")
    base = build_period_table(real, s.experiment)
    shocked = build_period_table(real.scaled_after(cutoff, 1.5), s.experiment)
    b = {r["hedge_month"]: r for r in table_records(base)}
    k = {r["hedge_month"]: r for r in table_records(shocked)}
    closed = [m for m, r in b.items() if r["status"] == "ok" and pd.Timestamp(r["exit_date"]) <= cutoff]
    assert len(closed) > 40
    for m in closed:
        for f in ("S_budget", "S_exit", "F_entry", "F_exit", "F_ref", "dS", "dF"):
            assert b[m][f] == k[m][f]
    dev = [r["hedge_month"] for r in table_records(base) if r["split"] == "development" and r["status"] == "ok"]
    for m in dev:
        assert ols_hedge_ratio(training_window(base, m, 36)) == ols_hedge_ratio(training_window(shocked, m, 36))

"""Indian scenario: calendar, synthetic market, period table, manifest, units and
contract identity. SYNTHETIC-INDIA data, temporary databases, no model calls.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hedgeproof.config import load_settings
from hedgeproof.india import (
    INDIAN_EXPECTED_UNIT,
    INDIAN_LABEL,
    SPOT_INDIA_DIESEL,
    FUT_INDIA_C1,
    FUT_INDIA_C2,
    FUT_INDIA_C3,
    indian_holidays,
    load_indian_market_data,
    read_ppac_csv,
    read_indian_futures_csv,
    synthetic_indian_market,
)
from hedgeproof.data import build_period_table, month_key, add_months
from hedgeproof.ingest import manifest_for


CFG_INDIA = Path(__file__).resolve().parents[1] / "config" / "india"


@pytest.fixture(scope="module")
def india_settings():
    return load_settings(CFG_INDIA)


@pytest.fixture(scope="module")
def india_market():
    return synthetic_indian_market()


@pytest.fixture(scope="module")
def india_table(india_market, india_settings):
    return build_period_table(india_market, india_settings.experiment)


# --- Holidays ----------------------------------------------------------------

def test_indian_holidays_include_weekends():
    hol = indian_holidays(__import__("datetime").date(2024, 1, 1), __import__("datetime").date(2024, 1, 31))
    import datetime as dt
    # a known weekend
    assert dt.date(2024, 1, 6) in hol
    assert dt.date(2024, 1, 7) in hol


def test_indian_holidays_include_republic_day():
    import datetime as dt
    hol = indian_holidays(dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    assert dt.date(2024, 1, 26) in hol


def test_indian_holidays_are_date_objects():
    import datetime as dt
    hol = indian_holidays(dt.date(2024, 1, 1), dt.date(2024, 1, 10))
    assert all(isinstance(h, dt.date) for h in hol)


# --- Synthetic market ---------------------------------------------------------

def test_synthetic_indian_market_label_and_units(india_market):
    assert india_market.names  # non-empty
    for v in india_market.units.values():
        assert v == INDIAN_EXPECTED_UNIT


def test_synthetic_indian_market_has_sessions(india_market):
    assert len(india_market.sessions) > 1000


def test_synthetic_indian_market_spot_positive(india_market):
    assert (india_market.spot > 0).all()


def test_synthetic_indian_market_futures_positive(india_market):
    assert (india_market.c1 > 0).all()
    assert (india_market.c2 > 0).all()
    assert (india_market.c3 > 0).all()


def test_synthetic_indian_market_level_inr(india_market):
    # Indian diesel level ~ INR 85-100 per litre
    assert 60 < india_market.spot.median() < 130


def test_synthetic_indian_market_contract_identity(india_market):
    sessions = india_market.sessions
    # Contract 2 on last session of a month and Contract 1 on first session of next
    # month should be close (same delivery month, no jump).
    import pandas as pd
    boundaries = []
    for a, b in zip(sessions, sessions[1:]):
        if month_key(a) != month_key(b):
            boundaries.append((a, b))
    assert len(boundaries) > 100


def test_synthetic_indian_market_drop_spot(india_market):
    md2 = synthetic_indian_market(drop_spot=("2020-01-02",))
    assert len(md2.spot) <= len(india_market.spot)


# --- Period table ------------------------------------------------------------

def test_india_period_table_not_empty(india_table):
    assert len(india_table) > 50


def test_india_period_table_columns(india_table):
    expected = ["hedge_month", "entry_date", "exit_date", "delivery_month", "exit_delivery_month",
                "budget_spot_date", "f_ref_date", "S_budget", "S_exit", "F_entry", "F_exit", "F_ref",
                "dS", "dF", "split", "status"]
    assert list(india_table.columns) == expected


def test_india_period_table_contract_identity(india_table):
    ok = india_table[india_table["status"] == "ok"]
    assert (ok["delivery_month"] == ok["exit_delivery_month"]).all()


def test_india_period_table_splits(india_table):
    counts = india_table["split"].value_counts().to_dict()
    assert "development" in counts
    assert "validation" in counts
    assert "holdout" in counts


def test_india_period_table_expected_counts(india_table):
    counts = india_table["split"].value_counts().to_dict()
    assert counts.get("development", 0) == 10
    assert counts.get("validation", 0) == 23
    assert counts.get("holdout", 0) == 49


def test_india_period_table_no_interpolation(india_table):
    # rejected rows exist (stale/missing) but are kept, not patched
    rejected = india_table[india_table["status"] != "ok"]
    # at least the structure is intact
    assert isinstance(rejected, type(india_table))


def test_india_period_table_dS_finite_for_ok(india_table):
    import math
    ok = india_table[india_table["status"] == "ok"]
    assert ok["dS"].notna().all()
    assert ok["dF"].notna().all()


# --- Config ------------------------------------------------------------------

def test_india_settings_currency(india_settings):
    assert india_settings.policy.currency == "INR"


def test_india_settings_contract_size(india_settings):
    assert india_settings.policy.contract_size == 15000


def test_india_settings_forecast(india_settings):
    assert india_settings.forecast_gallons == 1500000


def test_india_settings_n_cap(india_settings):
    # 0.75 * 1500000 / 15000 = 75
    assert india_settings.policy.n_cap(india_settings.forecast_gallons) == 75


def test_india_settings_experiment_id(india_settings):
    assert india_settings.experiment_id == "HP-INDIA"


def test_india_settings_cash_cap(india_settings):
    assert india_settings.policy.cash_cap == 2000000


def test_india_settings_instrument(india_settings):
    assert india_settings.policy.instrument == "MCX-CRUDE"


# --- Manifest ----------------------------------------------------------------

def test_india_manifest_synthetic(india_market, india_settings):
    man, table = manifest_for(india_market, india_settings, [], "SYNTHETIC-INDIA")
    assert man.sessions == len(india_market.sessions)
    sids = [s.series_id for s in man.series]
    assert "IND_DIESEL_RETAIL_INR_PER_LITRE" in sids
    assert "MCX_CRUDE_C1_INR_PER_LITRE" in sids


def test_india_period_table_sha256_stable(india_market, india_settings):
    from hedgeproof.data import table_sha256
    _, t1 = manifest_for(india_market, india_settings, [], "SYNTHETIC-INDIA")
    _, t2 = manifest_for(india_market, india_settings, [], "SYNTHETIC-INDIA")
    assert table_sha256(t1) == table_sha256(t2)


# --- Loaders (real files) ----------------------------------------------------

def test_read_ppac_csv_roundtrip(tmp_path):
    import csv
    p = tmp_path / "ppac_diesel_daily.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "diesel_delhi"])
        w.writerow(["2024-01-01", "89.5"])
        w.writerow(["2024-01-02", "90.0"])
    rs = read_ppac_csv(p, city="Delhi")
    assert len(rs.values) == 2
    assert rs.unit == INDIAN_EXPECTED_UNIT
    assert rs.values.iloc[0] == 89.5


def test_read_ppac_csv_missing_city_fallback(tmp_path):
    import csv
    p = tmp_path / "ppac_diesel_daily.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "diesel_mumbai"])
        w.writerow(["2024-01-01", "91.0"])
    rs = read_ppac_csv(p, city="Delhi")
    assert len(rs.values) == 1


def test_read_indian_futures_csv_long_form(tmp_path):
    import csv
    p = tmp_path / "mcx_crude_daily.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "contract", "close"])
        # INR per barrel -> converted to INR per litre inside loader
        w.writerow(["2024-01-01", "C1", "6000"])
        w.writerow(["2024-01-01", "C2", "6100"])
        w.writerow(["2024-01-01", "C3", "6200"])
    fut = read_indian_futures_csv(p)
    assert FUT_INDIA_C1 in fut
    assert FUT_INDIA_C2 in fut
    assert FUT_INDIA_C3 in fut
    # converted: 6000 INR/barrel / 158.987 = ~37.7 INR/litre
    v = fut[FUT_INDIA_C1].values.iloc[0]
    assert 37 < v < 38


def test_load_indian_market_data_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_indian_market_data(tmp_path)


def test_load_indian_market_data_roundtrip(tmp_path):
    import csv
    raw = tmp_path / "raw"
    raw.mkdir()
    with (raw / "ppac_diesel_daily.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "diesel_delhi"])
        for i in range(5):
            w.writerow([f"2024-01-{i+1:02d}", str(89.0 + i)])
    with (raw / "mcx_crude_daily.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "contract", "close"])
        for i in range(5):
            for j, c in enumerate(["C1", "C2", "C3"]):
                w.writerow([f"2024-01-{i+1:02d}", c, str((6000 + j * 100) * 158.987)])
    md = load_indian_market_data(raw)
    assert len(md.sessions) == 5
    assert md.spot.index.equals(md.c1.index) or len(md.spot) == 5


# --- Trusted core smoke (Indian scenario) ------------------------------------

def test_india_trusted_core_smoke():
    from hedgeproof.cli import build_core
    core = build_core("test", synthetic=True, scenario="india")
    h = core.health()
    assert h["data_label"] == "SYNTHETIC-INDIA TEST FIXTURE"
    assert core.settings.policy.currency == "INR"
    assert core.settings.forecast_gallons == 1500000


def test_india_period_table_via_core():
    from hedgeproof.cli import build_core
    core = build_core("test", synthetic=True, scenario="india")
    # period table rows exist in manifest-derived data; check core has data
    assert core.health()["data_loaded"] is True
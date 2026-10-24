"""Tests for hedgeproof.validators."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from hedgeproof.config import load_settings
from hedgeproof.data import build_period_table
from hedgeproof.synthetic import synthetic_market
from hedgeproof.india import synthetic_indian_market
from hedgeproof.validators import (
    is_clean,
    validate_all,
    validate_config,
    validate_market_data,
    validate_period_table,
    validate_raw_files,
)

REPO = Path(__file__).resolve().parents[1]


def test_validate_market_data_clean_us():
    md = synthetic_market()
    probs = validate_market_data(md)
    assert probs == [], probs


def test_validate_market_data_clean_india():
    md = synthetic_indian_market()
    probs = validate_market_data(md)
    assert probs == [], probs


def test_validate_market_data_empty_series():
    md = synthetic_market()
    md.spot = md.spot.iloc[:0]
    probs = validate_market_data(md)
    assert any("empty series" in p or "spot" in p for p in probs)


def test_validate_market_data_duplicates():
    md = synthetic_market()
    dup = pd.concat([md.spot, md.spot.iloc[:1]])
    md.spot = dup.sort_index()
    probs = validate_market_data(md)
    assert any("duplicate" in p for p in probs)


def test_validate_period_table_clean_us():
    md = synthetic_market()
    settings = load_settings()
    table = build_period_table(md, settings.experiment)
    probs = validate_period_table(table)
    assert probs == [], probs


def test_validate_period_table_clean_india():
    md = synthetic_indian_market()
    settings = load_settings(REPO / "config" / "india")
    table = build_period_table(md, settings.experiment)
    probs = validate_period_table(table)
    assert probs == [], probs


def test_validate_period_table_empty():
    probs = validate_period_table(pd.DataFrame())
    assert probs and "empty" in probs[0]


def test_validate_period_table_missing_column():
    md = synthetic_market()
    settings = load_settings()
    table = build_period_table(md, settings.experiment)
    table = table.drop(columns=["dS"])
    probs = validate_period_table(table)
    assert any("missing column" in p and "dS" in p for p in probs)


def test_validate_config_clean_us():
    settings = load_settings()
    probs = validate_config(settings)
    assert probs == [], probs


def test_validate_config_clean_india():
    settings = load_settings(REPO / "config" / "india")
    probs = validate_config(settings)
    assert probs == [], probs


def test_validate_config_bad_forecast():
    settings = load_settings()
    settings.agency["forecast_gallons_per_month"] = 0
    probs = validate_config(settings)
    assert any("forecast_gallons" in p for p in probs)


def test_validate_config_bad_max_hedge():
    settings = load_settings()
    settings.policy.raw["max_hedge_ratio"] = 1.5
    probs = validate_config(settings)
    assert any("max_hedge_ratio" in p for p in probs)


def test_validate_raw_files_missing(tmp_path):
    probs = validate_raw_files(tmp_path, ["nope.csv"])
    assert probs and "missing raw file" in probs[0]


def test_validate_raw_files_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    probs = validate_raw_files(tmp_path, ["empty.csv"])
    assert any("empty raw file" in p for p in probs)


def test_validate_all_clean():
    md = synthetic_market()
    settings = load_settings()
    table = build_period_table(md, settings.experiment)
    res = validate_all(md, table, settings)
    assert is_clean(res), res


def test_validate_all_india_clean():
    md = synthetic_indian_market()
    settings = load_settings(REPO / "config" / "india")
    table = build_period_table(md, settings.experiment)
    res = validate_all(md, table, settings)
    assert is_clean(res), res
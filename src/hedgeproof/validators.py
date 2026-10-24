"""Validation helpers for market data, period tables and configs.

Owner: Nikshep (data and quant engine).

These checks are *trusted-side* sanity checks: they never compute a hedge
result, they only answer "is this data/config internally consistent enough to
be worth running?" Every function returns a list of human-readable problem
strings; an empty list means "no problems found". They are used by the ingest
path, the test suite and the (optional) `hedgeproof validate` command.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from hedgeproof.config import load_settings
from hedgeproof.data import MarketData, build_period_table


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


def validate_market_data(md: MarketData) -> list[str]:
    """Check a MarketData object for internal consistency."""
    problems: list[str] = []
    if md.spot is None or md.c1 is None or md.c2 is None or md.c3 is None:
        problems.append("market data is missing one or more series")
        return problems
    for name, s in (("spot", md.spot), ("c1", md.c1), ("c2", md.c2), ("c3", md.c3)):
        if s is None or len(s) == 0:
            problems.append(f"{name}: empty series")
            continue
        if s.index.has_duplicates:
            problems.append(f"{name}: duplicate dates")
        if not s.index.is_monotonic_increasing:
            problems.append(f"{name}: dates not sorted")
        if s.isna().any():
            problems.append(f"{name}: contains NaN")
        if not (s > 0).all() if len(s) else True:
            problems.append(f"{name}: non-positive price")
        if not all(isinstance(x, (int, float)) for x in s.tolist()):
            problems.append(f"{name}: non-numeric values")
    # Aligned sessions
    sessions = md.sessions
    if len(sessions) == 0:
        problems.append("no overlapping sessions between Contract 1 and Contract 2")
    else:
        if len(sessions) < 100:
            problems.append(f"only {len(sessions)} sessions; expected hundreds")
    # Spot coverage on sessions
    missing_spot = sum(1 for s in sessions if s not in md.spot.index)
    if missing_spot > len(sessions) * 0.1:
        problems.append(f"spot missing on {missing_spot} of {len(sessions)} sessions (>10%)")
    # Futures continuity at month boundaries
    try:
        from hedgeproof.data import continuity_report

        cont = continuity_report(md)
        if cont.get("flagged", 0) > 10:
            problems.append(f"continuity: {cont['flagged']} flagged month-boundary jumps")
    except Exception as e:  # noqa: BLE001
        problems.append(f"continuity report failed: {e}")
    return problems


def validate_period_table(table: pd.DataFrame) -> list[str]:
    """Check a period table for internal consistency."""
    problems: list[str] = []
    if table is None or len(table) == 0:
        problems.append("period table is empty")
        return problems
    required = ["hedge_month", "entry_date", "exit_date", "delivery_month", "exit_delivery_month",
                "S_budget", "S_exit", "F_entry", "F_exit", "dS", "dF", "split", "status"]
    for c in required:
        if c not in table.columns:
            problems.append(f"missing column: {c}")
    if problems:
        return problems
    # Contract identity
    ok = table[table["status"] == "ok"]
    if len(ok) and not (ok["delivery_month"] == ok["exit_delivery_month"]).all():
        problems.append("contract identity broken: delivery months differ on some rows")
    # No NaN in ok rows for key fields
    for col in ("S_budget", "S_exit", "F_entry", "F_exit", "dS", "dF"):
        if ok[col].isna().any():
            problems.append(f"{col}: NaN in ok rows")
    # Splits
    for sp in ("development", "validation", "holdout"):
        if sp not in set(table["split"]):
            problems.append(f"split missing: {sp}")
    # Status values
    allowed_status = {"ok"} | {s for s in table["status"].unique() if str(s).startswith("rejected")}
    bad = set(table["status"].unique()) - allowed_status
    if bad:
        problems.append(f"unexpected status values: {sorted(bad)}")
    # dF non-zero variance not checked here (engine does)
    return problems


def validate_config(settings: Any) -> list[str]:
    """Check a Settings object for internal consistency."""
    problems: list[str] = []
    try:
        p = settings.policy
        a = settings.agency
        e = settings.experiment
    except Exception as ex:  # noqa: BLE001
        return [f"settings incomplete: {ex}"]
    # Forecast positive
    try:
        q = settings.forecast_gallons
        if q <= 0:
            problems.append("forecast_gallons_per_month must be positive")
    except Exception as ex:  # noqa: BLE001
        problems.append(f"forecast_gallons: {ex}")
    # Contract size
    try:
        cs = p.contract_size
        if cs <= 0:
            problems.append("contract_size must be positive")
        if q % cs != 0 and False:
            pass
    except Exception as ex:  # noqa: BLE001
        problems.append(f"contract_size: {ex}")
    # n_cap at least 1
    try:
        nc = p.n_cap(q)
        if nc < 1:
            problems.append("n_cap < 1: forecast too small for even one contract")
    except Exception as ex:  # noqa: BLE001
        problems.append(f"n_cap: {ex}")
    # max_hedge_ratio
    try:
        if not (0 < p.max_hedge_ratio <= 1.0):
            problems.append("max_hedge_ratio must be in (0, 1]")
    except Exception as ex:  # noqa: BLE001
        problems.append(f"max_hedge_ratio: {ex}")
    # cash stress cap
    try:
        if p.cash_cap <= 0:
            problems.append("cash_stress_cap must be positive")
    except Exception as ex:  # noqa: BLE001
        problems.append(f"cash_stress_cap: {ex}")
    # splits present
    for name in ("development", "validation", "holdout"):
        if name not in e.get("splits", {}):
            problems.append(f"missing split: {name}")
    # pass rule present
    if "pass_rule" not in e:
        problems.append("missing pass_rule")
    # research limits
    rl = e.get("research_limits", {})
    if rl.get("max_candidates_per_lineage", 0) < 1:
        problems.append("max_candidates_per_lineage must be >= 1")
    # currency
    if not p.currency:
        problems.append("currency missing")
    return problems


def validate_raw_files(raw_dir: Path, expected_names: list[str]) -> list[str]:
    """Check that the expected raw files exist in raw_dir."""
    problems: list[str] = []
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        problems.append(f"raw dir missing: {raw_dir}")
        return problems
    for name in expected_names:
        p = raw_dir / name
        if not p.exists():
            problems.append(f"missing raw file: {name}")
        elif p.stat().st_size == 0:
            problems.append(f"empty raw file: {name}")
    return problems


def validate_all(md: MarketData, table: pd.DataFrame, settings: Any) -> dict[str, list[str]]:
    """Run all validators and return a dict of problem lists."""
    return {
        "market_data": validate_market_data(md),
        "period_table": validate_period_table(table),
        "config": validate_config(settings),
    }


def is_clean(results: dict[str, list[str]]) -> bool:
    return all(not v for v in results.values())
"""Indian fuel-hedge data support: calendar, loaders and a labelled synthetic generator.

Owner: Nikshep (data and quant engine), Indian scenario.

This module is the Indian counterpart of :mod:`hedgeproof.data` (U.S. EIA) and
:mod:`hedgeproof.synthetic`. It exists so the same trusted engine, gate and
dashboard can run on an Indian-flavoured scenario without touching the U.S.
code path. Every artifact produced from the synthetic generator carries the
label ``SYNTHETIC-INDIA``; real Indian files, when supplied, are recorded in a
manifest exactly like the EIA files.

Honesty notes
--------------
* India has no liquid exchange-traded ULSD diesel futures contract. The Indian
  scenario therefore uses MCX crude-oil futures as the hedge instrument and an
  Indian retail diesel price as the physical price proxy, with the basis risk
  between the two stated explicitly. This is an illustrative proxy, not a
  validated deployment for any Indian transit agency.
* Indian retail diesel prices are administered in part and published by PPAC
  (Petroleum Planning & Analysis Cell) and the OMCs. The loader accepts the
  PPAC daily price CSV and an MCX futures CSV; it does not invent prices.
* Units: Indian scenario prices are in INR per litre (spot) and INR per
  barrel converted to INR per litre for futures; the contract size is declared
  in litres in ``config/india/policy.toml``.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from hedgeproof.data import MarketData, month_key, add_months, month_range
from hedgeproof.records import hash_value

# ---------------------------------------------------------------------------
# Labels and series identity
# ---------------------------------------------------------------------------

INDIAN_LABEL = "SYNTHETIC-INDIA"
SPOT_INDIA_DIESEL = "IND_DIESEL_RETAIL_INR_PER_LITRE"
FUT_INDIA_C1 = "MCX_CRUDE_C1_INR_PER_LITRE"
FUT_INDIA_C2 = "MCX_CRUDE_C2_INR_PER_LITRE"
FUT_INDIA_C3 = "MCX_CRUDE_C3_INR_PER_LITRE"
INDIAN_SERIES_ROLES = {
    SPOT_INDIA_DIESEL: "physical price proxy S (Indian retail diesel, INR/litre)",
    FUT_INDIA_C1: "futures Contract 1 (exit leg, MCX crude proxy)",
    FUT_INDIA_C2: "futures Contract 2 (entry leg, MCX crude proxy)",
    FUT_INDIA_C3: "futures Contract 3 (sizing reference F_ref only)",
}
INDIAN_EXPECTED_UNIT = "INR per Litre"
INDIAN_SOURCE_URLS = {
    "ppac_diesel_daily.csv": "https://ppac.gov.in/ (Petroleum Planning & Analysis Cell, retail selling price)",
    "mcx_crude_daily.csv": "https://www.mcxindia.com/ (MCX crude oil futures, daily bhavcopy)",
}

# Indian retail diesel is roughly INR 85-100 per litre; MCX crude proxy level
# is set so that the futures track it with basis noise (as in the U.S. case).
INDIAN_LEVEL_INR_PER_LITRE = 90.0
LITRES_PER_BARREL = 158.987294928


# ---------------------------------------------------------------------------
# Indian market holidays
# ---------------------------------------------------------------------------


def _indian_holidays(start: date, end: date) -> set[date]:
    """Indian market (NSE/MCX) holidays, plus weekends, for the given range.

    This is a declared, best-effort list of the major trading holidays. It is
    used only by the synthetic generator and the session calendar; real data
    files carry their own trading dates.
    """
    out: set[date] = set()
    for y in range(start.year, end.year + 1):
        candidates = {
            date(y, 1, 26),   # Republic Day
            date(y, 3, 8),    # Holi (approx; varies)
            date(y, 4, 14),   # Ambedkar Jayanti / Good Friday (approx)
            date(y, 5, 1),    # Maharashtra Day
            date(y, 8, 15),   # Independence Day
            date(y, 10, 2),   # Gandhi Jayanti
            date(y, 10, 24),  # Dussehra (approx)
            date(y, 11, 1),   # Diwali (approx)
            date(y, 11, 12),  # Diwali (approx)
            date(y, 12, 25),  # Christmas
        }
        for c in candidates:
            if start <= c <= end:
                out.add(c)
    # Weekends
    d = start
    while d <= end:
        if d.weekday() >= 5:
            out.add(d)
        d += timedelta(days=1)
    return out


def indian_holidays(start: date, end: date) -> set[date]:
    return _indian_holidays(start, end)


# ---------------------------------------------------------------------------
# Synthetic Indian market (labelled SYNTHETIC-INDIA)
# ---------------------------------------------------------------------------


def synthetic_indian_market(
    seed: int = 11,
    start: str = "2013-10-01",
    end: str = "2024-04-05",
    beta: float = 0.88,
    basis_noise: float = 0.6,
    independent_spot: bool = False,
    spread_per_month: float = 0.15,
    level: float = INDIAN_LEVEL_INR_PER_LITRE,
    drop_spot: tuple[str, ...] = (),
) -> MarketData:
    """SYNTHETIC Indian-flavoured market data, labelled SYNTHETIC-INDIA.

    Reuses the generic synthetic generator with Indian holidays and an Indian
    price level. Never used for empirical claims.
    """
    from hedgeproof.synthetic import synthetic_market

    def _hol(s0: date, e0: date) -> set[date]:
        return _indian_holidays(s0, e0)

    md = synthetic_market(
        seed=seed,
        start=start,
        end=end,
        beta=beta,
        basis_noise=basis_noise,
        independent_spot=independent_spot,
        spread_per_month=spread_per_month,
        level=level,
        drop_spot=drop_spot,
        holidays=_hol,
    )
    # Relabel the MarketData names/units to the Indian identity.
    md.names = {
        SPOT_INDIA_DIESEL: "Indian retail diesel spot (SYNTHETIC-INDIA)",
        FUT_INDIA_C1: "MCX crude proxy Contract 1 (SYNTHETIC-INDIA)",
        FUT_INDIA_C2: "MCX crude proxy Contract 2 (SYNTHETIC-INDIA)",
        FUT_INDIA_C3: "MCX crude proxy Contract 3 (SYNTHETIC-INDIA)",
    }
    md.units = {k: INDIAN_EXPECTED_UNIT for k in md.names}
    # The MarketData field names stay spot/c1/c2/c3; record the Indian ids in names.
    md.names = {**{SPOT_INDIA_DIESEL: md.names[SPOT_INDIA_DIESEL]}, **md.names}
    return md


# ---------------------------------------------------------------------------
# Real Indian file loaders (PPAC CSV + MCX bhavcopy CSV)
# ---------------------------------------------------------------------------


@dataclass
class IndianRawSeries:
    series_id: str
    name: str
    unit: str
    values: pd.Series  # index: pandas Timestamp (date), float values, no NaN


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return pd.Timestamp(s).date()
    except (ValueError, TypeError):
        return None


def read_ppac_csv(path: Path, city: str = "Delhi") -> IndianRawSeries:
    """Read a PPAC-style daily diesel retail price CSV.

    Expected columns (case-insensitive, flexible): 'date' and a column whose name
    contains 'diesel' and the chosen city (or any diesel column if city missing).
    Values are INR per litre. Returns a series keyed by trading date.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name}: empty PPAC file")
    # Find date column
    header = [h.strip() for h in rows[0].keys()]
    date_col = next((h for h in header if h.lower() in ("date", "price_date", "effective_date")), None)
    if date_col is None:
        date_col = next((h for h in header if "date" in h.lower()), None)
    if date_col is None:
        raise ValueError(f"{path.name}: no date column found")
    # Find diesel price column
    price_col = None
    city_l = city.lower()
    for h in header:
        hl = h.lower()
        if "diesel" in hl and city_l in hl:
            price_col = h
            break
    if price_col is None:
        for h in header:
            if "diesel" in h.lower():
                price_col = h
                break
    if price_col is None:
        # Fall back to any column containing 'price'
        for h in header:
            if "price" in h.lower():
                price_col = h
                break
    if price_col is None:
        raise ValueError(f"{path.name}: no diesel price column found")

    dates, vals = [], []
    for r in rows:
        d = _parse_date(r.get(date_col, ""))
        v = r.get(price_col, "")
        if d is None or v is None or str(v).strip() == "":
            continue
        try:
            num = float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        if not math.isfinite(num):
            continue
        dates.append(pd.Timestamp(d))
        vals.append(num)
    if not dates:
        raise ValueError(f"{path.name}: no valid rows")
    s = pd.Series(vals, index=pd.DatetimeIndex(dates), dtype="float64").sort_index()
    if s.index.has_duplicates:
        s = s.groupby(s.index).last()
    return IndianRawSeries(SPOT_INDIA_DIESEL, f"Indian retail diesel ({city})", INDIAN_EXPECTED_UNIT, s)


def read_indian_futures_csv(path: Path) -> dict[str, IndianRawSeries]:
    """Read an MCX crude-oil bhavcopy CSV and return Contracts 1-3 as INR/litre.

    Expected columns: 'date'/'trade_date' and contract-month columns or a single
    'close'/'settle' with a 'contract'/'expiry' column. This loader accepts the
    common long form: date, contract_code, close. Values are converted from
    INR per barrel to INR per litre using LITRES_PER_BARREL.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name}: empty MCX file")
    header = [h.strip() for h in rows[0].keys()]
    date_col = next((h for h in header if "date" in h.lower()), None)
    if date_col is None:
        raise ValueError(f"{path.name}: no date column")
    # Detect long form
    contract_col = next((h for h in header if "contract" in h.lower() or "expiry" in h.lower() or "symbol" in h.lower()), None)
    close_col = next((h for h in header if h.lower() in ("close", "settle", "settlement", "closing") or "close" in h.lower()), None)
    if close_col is None:
        raise ValueError(f"{path.name}: no close column")

    # Group closes by (date, contract)
    by_date: dict[pd.Timestamp, dict[str, float]] = {}
    for r in rows:
        d = _parse_date(r.get(date_col, ""))
        if d is None:
            continue
        close_raw = r.get(close_col, "")
        try:
            close_val = float(str(close_raw).replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        if not math.isfinite(close_val):
            continue
        # Convert INR/barrel -> INR/litre
        close_val = close_val / LITRES_PER_BARREL
        ts = pd.Timestamp(d)
        key = r.get(contract_col, "") if contract_col else ""
        by_date.setdefault(ts, {})[key.strip()] = close_val

    if not by_date:
        raise ValueError(f"{path.name}: no valid rows")

    # If a contract column exists, pick the three nearest distinct contracts per date.
    # Otherwise, treat the whole file as Contract 1 only (caller must supply three files).
    if contract_col:
        # Build per-contract series, then align the three nearest by sorting contract codes.
        all_contracts = sorted({k for v in by_date.values() for k in v})
        # Map each date to sorted contract codes present
        c1s, c2s, c3s = [], [], []
        dates_sorted = sorted(by_date)
        for ts in dates_sorted:
            present = sorted(by_date[ts])
            vals = [by_date[ts][k] for k in present]
            c1s.append(vals[0] if len(vals) > 0 else float("nan"))
            c2s.append(vals[1] if len(vals) > 1 else float("nan"))
            c3s.append(vals[2] if len(vals) > 2 else float("nan"))
        def _series(vals):
            s = pd.Series(vals, index=pd.DatetimeIndex(dates_sorted), dtype="float64")
            return s.dropna()
        return {
            FUT_INDIA_C1: IndianRawSeries(FUT_INDIA_C1, "MCX crude proxy Contract 1", INDIAN_EXPECTED_UNIT, _series(c1s)),
            FUT_INDIA_C2: IndianRawSeries(FUT_INDIA_C2, "MCX crude proxy Contract 2", INDIAN_EXPECTED_UNIT, _series(c2s)),
            FUT_INDIA_C3: IndianRawSeries(FUT_INDIA_C3, "MCX crude proxy Contract 3", INDIAN_EXPECTED_UNIT, _series(c3s)),
        }

    # Single-contract file: caller supplies only Contract 1; leave C2/C3 empty-ish
    dates_sorted = sorted(by_date)
    vals = [list(by_date[ts].values())[0] for ts in dates_sorted]
    s = pd.Series(vals, index=pd.DatetimeIndex(dates_sorted), dtype="float64")
    return {
        FUT_INDIA_C1: IndianRawSeries(FUT_INDIA_C1, "MCX crude proxy Contract 1", INDIAN_EXPECTED_UNIT, s),
    }


def load_indian_market_data(raw_dir: Path) -> MarketData:
    raw_dir = Path(raw_dir)
    spot_path = raw_dir / "ppac_diesel_daily.csv"
    fut_path = raw_dir / "mcx_crude_daily.csv"
    if not spot_path.exists():
        raise FileNotFoundError(f"missing {spot_path}")
    if not fut_path.exists():
        raise FileNotFoundError(f"missing {fut_path}")
    spot_rs = read_ppac_csv(spot_path)
    fut = read_indian_futures_csv(fut_path)
    if FUT_INDIA_C2 not in fut or FUT_INDIA_C3 not in fut:
        raise ValueError("MCX file must contain at least three contract columns")
    allser = {SPOT_INDIA_DIESEL: spot_rs, **fut}
    return MarketData(
        spot=spot_rs.values,
        c1=fut[FUT_INDIA_C1].values,
        c2=fut[FUT_INDIA_C2].values,
        c3=fut[FUT_INDIA_C3].values,
        names={k: v.name for k, v in allser.items()},
        units={k: v.unit for k, v in allser.items()},
    )

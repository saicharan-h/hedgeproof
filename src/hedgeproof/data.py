"""EIA data loading, the session calendar, contract identity and the period table.

Owner: Nikshep (data and quant engine).

Plain-language summary
----------------------
* A *session* is a trading date that has both a Contract 1 and a Contract 2
  NY Harbor futures close.
* ``d_m`` is the first session of calendar month ``m``.
* Hedge month ``p``: buy Contract 2 at the ``d_p`` close (delivery month p+2) and
  sell it at the ``d_(p+1)`` close, when the same delivery month has become
  Contract 1. Both legs record the delivery month and we assert they match,
  so a profit is never computed from two different contracts.
* The budget is fixed from the spot price known before entry; the fuel is bought
  at spot on the exit session.

Nothing here patches or interpolates prices. A row that cannot be built is kept
with a rejection reason and excluded from calculations.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from hedgeproof.records import hash_value, sha256_hex

# EIA series used (checked on EIA pages, 23 Oct 2026).
SPOT_GULF_ULSD = "EER_EPD2DXL0_PF4_RGC_DPG"
FUT_C1 = "EER_EPD2F_PE1_Y35NY_DPG"
FUT_C2 = "EER_EPD2F_PE2_Y35NY_DPG"
FUT_C3 = "EER_EPD2F_PE3_Y35NY_DPG"
SERIES_ROLES = {
    SPOT_GULF_ULSD: "physical price proxy S (Gulf Coast ULSD spot)",
    FUT_C1: "futures Contract 1 (exit leg)",
    FUT_C2: "futures Contract 2 (entry leg)",
    FUT_C3: "futures Contract 3 (sizing reference F_ref only)",
}
EXPECTED_UNIT = "Dollars per Gallon"

SOURCE_URLS = {
    "PET_PRI_FUT_S1_D.xls": "https://www.eia.gov/dnav/pet/xls/PET_PRI_FUT_S1_D.xls",
    "PET_PRI_SPT_S1_D.xls": "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_D.xls",
}

PERIOD_COLUMNS = [
    "hedge_month",
    "entry_date",
    "exit_date",
    "delivery_month",
    "exit_delivery_month",
    "budget_spot_date",
    "f_ref_date",
    "S_budget",
    "S_exit",
    "F_entry",
    "F_exit",
    "F_ref",
    "dS",
    "dF",
    "split",
    "status",
]


class DataError(ValueError):
    """Raised when raw data violates an assumption (unit, layout, mapping)."""


# --- Month arithmetic -------------------------------------------------------


def month_key(d: date | pd.Timestamp) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(month: str, k: int) -> str:
    y, m = (int(x) for x in month.split("-"))
    idx = y * 12 + (m - 1) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_range(first: str, last: str) -> list[str]:
    out, m = [], first
    while m <= last:
        out.append(m)
        m = add_months(m, 1)
    return out


# --- Raw EIA workbook loader ------------------------------------------------


@dataclass
class RawSeries:
    series_id: str
    name: str
    unit: str
    values: pd.Series  # index: pandas Timestamp (date), float values, no NaN


def _unit_from_name(name: str) -> str:
    found = re.findall(r"\(([^()]*)\)", name)
    return found[-1].strip() if found else ""


def _cell_date(cell: Any, datemode: int) -> date | None:
    import xlrd

    if cell.ctype in (xlrd.XL_CELL_DATE, xlrd.XL_CELL_NUMBER) and cell.value:
        return xlrd.xldate_as_datetime(cell.value, datemode).date()
    if cell.ctype == xlrd.XL_CELL_TEXT and cell.value.strip():
        try:
            return pd.Timestamp(cell.value.strip()).date()
        except (ValueError, TypeError):
            return None
    return None


def read_eia_xls(path: Path, wanted: list[str]) -> dict[str, RawSeries]:
    """Read the wanted series from an EIA dnav workbook (sheets named 'Data N').

    Each data sheet has a 'Sourcekey' row with series IDs, followed by a 'Date'
    row with series names (unit in the final parentheses), then dated rows.
    """
    import xlrd

    book = xlrd.open_workbook(str(path))
    found: dict[str, RawSeries] = {}
    for sheet in book.sheets():
        key_row = None
        for r in range(min(10, sheet.nrows)):
            if str(sheet.cell_value(r, 0)).strip().lower() == "sourcekey":
                key_row = r
                break
        if key_row is None:
            continue
        ids = [str(sheet.cell_value(key_row, c)).strip() for c in range(sheet.ncols)]
        names = [str(sheet.cell_value(key_row + 1, c)).strip() for c in range(sheet.ncols)]
        for col, sid in enumerate(ids):
            if sid not in wanted:
                continue
            dates, vals = [], []
            for r in range(key_row + 2, sheet.nrows):
                d = _cell_date(sheet.cell(r, 0), book.datemode)
                v = sheet.cell(r, col)
                if d is None or v.ctype != xlrd.XL_CELL_NUMBER:
                    continue
                if not math.isfinite(float(v.value)):
                    continue
                dates.append(pd.Timestamp(d))
                vals.append(float(v.value))
            s = pd.Series(vals, index=pd.DatetimeIndex(dates), dtype="float64").sort_index()
            if s.index.has_duplicates:
                raise DataError(f"{sid}: duplicate dates in {path.name}")
            found[sid] = RawSeries(sid, names[col], _unit_from_name(names[col]), s)
    missing = [w for w in wanted if w not in found]
    if missing:
        raise DataError(f"{path.name}: series not found: {missing}")
    for rs in found.values():
        if rs.unit != EXPECTED_UNIT:
            raise DataError(f"{rs.series_id}: unit is {rs.unit!r}, expected {EXPECTED_UNIT!r}")
    return found


# --- Market data container --------------------------------------------------


@dataclass
class MarketData:
    """Four aligned daily series: spot S and futures Contracts 1 to 3."""

    spot: pd.Series
    c1: pd.Series
    c2: pd.Series
    c3: pd.Series
    names: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)

    @property
    def sessions(self) -> list[pd.Timestamp]:
        both = self.c1.index.intersection(self.c2.index)
        return list(both.sort_values())

    def first_sessions(self) -> dict[str, pd.Timestamp]:
        """d_m for every month that has sessions."""
        out: dict[str, pd.Timestamp] = {}
        for s in self.sessions:
            out.setdefault(month_key(s), s)
        return out

    def scaled_after(self, cutoff: pd.Timestamp, factor: float) -> "MarketData":
        """Copy with every price strictly after ``cutoff`` multiplied (look-ahead test)."""

        def scale(s: pd.Series) -> pd.Series:
            s = s.copy()
            s[s.index > cutoff] *= factor
            return s

        return MarketData(scale(self.spot), scale(self.c1), scale(self.c2), scale(self.c3), self.names, self.units)


def load_market_data(raw_dir: Path) -> MarketData:
    fut = read_eia_xls(raw_dir / "PET_PRI_FUT_S1_D.xls", [FUT_C1, FUT_C2, FUT_C3])
    spt = read_eia_xls(raw_dir / "PET_PRI_SPT_S1_D.xls", [SPOT_GULF_ULSD])
    allser = {**fut, **spt}
    return MarketData(
        spot=spt[SPOT_GULF_ULSD].values,
        c1=fut[FUT_C1].values,
        c2=fut[FUT_C2].values,
        c3=fut[FUT_C3].values,
        names={k: v.name for k, v in allser.items()},
        units={k: v.unit for k, v in allser.items()},
    )


# --- Period table -----------------------------------------------------------


@dataclass(frozen=True)
class SplitDef:
    name: str
    first_hedge_month: str
    last_hedge_month: str
    start_date: str
    end_date: str


def split_defs(experiment: dict[str, Any]) -> list[SplitDef]:
    out = []
    for name in ("development", "validation", "holdout"):
        s = experiment["splits"][name]
        out.append(SplitDef(name, s["first_hedge_month"], s["last_hedge_month"], s["start_date"], s["end_date"]))
    return out


def assign_split(hedge_month: str, entry: pd.Timestamp, exit_: pd.Timestamp, splits: list[SplitDef], warmup_first: str) -> str:
    """A position belongs to a split only if it opens and closes inside it."""
    for sp in splits:
        start, end = pd.Timestamp(sp.start_date), pd.Timestamp(sp.end_date)
        opens_inside = start <= entry <= end
        closes_inside = start <= exit_ <= end
        if opens_inside and closes_inside and sp.first_hedge_month <= hedge_month <= sp.last_hedge_month:
            return sp.name
        if opens_inside != closes_inside:
            return "purged"
    if hedge_month < warmup_first:
        return "before_warmup"
    if hedge_month < splits[0].first_hedge_month:
        return "warmup"
    return "outside"


def build_period_table(
    md: MarketData,
    experiment: dict[str, Any],
    *,
    spot_lag_sessions: int = 1,
    stale_max_sessions: int = 3,
) -> pd.DataFrame:
    """One row per hedge month from the warm-up start to the last month with an exit."""
    sessions = md.sessions
    pos = {s: i for i, s in enumerate(sessions)}
    d = md.first_sessions()
    warm = experiment["splits"]["warmup_first_hedge_month"]
    splits = split_defs(experiment)
    months = sorted(m for m in d if m >= warm)
    rows: list[dict[str, Any]] = []
    for p in months:
        nxt = add_months(p, 1)
        if nxt not in d:
            continue  # no exit session in the data (for example April 2024)
        entry, exit_ = d[p], d[nxt]
        row: dict[str, Any] = {c: None for c in PERIOD_COLUMNS}
        row.update(
            hedge_month=p,
            entry_date=entry.date().isoformat(),
            exit_date=exit_.date().isoformat(),
            delivery_month=add_months(month_key(entry), 2),
            exit_delivery_month=add_months(month_key(exit_), 1),
        )
        status = "ok"
        if row["delivery_month"] != row["exit_delivery_month"]:
            status = "rejected: entry and exit are different delivery months"
        i = pos[entry]
        # Budget spot: latest spot usable before the decision (spot lag), within the stale limit.
        s_budget = s_date = None
        for k in range(spot_lag_sessions, spot_lag_sessions + stale_max_sessions):
            if i - k < 0:
                break
            cand = sessions[i - k]
            if cand in md.spot.index:
                s_budget, s_date = float(md.spot[cand]), cand
                break
        if s_budget is None and status == "ok":
            status = "rejected: stale budget spot (none within limit)"
        # F_ref: Contract 3 on the latest session before d_p, still in month p-1.
        f_ref = f_date = None
        for k in range(1, 1 + stale_max_sessions):
            if i - k < 0:
                break
            cand = sessions[i - k]
            if month_key(cand) != add_months(p, -1):
                break
            if cand in md.c3.index:
                f_ref, f_date = float(md.c3[cand]), cand
                break
        if f_ref is None and status == "ok":
            status = "rejected: no Contract 3 reference close"
        s_exit = float(md.spot[exit_]) if exit_ in md.spot.index else None
        if s_exit is None and status == "ok":
            status = "rejected: missing exit spot (no interpolation)"
        f_entry, f_exit = float(md.c2[entry]), float(md.c1[exit_])
        row.update(
            budget_spot_date=s_date.date().isoformat() if s_date is not None else None,
            f_ref_date=f_date.date().isoformat() if f_date is not None else None,
            S_budget=s_budget,
            S_exit=s_exit,
            F_entry=f_entry,
            F_exit=f_exit,
            F_ref=f_ref,
            dS=(s_exit - s_budget) if (s_exit is not None and s_budget is not None) else None,
            dF=f_exit - f_entry,
            split=assign_split(p, entry, exit_, splits, warm),
            status=status,
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=PERIOD_COLUMNS)


def operational_entry(md: MarketData, replay_date: str, stale_max_sessions: int = 3) -> dict[str, Any]:
    """Entry facts for the paper decision at the replay date (no exit exists)."""
    rd = pd.Timestamp(replay_date)
    d = md.first_sessions()
    p = month_key(rd)
    if d.get(p) != rd:
        raise DataError(f"replay date {replay_date} is not the first session of {p}")
    sessions = md.sessions
    i = sessions.index(rd)
    f_ref = f_date = None
    for k in range(1, 1 + stale_max_sessions):
        cand = sessions[i - k]
        if month_key(cand) != add_months(p, -1):
            break
        if cand in md.c3.index:
            f_ref, f_date = float(md.c3[cand]), cand
            break
    if f_ref is None:
        raise DataError("no Contract 3 reference close before the replay date")
    return {
        "hedge_month": p,
        "entry_date": rd.date().isoformat(),
        "delivery_month": add_months(p, 2),
        "F_entry": float(md.c2[rd]),
        "F_ref": f_ref,
        "f_ref_date": f_date.date().isoformat(),
        "last_data_session_before_entry": sessions[i - 1].date().isoformat(),
    }


def table_sha256(table: pd.DataFrame) -> str:
    return hash_value(table_records(table))


def table_records(table: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows as plain dicts with None for missing values (JSON-safe)."""
    out = []
    for rec in table.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, float) and not math.isfinite(v):
                v = None
            clean[k] = v
        out.append(clean)
    return out


# --- Training windows and time-restricted views -----------------------------


WINDOW_FIELDS = ["hedge_month", "entry_date", "exit_date", "S_budget", "S_exit", "F_entry", "F_exit", "dS", "dF"]


class WindowError(ValueError):
    pass


def training_window(table: pd.DataFrame, decision_month: str, window: int, purge: int = 2) -> list[dict[str, Any]]:
    """The most recent ``window`` valid completed positions for decision month p.

    Uses positions q <= p - purge only (q = p - 1 closes at the same close where
    p fills). Raises WindowError when the window cannot be filled or is degenerate.
    """
    last_allowed = add_months(decision_month, -purge)
    ok = table[(table["status"] == "ok") & (table["hedge_month"] <= last_allowed)]
    if len(ok) < window:
        raise WindowError(f"only {len(ok)} valid positions before {decision_month}, need {window}")
    rows = ok.tail(window)
    recs = [{k: r[k] for k in WINDOW_FIELDS} for r in table_records(rows)]
    for r in recs:
        for k in ("S_budget", "S_exit", "F_entry", "F_exit", "dS", "dF"):
            if r[k] is None or not math.isfinite(float(r[k])):
                raise WindowError(f"non-finite {k} in window position {r['hedge_month']}")
    dfs = [r["dF"] for r in recs]
    if max(dfs) - min(dfs) == 0:
        raise WindowError("Var(dF) is zero in the window")
    return recs


def continuity_report(md: MarketData) -> dict[str, Any]:
    """Compare the same-contract roll move with the median daily move.

    At each month boundary, Contract 2 on the last session of month m and
    Contract 1 on d_(m+1) are the same delivery month. A big jump there would
    suggest the mapping is wrong. Reported, never used to patch prices.
    """
    sessions = md.sessions
    within: list[float] = []
    boundaries = []
    for a, b in zip(sessions, sessions[1:]):
        if month_key(a) == month_key(b):
            within.append(abs(float(md.c1[b]) - float(md.c1[a])))
        else:
            boundaries.append((a, b))
    med = float(pd.Series(within).median()) if within else float("nan")
    flagged = []
    for a, b in boundaries:
        same = float(md.c1[b]) - float(md.c2[a])
        cross = float(md.c1[b]) - float(md.c1[a])
        if abs(same) > 3 * med:
            flagged.append(
                {"last_session": a.date().isoformat(), "first_session": b.date().isoformat(), "same_contract_move": round(same, 4), "cross_contract_move": round(cross, 4)}
            )
    return {
        "boundaries": len(boundaries),
        "median_abs_daily_move_c1": med,
        "threshold": 3 * med,
        "flagged": len(flagged),
        "flagged_boundaries": flagged,
    }


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def parse_ist(ts: str) -> str:
    """Normalize a team-reported retrieval time to ISO 8601 with +05:30."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.isoformat(timespec="minutes") + "+05:30"
    return dt.isoformat(timespec="minutes")

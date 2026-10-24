"""SYNTHETIC market data for tests and labelled fixtures only.

Never used for empirical claims. Every artifact built from it carries the label
SYNTHETIC. Each delivery contract has one continuous price path, so Contract 2
on the last session of a month and Contract 1 on the next first session are the
same contract (as in the real data), and the contract-identity tests are
meaningful.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from hedgeproof.data import MarketData

SYNTHETIC_LABEL = "SYNTHETIC"


def _holidays(start: date, end: date) -> set[date]:
    out = {date(2024, 3, 29)}  # Good Friday 2024: 28 Mar is followed by 1 Apr
    for y in range(start.year, end.year + 1):
        out |= {date(y, 1, 1), date(y, 7, 4), date(y, 12, 25)}
    return out


def synthetic_market(
    seed: int = 7,
    start: str = "2013-10-01",
    end: str = "2024-04-05",
    beta: float = 0.9,
    basis_noise: float = 0.04,
    independent_spot: bool = False,
    spread_per_month: float = 0.01,
    level: float = 2.5,
    drop_spot: tuple[str, ...] = (),
) -> MarketData:
    rng = np.random.default_rng(seed)
    s0, e0 = date.fromisoformat(start), date.fromisoformat(end)
    hol = _holidays(s0, e0)
    days = []
    d = s0
    while d <= e0:
        if d.weekday() < 5 and d not in hol:
            days.append(d)
        d += timedelta(days=1)
    n = len(days)
    # Mean-reverting log price for the nearby futures level.
    x = np.empty(n)
    x[0] = np.log(level)
    for i in range(1, n):
        x[i] = x[i - 1] + 0.01 * (np.log(level) - x[i - 1]) + 0.018 * rng.standard_normal()
    base = np.exp(x)
    idx = pd.DatetimeIndex([pd.Timestamp(t) for t in days])

    def contract_price(k: int) -> np.ndarray:
        # Price of the contract delivering k months after the current month, with
        # continuous time-to-delivery so the same contract has no jump at a roll.
        out = np.empty(n)
        for i, t in enumerate(days):
            dm = t.year * 12 + t.month - 1 + k
            delivery_start = date(dm // 12, dm % 12 + 1, 1)
            tau_months = (delivery_start - t).days / 30.4
            out[i] = base[i] + spread_per_month * tau_months
        return out

    c1, c2, c3 = contract_price(1), contract_price(2), contract_price(3)
    if independent_spot:
        y = np.empty(n)
        y[0] = np.log(level)
        for i in range(1, n):
            y[i] = y[i - 1] + 0.01 * (np.log(level) - y[i - 1]) + 0.018 * rng.standard_normal()
        spot = np.exp(y)
    else:
        b = np.zeros(n)
        for i in range(1, n):
            b[i] = 0.7 * b[i - 1] + basis_noise * rng.standard_normal()
        spot = 0.3 + beta * base + b
    spot_s = pd.Series(spot, index=idx)
    if drop_spot:
        spot_s = spot_s.drop(pd.DatetimeIndex([pd.Timestamp(x) for x in drop_spot]), errors="ignore")
    return MarketData(
        spot=spot_s,
        c1=pd.Series(c1, index=idx),
        c2=pd.Series(c2, index=idx),
        c3=pd.Series(c3, index=idx),
        names={"label": SYNTHETIC_LABEL},
        units={},
    )

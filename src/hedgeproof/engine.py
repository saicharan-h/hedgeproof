"""Trusted quantitative engine: sizing, cash flows, metrics, baselines, bootstrap.

Owner: Nikshep (data and quant engine).

Only trusted code calls this module. Agents never compute or report their own
metrics; generated estimator code only returns one raw hedge ratio per window.

Core identity (per hedge month p, Q gallons, n contracts of 42,000 gallons):

    Budget(p)      = Q * S_budget
    NetCost(p)     = Q * S_exit - 42,000 * n * dF + n * cost_per_contract
    BudgetError(p) = NetCost(p) - Budget(p) = Q * dS - 42,000 * n * dF + costs

When futures rise (dF > 0) a long hedge gains and lowers the net cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from hedgeproof.config import Policy, Settings

STRATEGIES = ("unhedged", "fixed50", "adaptive")
# Variance of dF below this ($/gal squared) is treated as zero (floating-point rounding of identical values).
ZERO_VARIANCE_TOL = 1e-12


# --- Sizing ------------------------------------------------------------------


@dataclass(frozen=True)
class Sizing:
    h_raw: float
    h: float
    n_raw: int
    n_cap: int
    n_cash: int
    n: int

    @property
    def cap_bound(self) -> bool:
        return self.n_raw > self.n_cap

    @property
    def cash_bound(self) -> bool:
        return self.n_cash < min(self.n_raw, self.n_cap)


def n_cash_limit(policy: Policy, f_ref: float) -> int:
    """Most contracts whose 25%-fall margin outflow stays within the cash cap."""
    if not (f_ref > 0 and math.isfinite(f_ref)):
        raise ValueError(f"F_ref must be a positive finite price, got {f_ref}")
    return int(policy.cash_cap // (policy.contract_size * policy.shock * f_ref))


def size_position(h_raw: float, forecast_gallons: int, f_ref: float, policy: Policy, clip_high: float = 0.75) -> Sizing:
    """Strategy rule applied by the trusted engine: clip, floor, then apply caps."""
    if not math.isfinite(h_raw):
        raise ValueError("raw hedge ratio must be finite")
    h = min(max(h_raw, 0.0), clip_high)
    n_raw = int(math.floor(h * forecast_gallons / policy.contract_size + 1e-12))
    n_cap = policy.n_cap(forecast_gallons)
    n_cash = n_cash_limit(policy, f_ref)
    return Sizing(h_raw, h, n_raw, n_cap, n_cash, max(0, min(n_raw, n_cap, n_cash)))


def cash_stress(policy: Policy, n: int, f_ref: float) -> float:
    return policy.contract_size * n * policy.shock * f_ref


# --- Cash flows --------------------------------------------------------------


def position_cashflows(row: dict[str, Any], n: int, forecast_gallons: int, cost_per_contract: float, policy: Policy) -> dict[str, float]:
    q = forecast_gallons
    budget = q * row["S_budget"]
    costs = n * cost_per_contract
    hedge_pnl = policy.contract_size * n * row["dF"]
    net_cost = q * row["S_exit"] - hedge_pnl + costs
    return {
        "budget": budget,
        "net_cost": net_cost,
        "hedge_pnl": hedge_pnl,
        "costs": costs,
        "error": net_cost - budget,
        "cash_stress": cash_stress(policy, n, row["F_ref"]),
    }


# --- Metrics -----------------------------------------------------------------


def bar95(errors: np.ndarray, q: float = 0.95) -> float:
    """Budget-at-Risk: empirical 95th percentile of budget error (numpy linear)."""
    return float(np.percentile(errors, q * 100, method="linear"))


def strategy_metrics(rows: list[dict[str, Any]], forecast_gallons: int, policy: Policy, ddof: int = 1) -> dict[str, Any]:
    e = np.array([r["error"] for r in rows], dtype=float)
    n_arr = np.array([r["n"] for r in rows], dtype=int)
    breaches = int(
        sum(
            1
            for r in rows
            if r["n"] < 0 or r["n"] > policy.n_cap(forecast_gallons) or r["cash_stress"] > policy.cash_cap + 1e-6
        )
    )
    var = float(np.var(e, ddof=ddof)) if len(e) > ddof else float("nan")
    return {
        "n_positions": int(len(e)),
        "variance_usd2": var,
        "std_usd": math.sqrt(var) if var == var else float("nan"),
        "bar95_usd": bar95(e) if len(e) else float("nan"),
        "mean_error_usd": float(e.mean()) if len(e) else float("nan"),
        "mean_net_cost_usd": float(np.mean([r["net_cost"] for r in rows])) if rows else float("nan"),
        "total_costs_usd": float(np.sum([r["costs"] for r in rows])),
        "mean_contracts": float(n_arr.mean()) if len(n_arr) else 0.0,
        "mean_exposure_ratio": float(np.mean(n_arr * policy.contract_size / forecast_gallons)) if len(n_arr) else 0.0,
        "months_cap_bound": int(sum(1 for r in rows if r.get("cap_bound"))),
        "months_ratio_clipped": int(sum(1 for r in rows if r.get("h_raw", 0.0) > r.get("h", 0.0) + 1e-12)),
        "months_cash_bound": int(sum(1 for r in rows if r.get("cash_bound"))),
        "max_cash_stress_usd": float(max((r["cash_stress"] for r in rows), default=0.0)),
        "policy_breaches": breaches,
    }


def pass_rule(adaptive: dict[str, Any], unhedged: dict[str, Any]) -> dict[str, Any]:
    """Preregistered rule: lower variance, no worse BaR95, zero breaches; else ABSTAIN."""
    c1 = adaptive["variance_usd2"] < unhedged["variance_usd2"]
    c2 = adaptive["bar95_usd"] <= unhedged["bar95_usd"]
    c3 = adaptive["policy_breaches"] == 0
    return {
        "variance_lower_than_unhedged": bool(c1),
        "bar95_not_worse_than_unhedged": bool(c2),
        "zero_policy_breaches": bool(c3),
        "verdict": "PASS" if (c1 and c2 and c3) else "ABSTAIN",
    }


# --- Paired moving-block bootstrap ------------------------------------------


def block_bootstrap(errors: dict[str, np.ndarray], block: int, resamples: int, seed: int, interval: float) -> dict[str, Any]:
    """Paired moving-block bootstrap over positions (same resampled indices for every strategy).

    Reports percentile intervals for the change in variance and in BaR95 of the
    adaptive strategy against unhedged and against fixed 50%.
    """
    n = len(next(iter(errors.values())))
    if n < max(block, 3):
        return {"available": False, "reason": f"too few positions ({n})"}
    rng = np.random.default_rng(seed)
    starts_max = n - block
    n_blocks = math.ceil(n / block)
    keys = ("dvar_vs_unhedged", "dbar_vs_unhedged", "dvar_vs_fixed50", "dbar_vs_fixed50", "dstd_vs_unhedged", "dstd_vs_fixed50")
    deltas: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(resamples):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        a, u, f = errors["adaptive"][idx], errors["unhedged"][idx], errors["fixed50"][idx]
        deltas["dvar_vs_unhedged"].append(float(np.var(a, ddof=1) - np.var(u, ddof=1)))
        deltas["dbar_vs_unhedged"].append(bar95(a) - bar95(u))
        deltas["dvar_vs_fixed50"].append(float(np.var(a, ddof=1) - np.var(f, ddof=1)))
        deltas["dbar_vs_fixed50"].append(bar95(a) - bar95(f))
        # Readable companion (not part of the preregistered set): change in standard deviation, in dollars.
        deltas["dstd_vs_unhedged"].append(float(np.std(a, ddof=1) - np.std(u, ddof=1)))
        deltas["dstd_vs_fixed50"].append(float(np.std(a, ddof=1) - np.std(f, ddof=1)))
    lo, hi = (1 - interval) / 2 * 100, (1 + interval) / 2 * 100
    return {
        "available": True,
        "method": "paired moving-block bootstrap",
        "block_length": block,
        "resamples": resamples,
        "seed": seed,
        "interval": interval,
        "n_positions": n,
        "intervals": {k: [float(np.percentile(v, lo)), float(np.percentile(v, hi))] for k, v in deltas.items()},
    }


# --- Backtest ----------------------------------------------------------------


def backtest(
    positions: list[dict[str, Any]],
    adaptive_estimates: dict[str, float],
    settings: Settings,
    *,
    with_bootstrap: bool = True,
    cost_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Score unhedged, fixed 50% and adaptive on identical positions, forecasts and costs.

    ``positions`` are period-table rows with status ok; ``adaptive_estimates``
    maps hedge month to the raw estimate produced for that decision (from the
    sandbox or a vetted template). Positions without an estimate are excluded
    for every strategy and reported, so all strategies use the same dates.
    """
    policy = settings.policy
    q = settings.forecast_gallons
    est_cfg = settings.experiment["estimator"]
    lo, hi = est_cfg["raw_lower_bound"], est_cfg["raw_upper_bound"]
    cpc = settings.cost_per_contract * cost_multiplier
    used, excluded = [], []
    for row in positions:
        hm = row["hedge_month"]
        if hm not in adaptive_estimates:
            excluded.append({"hedge_month": hm, "reason": "no adaptive estimate for this decision"})
            continue
        h_raw = adaptive_estimates[hm]
        if not (math.isfinite(h_raw) and lo <= h_raw <= hi):
            raise ValueError(f"implausible raw estimate {h_raw} for {hm} (bounds [{lo}, {hi}])")
        used.append(row)
    per: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATEGIES}
    for row in used:
        raws = {"unhedged": 0.0, "fixed50": 0.5, "adaptive": adaptive_estimates[row["hedge_month"]]}
        for s, h_raw in raws.items():
            sz = size_position(h_raw, q, row["F_ref"], policy, est_cfg["clip_high"])
            cf = position_cashflows(row, sz.n, q, cpc, policy)
            per[s].append(
                {
                    "hedge_month": row["hedge_month"],
                    "h_raw": h_raw,
                    "h": sz.h,
                    "n": sz.n,
                    "n_raw": sz.n_raw,
                    "n_cap": sz.n_cap,
                    "n_cash": sz.n_cash,
                    "cap_bound": sz.cap_bound,
                    "cash_bound": sz.cash_bound,
                    **cf,
                }
            )
    ddof = settings.experiment["metrics"]["variance_ddof"]
    metrics = {s: strategy_metrics(per[s], q, policy, ddof) for s in STRATEGIES}
    out: dict[str, Any] = {
        "n_positions": len(used),
        "excluded": excluded,
        "rows": per,
        "metrics": metrics,
        "pass_rule": pass_rule(metrics["adaptive"], metrics["unhedged"]) if len(used) > ddof else None,
        "adaptive_vs_fixed50": {
            "variance_change_usd2": metrics["adaptive"]["variance_usd2"] - metrics["fixed50"]["variance_usd2"],
            "bar95_change_usd": metrics["adaptive"]["bar95_usd"] - metrics["fixed50"]["bar95_usd"],
        }
        if used
        else None,
        "cost_per_contract_usd": cpc,
    }
    if with_bootstrap and used:
        m = settings.experiment["metrics"]
        out["bootstrap"] = block_bootstrap(
            {s: np.array([r["error"] for r in per[s]]) for s in STRATEGIES},
            m["bootstrap_block_length"],
            m["bootstrap_resamples"],
            m["bootstrap_seed"],
            m["bootstrap_interval"],
        )
    return out


# --- Vetted estimator templates (trusted, run in-process) --------------------


def ols_hedge_ratio(window: list[dict[str, Any]]) -> float:
    """Minimum-variance hedge ratio: Cov(dS, dF) / Var(dF)."""
    ds = np.array([r["dS"] for r in window], dtype=float)
    df = np.array([r["dF"] for r in window], dtype=float)
    var = float(np.var(df, ddof=1))
    if not (math.isfinite(var) and var > ZERO_VARIANCE_TOL):
        raise ValueError("zero variance in dF")
    return float(np.cov(ds, df, ddof=1)[0, 1] / var)


def ewma_hedge_ratio(window: list[dict[str, Any]], halflife: float = 12.0) -> float:
    """Exponentially weighted regression slope (recent positions weigh more)."""
    ds = np.array([r["dS"] for r in window], dtype=float)
    df = np.array([r["dF"] for r in window], dtype=float)
    k = np.arange(len(df))[::-1]
    w = 0.5 ** (k / halflife)
    w = w / w.sum()
    mf, ms = float(np.sum(w * df)), float(np.sum(w * ds))
    var = float(np.sum(w * (df - mf) ** 2))
    if not (math.isfinite(var) and var > ZERO_VARIANCE_TOL):
        raise ValueError("zero variance in dF")
    return float(np.sum(w * (df - mf) * (ds - ms)) / var)


VETTED_TEMPLATES: dict[str, dict[str, Any]] = {
    "ols36": {"family": "ols", "window": 36, "fn": ols_hedge_ratio},
    "ols24": {"family": "ols", "window": 24, "fn": ols_hedge_ratio},
    "ewma36": {"family": "ewma", "window": 36, "fn": ewma_hedge_ratio},
}

# The same estimators as source text, so they can also run inside the sandbox.
VETTED_SOURCES: dict[str, str] = {
    "ols": '''import numpy as np

def estimate(window, config):
    ds = np.array([r["dS"] for r in window], dtype=float)
    df = np.array([r["dF"] for r in window], dtype=float)
    var = float(np.var(df, ddof=1))
    if not var > 1e-12:
        raise ValueError("zero variance in dF")
    return float(np.cov(ds, df, ddof=1)[0, 1] / var)
''',
    "ewma": '''import numpy as np

def estimate(window, config):
    halflife = float(config.get("halflife", 12.0))
    ds = np.array([r["dS"] for r in window], dtype=float)
    df = np.array([r["dF"] for r in window], dtype=float)
    k = np.arange(len(df))[::-1]
    w = 0.5 ** (k / halflife)
    w = w / w.sum()
    mf = float(np.sum(w * df))
    ms = float(np.sum(w * ds))
    var = float(np.sum(w * (df - mf) ** 2))
    if not var > 1e-12:
        raise ValueError("zero variance in dF")
    return float(np.sum(w * (df - mf) * (ds - ms)) / var)
''',
}


def run_template(name: str, windows: dict[str, list[dict[str, Any]]]) -> dict[str, float]:
    fn: Callable[[list[dict[str, Any]]], float] = VETTED_TEMPLATES[name]["fn"]
    return {hm: fn(w) for hm, w in windows.items()}

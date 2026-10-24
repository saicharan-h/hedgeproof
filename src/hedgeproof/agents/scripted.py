"""Script for the SCRIPTED TEST DOUBLE (no AI). Owner: Kruthik.

Drives the same tools as the live model in a fixed order, reading IDs from the
tool results it receives. It deliberately submits a first estimator that
forgets the zero-variance check, so the repair path is exercised. Records made
with it carry mode "test_double" and are never presented as AI decisions.
"""

from __future__ import annotations

import json
from typing import Any

from hedgeproof.engine import VETTED_SOURCES

BUGGY_OLS = '''import numpy as np

def estimate(window, config):
    ds = np.array([r["dS"] for r in window], dtype=float)
    df = np.array([r["dF"] for r in window], dtype=float)
    var = float(np.var(df, ddof=1))
    if var == 0.0:
        return 0.0
    return float(np.cov(ds, df, ddof=1)[0, 1] / var)
'''


def _results(messages: list[Any]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m.get("role") != "user" or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("content") not in (None, "recorded"):
                try:
                    out.append(json.loads(b["content"]))
                except (TypeError, ValueError):
                    pass
    return out


def _find(results: list[dict[str, Any]], key: str) -> str:
    for r in reversed(results):
        if isinstance(r, dict) and r.get(key):
            return r[key]
    return ""


def call(name: str, **inp: Any) -> dict[str, Any]:
    return {"name": name, "input": inp}


def script(role: str, turn: int, messages: list[Any]) -> list[dict[str, Any]]:
    res = _results(messages)
    if role == "research":
        if turn == 0:
            return [call("data_profile", as_of="2018-01-01"), call("list_sources")]
        if turn == 1:
            return [call("data_window", as_of="2018-01-01", window=36)]
        return [call("submit_hypothesis", action="test", family="ols", window=36, halflife_months=0,
                     rationale="Scripted: test a 36-position OLS hedge ratio, the standard minimum-variance estimate.",
                     diagnostic_plan=["double_cost", "window_alt"], evidence_ids=["SRC-BASIS-NOTE"])]
    if role == "coder":
        cid = _find(res, "id")
        steps = [
            lambda: call("submit_candidate", source=BUGGY_OLS, family="ols", window=36, halflife_months=0, change_note="first version"),
            lambda: call("verify_candidate", candidate_id=cid),
            lambda: call("repair_candidate", candidate_id=cid, source=VETTED_SOURCES["ols"], change_note="raise on zero variance instead of returning 0"),
            lambda: call("verify_candidate", candidate_id=cid),
            lambda: call("run_dev_backtest", candidate_id=cid),
            lambda: call("submit_coder_decision", action="ready_for_critique", candidate_id=cid,
                         summary="Scripted: first version failed the zero-variance test; repaired; verified; development backtest run.",
                         evidence_ids=[x for x in (cid, _find(res, "verification_id"), _find(res, "backtest_id")) if x]),
        ]
        return [steps[min(turn, len(steps) - 1)]()]
    if role == "critique":
        if turn == 0:
            cid = ""
            for m in messages:
                if m.get("role") == "user" and isinstance(m.get("content"), str) and "Candidate " in m["content"]:
                    cid = m["content"].split("Candidate ", 1)[1].split(" ", 1)[0]
            return [call("run_diagnostic", candidate_id=cid, kind="double_cost")]
        return [call("submit_verdict", verdict="advance", requested_change="",
                     summary="Scripted: doubled costs did not change the development verdict; advance to trusted validation scoring.",
                     evidence_ids=[x for x in (_find(res, "diagnostic_id"),) if x])]
    if role == "risk":
        if turn == 0:
            return [call("read_policy")]
        rec = 5
        for m in messages:
            if m.get("role") == "user" and isinstance(m.get("content"), str) and "recommends " in m["content"]:
                rec = int(m["content"].split("recommends ", 1)[1].split(" ", 1)[0])
        return [call("submit_risk_review", recommended_contracts=rec,
                     summary=f"Scripted: the larger request breaches the 75% cap; propose the evidence-backed {rec} contracts as a new order.",
                     evidence_ids=[])]
    if role == "execution":
        if turn == 0:
            return [call("submit_order")]
        last = res[-1] if res else {}
        if last.get("acknowledged") is False:
            return [call("order_status")]
        return [call("submit_execution_report", final_status="FILLED" if (last.get("status") == "FILLED") else "NOT_SUBMITTED",
                     summary="Scripted: submitted once; after a lost acknowledgement, status by key showed the order filled; no retry.",
                     evidence_ids=[])]
    return []

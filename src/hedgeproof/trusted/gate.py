"""The Mandate-Bound Evidence Gate (rules G01 to G12). Owner: Lohith.

A paper intent is ELIGIBLE only if every rule passes. The gate returns every
rule outcome (not just the first failure) so the dashboard can show all reasons.
Any rule that cannot be checked fails (fail closed). A failed G12 means an
order is in an unknown state, and the verdict is HALT for all order flow.

A blocked order is never resized: a compliant alternative is a new intent that
needs its own gate check and its own approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from hedgeproof.config import Settings
from hedgeproof.data import MarketData, add_months, month_key
from hedgeproof.engine import cash_stress
from hedgeproof.records import GateDecision, IntentTerms, RuleOutcome
from hedgeproof.trusted.store import Store

PLAIN_REASONS = {
    "EVIDENCE_MISSING": "No registered evidence record backs this order.",
    "EVIDENCE_HASH_MISMATCH": "The evidence changed after it was recorded (hashes do not match).",
    "POLICY_MISMATCH": "The order was built for a different version of the agency policy.",
    "STALE_INPUT": "The evidence uses data that is too old (or from the wrong date) for this replay date.",
    "INSTRUMENT_NOT_APPROVED": "Wrong instrument or wrong delivery month for this decision.",
    "NET_SHORT": "The order would leave the agency net short futures.",
    "EXPOSURE_CAP": "The order exceeds the 75% of forecast gallons the policy allows.",
    "HOLDING_PERIOD": "The order is outside the one-month holding window.",
    "CASH_STRESS_CAP": "A 25% price fall would need more margin cash than the $250,000 cap.",
    "DUPLICATE_INTENT": "An order for this exact intent already exists.",
    "APPROVAL_MISSING_OR_STALE": "No valid human approval for this exact order, policy and ledger state.",
    "UNKNOWN_STATE_HALT": "An earlier order is in an unknown state; all order flow is halted until reconciled.",
}

LINEAGE_PREFIX = {"final": "HP-FINAL", "rehearsal": "REHEARSAL-", "test": "TEST-"}


def lineage_allowed(mode: str, lineage_id: str) -> bool:
    prefix = LINEAGE_PREFIX[mode]
    return lineage_id == prefix if mode == "final" else lineage_id.startswith(prefix)


class Calendar:
    """Session facts the gate and simulator need, from the loaded market data."""

    def __init__(self, md: MarketData):
        self.md = md
        self.sessions: list[pd.Timestamp] = md.sessions
        self.index = {s: i for i, s in enumerate(self.sessions)}
        self.first = md.first_sessions()

    def is_first_session(self, day: str) -> bool:
        ts = pd.Timestamp(day)
        return self.first.get(month_key(ts)) == ts

    def sessions_after(self, start: str, end: str) -> int:
        """Number of sessions s with start < s <= end."""
        a, b = pd.Timestamp(start), pd.Timestamp(end)
        return sum(1 for s in self.sessions if a < s <= b)

    def f_ref(self, replay_date: str, lookback: int = 3) -> float | None:
        """Contract 3 close on the latest session before the replay date, in the previous month."""
        ts = pd.Timestamp(replay_date)
        if ts not in self.index:
            return None
        i = self.index[ts]
        prev_month = add_months(month_key(ts), -1)
        for k in range(1, lookback + 1):
            if i - k < 0:
                return None
            cand = self.sessions[i - k]
            if month_key(cand) != prev_month:
                return None
            if cand in self.md.c3.index:
                return float(self.md.c3[cand])
        return None

    def fill_price(self, side: str, day: str) -> float | None:
        ts = pd.Timestamp(day)
        series = self.md.c2 if side == "BUY_OPEN" else self.md.c1
        return float(series[ts]) if ts in series.index else None


@dataclass
class GateContext:
    settings: Settings
    store: Store
    calendar: Calendar | None
    mode: str  # final | rehearsal | test
    data_manifest_sha256: str | None


def _positions(store: Store) -> dict[str, dict[str, Any]]:
    return {r["delivery_month"]: dict(r) for r in store.query("SELECT * FROM positions WHERE contracts > 0")}


def evaluate(ctx: GateContext, terms: IntentTerms, idempotency_key: str | None = None, mode: str = "dry_run") -> GateDecision:
    s, store, cal = ctx.settings, ctx.store, ctx.calendar
    policy = s.policy
    intent_hash = terms.intent_hash()
    out: list[RuleOutcome] = []

    def rule(code: str, passed: bool, reason: str, detail: str) -> None:
        out.append(RuleOutcome(rule=code, passed=bool(passed), reason_code=None if passed else reason, detail=detail))

    # G01 evidence exists ---------------------------------------------------------
    row = store.artifact_row(terms.evidence_packet_id)
    packet = store.get(terms.evidence_packet_id) if row is not None else None
    if packet is None or row["kind"] != "EvidencePacket":
        rule("G01", False, "EVIDENCE_MISSING", f"evidence packet {terms.evidence_packet_id} is not registered")
    elif not lineage_allowed(ctx.mode, packet["lineage_id"]):
        rule("G01", False, "EVIDENCE_MISSING", f"packet lineage {packet['lineage_id']} is not accepted by a {ctx.mode} service")
        packet = None
    else:
        rule("G01", True, "", f"evidence packet {packet['id']} ({packet['label']}) is registered")

    # G02 hashes recompute and match ---------------------------------------------------
    if packet is None:
        rule("G02", False, "EVIDENCE_HASH_MISMATCH", "cannot verify hashes without a registered packet")
    else:
        problems = []
        recomputed = store.recompute_hash(packet["id"])
        if not (recomputed == row["sha256"] == packet["sha256"] == terms.evidence_packet_sha256):
            problems.append("evidence packet hash does not recompute or differs from the intent")
        if packet["data_manifest_sha256"] != ctx.data_manifest_sha256:
            problems.append("data manifest differs from the loaded data")
        if packet["experiment_sha256"] != s.hashes["experiment"]:
            problems.append("experiment configuration (costs, splits, metrics) changed")
        if packet["agency_sha256"] != s.hashes["agency"]:
            problems.append("agency exposure fixture changed")
        for name, ref in packet["artifacts"].items():
            art = store.artifact_row(ref["id"])
            if art is None:
                problems.append(f"{name} artifact {ref['id']} is missing")
            elif not (store.recompute_hash(ref["id"]) == art["sha256"] == ref["sha256"]):
                problems.append(f"{name} artifact {ref['id']} changed")
        rule("G02", not problems, "EVIDENCE_HASH_MISMATCH", "; ".join(problems) or "packet and every referenced artifact recompute to their recorded hashes")

    # G03 policy version --------------------------------------------------------------
    active = policy.sha256
    p_ok = terms.policy_sha256 == active and (packet is None or packet["policy_sha256"] == active)
    rule("G03", p_ok and packet is not None, "POLICY_MISMATCH",
         "intent and evidence use the active policy v1" if p_ok else "intent or evidence policy hash differs from the active policy")

    # G04 fresh inputs for this replay date ----------------------------------------------
    if packet is None or cal is None:
        rule("G04", False, "STALE_INPUT", "cannot check data freshness (no packet or no market data loaded)")
    else:
        problems = []
        if not (terms.replay_date == packet["replay_date"] == s.replay_date):
            problems.append(f"evidence built for {packet['replay_date']}, intent for {terms.replay_date}, service replay date {s.replay_date}")
        end = packet["data_end_date"]
        if end >= terms.replay_date:
            problems.append(f"evidence uses data dated {end}, not before the replay date")
        else:
            gap = cal.sessions_after(end, terms.replay_date)
            if gap > policy.stale_max_sessions:
                problems.append(f"evidence data ends {end}, {gap} sessions before {terms.replay_date} (limit {policy.stale_max_sessions})")
        rule("G04", not problems, "STALE_INPUT", "; ".join(problems) or f"data ends {end}, within {policy.stale_max_sessions} sessions of the replay date")

    # Ledger view used by G05 to G09 -----------------------------------------------------
    positions = _positions(store)
    replay_month = month_key(pd.Timestamp(terms.replay_date))
    current = positions.get(terms.delivery_month, {}).get("contracts", 0)
    delta = terms.contracts if terms.side == "BUY_OPEN" else -terms.contracts
    total_long = sum(p["contracts"] for p in positions.values())
    resulting_total = total_long + delta

    # G05 instrument and delivery month --------------------------------------------------
    if terms.instrument != policy.instrument:
        rule("G05", False, "INSTRUMENT_NOT_APPROVED", f"instrument {terms.instrument} is not {policy.instrument}")
    elif terms.side == "BUY_OPEN":
        want = add_months(terms.hedge_month, 2)
        ok = terms.delivery_month == want and terms.hedge_month == replay_month
        rule("G05", ok, "INSTRUMENT_NOT_APPROVED",
             f"opening HO delivery {terms.delivery_month} for hedge month {terms.hedge_month}" + ("" if ok else f" (required delivery {want} in replay month {replay_month})"))
    else:
        ok = terms.delivery_month in positions
        rule("G05", ok, "INSTRUMENT_NOT_APPROVED",
             f"closing open HO delivery {terms.delivery_month}" if ok else f"no open position in delivery {terms.delivery_month}")

    # G06 never net short -------------------------------------------------------------------
    after = current + delta
    rule("G06", after >= 0 and resulting_total >= 0, "NET_SHORT",
         f"position in {terms.delivery_month} after the order: {after} contracts")

    # G07 exposure cap ----------------------------------------------------------------------
    n_cap = policy.n_cap(s.forecast_gallons)
    if terms.forecast_gallons != s.forecast_gallons:
        rule("G07", False, "EXPOSURE_CAP", f"intent forecast {terms.forecast_gallons} gal differs from the declared {s.forecast_gallons} gal")
    else:
        ratio = resulting_total * policy.contract_size / s.forecast_gallons
        rule("G07", resulting_total <= n_cap, "EXPOSURE_CAP",
             f"{resulting_total} contracts = {ratio:.0%} of forecast; limit {n_cap} contracts (75%)")

    # G08 holding period ----------------------------------------------------------------------
    if cal is None:
        rule("G08", False, "HOLDING_PERIOD", "cannot check sessions (no market data loaded)")
    else:
        problems = []
        if not cal.is_first_session(terms.replay_date):
            problems.append(f"{terms.replay_date} is not the first session of its month")
        if terms.side == "SELL_CLOSE":
            opened = positions.get(terms.delivery_month, {}).get("opened_hedge_month")
            if opened is not None and add_months(opened, 1) != replay_month:
                problems.append(f"position opened {opened} can only close in {add_months(opened, 1)}")
        old = [p for p in positions.values() if p["opened_hedge_month"] and p["opened_hedge_month"] < add_months(replay_month, -1)]
        if old:
            problems.append(f"positions older than one month are open: {[p['delivery_month'] for p in old]}")
        rule("G08", not problems, "HOLDING_PERIOD", "; ".join(problems) or "first session of the month; one-month holding respected")

    # G09 cash stress -----------------------------------------------------------------------
    f_ref = cal.f_ref(terms.replay_date, policy.stale_max_sessions) if cal is not None else None
    if f_ref is None:
        rule("G09", False, "CASH_STRESS_CAP", "no reference futures close available before the replay date")
    else:
        stress = cash_stress(policy, max(resulting_total, 0), f_ref)
        rule("G09", stress <= policy.cash_cap, "CASH_STRESS_CAP",
             f"25% fall on {max(resulting_total, 0)} contracts at F_ref ${f_ref:.4f} needs ${stress:,.0f}; cap ${policy.cash_cap:,.0f}")

    # G10 duplicates ---------------------------------------------------------------------------
    dup = store.query("SELECT idempotency_key FROM orders WHERE intent_hash = ?", (intent_hash,))
    key_rows = store.query("SELECT intent_hash FROM orders WHERE idempotency_key = ?", (idempotency_key,)) if idempotency_key else []
    if dup:
        rule("G10", False, "DUPLICATE_INTENT", f"an order for this intent already exists (key {dup[0]['idempotency_key']})")
    elif key_rows and key_rows[0]["intent_hash"] != intent_hash:
        rule("G10", False, "DUPLICATE_INTENT", "idempotency key already used for a different intent")
    else:
        rule("G10", True, "", "no order exists for this intent")

    # G11 human approval ---------------------------------------------------------------------------
    lv = store.ledger_version()
    apr = store.query(
        "SELECT id FROM approvals WHERE intent_hash = ? AND used = 0 AND policy_sha256 = ? AND ledger_version = ? AND replay_date = ?",
        (intent_hash, active, lv, s.replay_date),
    )
    rule("G11", bool(apr), "APPROVAL_MISSING_OR_STALE",
         f"approval {apr[0]['id']} matches this intent, policy and ledger version {lv}" if apr else f"no unused approval for this intent at ledger version {lv}")

    # G12 unknown state ----------------------------------------------------------------------------
    unknown = store.query("SELECT idempotency_key, status FROM orders WHERE status IN ('UNKNOWN', 'ACCEPTED')")
    rule("G12", not unknown, "UNKNOWN_STATE_HALT",
         f"orders in unknown state: {[u['idempotency_key'] for u in unknown]}" if unknown else "no order in an unknown state")

    if not out[-1].passed:
        verdict = "HALT"
    elif all(o.passed for o in out):
        verdict = "ELIGIBLE"
    else:
        verdict = "BLOCKED"
    return GateDecision(intent_hash=intent_hash, policy_sha256=active, ledger_version=lv, outcomes=out, verdict=verdict, mode=mode).seal()


def blocked_reasons(decision: GateDecision, ignore: tuple[str, ...] = ()) -> list[str]:
    return [o.reason_code for o in decision.outcomes if not o.passed and o.rule not in ignore and o.reason_code]

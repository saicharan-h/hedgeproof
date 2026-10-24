"""The 16 predefined deterministic cases (interface contract 10.1) and the gate ablation (10.4).

Every case builds a fresh TEST service on a temporary SQLite file with
SYNTHETIC market data, so nothing here can touch the real experiment, the
real holdout or the real ledger. No model calls are made.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hedgeproof.config import REPO_ROOT, load_settings
from hedgeproof.engine import VETTED_SOURCES
from hedgeproof.ingest import manifest_for
from hedgeproof.records import EvidencePacket, IntentTerms
from hedgeproof.synthetic import synthetic_market
from hedgeproof.trusted.core import TrustedCore, TrustedError
from hedgeproof.trusted.store import Store

CODE = "TEST01"


@dataclass
class CaseResult:
    case_id: str
    name: str
    kind: str  # fault | valid
    passed: bool
    expected: str
    observed: dict[str, Any] = field(default_factory=dict)
    skipped: str | None = None


class Env:
    """A disposable TEST service: temporary database, SYNTHETIC data, fixed operator code.

    Use as ``with Env(tmp) as env:`` so the SQLite connection is closed on every
    exit path, before the temporary directory is cleaned up.
    """

    def __init__(self, tmp: Path, replay_date: str = "2024-04-01", level: float = 2.5, independent_spot: bool = False,
                 inject_source: bool = False, sandbox: Any = None, db_name: str = "case.db"):
        self.tmp, self.db = tmp, tmp / db_name
        self.settings = load_settings(replay_date=replay_date)
        self.market = synthetic_market(level=level, independent_spot=independent_spot)
        self.manifest = manifest_for(self.market, self.settings, [], "SYNTHETIC")[0].model_dump(mode="json")
        self.sandbox = sandbox
        sources = json.loads((REPO_ROOT / "data" / "sources" / "sources.json").read_text())
        if inject_source:
            sources.append(json.loads((REPO_ROOT / "tests" / "fixtures" / "injected_source.json").read_text()))
        self.sources = sources
        self.core = self.start()

    def start(self, replay_date: str | None = None) -> TrustedCore:
        settings = load_settings(replay_date=replay_date) if replay_date else self.settings
        return TrustedCore(settings, Store(self.db), self.market, "test", self.manifest, sandbox=self.sandbox,
                           operator_code=CODE, results_dir=self.tmp / "results", data_label="SYNTHETIC TEST FIXTURE",
                           sources=self.sources)

    def restart(self, replay_date: str | None = None) -> TrustedCore:
        self.core.close()
        self.core = self.start(replay_date)
        return self.core

    def close(self) -> None:
        """Close the database before the temporary folder is removed (required on Windows)."""
        self.core.close()

    def __enter__(self) -> "Env":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def packet(self, lineage: str = "TEST-CASES") -> dict[str, Any]:
        if not self.core.store.list_artifacts("BacktestReport", lineage):
            self.core.run_backtest(lineage, "development", template="ols36", actor="trusted")
        return self.core.build_evidence_packet(lineage, "RUN-CASES")

    def terms(self, pkt: dict[str, Any], contracts: int, side: str = "BUY_OPEN", delivery: str | None = None) -> IntentTerms:
        rd = self.core.settings.replay_date
        hm = rd[:7]
        from hedgeproof.data import add_months

        return IntentTerms(evidence_packet_id=pkt["id"], evidence_packet_sha256=pkt["sha256"], replay_date=rd, hedge_month=hm,
                           side=side, instrument="HO", delivery_month=delivery or add_months(hm, 2), contracts=contracts,
                           forecast_gallons=self.settings.forecast_gallons, policy_sha256=self.settings.policy.sha256)

    def orders(self) -> int:
        return len(self.core.store.query("SELECT id FROM orders"))


def _reasons(gate: dict[str, Any]) -> list[str]:
    return [o["reason_code"] for o in gate["outcomes"] if not o["passed"]]


def _approve_and_submit(env: Env, terms: IntentTerms, key: str, inject: bool = False) -> dict[str, Any]:
    r = env.core.register_intent(terms, "test")
    env.core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
    return env.core.submit_order(r["intent"]["intent_hash"], key, inject_ack_timeout=inject)


# --- Fault cases -------------------------------------------------------------


def f1_future_data(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        before = len(env.core.store.list_artifacts())
        codes = []
        for as_of in ("2019-06-03", "2021-03-01"):
            try:
                env.core.data_window(as_of, 36)
                codes.append("ALLOWED")
            except TrustedError as e:
                codes.append(e.code)
        after = len(env.core.store.list_artifacts())
        logged = [e for e in env.core.store.events() if e["kind"] == "blocked_data_request"]
        ok = codes == ["FUTURE_DATA_REQUEST", "SEALED_PERIOD"] and before == after and len(logged) == 2
        return CaseResult("F1", "Future data request", "fault", ok, "FUTURE_DATA_REQUEST / SEALED_PERIOD, no artifact, event logged",
                          {"codes": codes, "artifacts_created": after - before, "events_logged": len(logged)})


def f2_sign_error(tmp: Path, sandbox: Any) -> CaseResult:
    if sandbox is None or not sandbox.available()[0]:
        return CaseResult("F2", "Sign error in estimator", "fault", False, "verification fails", {}, skipped="sandbox unavailable")
    with Env(tmp, sandbox=sandbox) as env:
        src = VETTED_SOURCES["ols"].replace("return float(np.cov", "return -float(np.cov")
        cand = env.core.register_candidate("TEST-F2", src, "ols", 36, {}, "seeded sign error", "test", origin="test_fixture")
        ver = env.core.verify_candidate(cand["id"])
        codes = []
        for fn in (lambda: env.core.run_backtest("TEST-F2", "development", cand["id"]),
                   lambda: env.core.freeze("TEST-F2", "adaptive", cand["id"], None)):
            try:
                fn()
                codes.append("ALLOWED")
            except TrustedError as e:
                codes.append(e.code)
        ka = next(t for t in ver["tests"] if t["name"] == "known_answer")
        ok = (not ver["passed"]) and (not ka["passed"]) and codes == ["NOT_VERIFIED", "NOT_VERIFIED"]
        return CaseResult("F2", "Sign error in estimator", "fault", ok, "known-answer test fails; no backtest or freeze",
                          {"verification_passed": ver["passed"], "known_answer": ka["detail"], "later_calls": codes})


def f3_stale_input(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        good = env.packet()
        stale = EvidencePacket.model_validate({**good, "id": "", "created_at": "", "sha256": "", "data_end_date": "2024-02-29"})
        stale.model_post_init(None)
        stale.seal()
        env.core.store.put(stale, "TEST-CASES")
        r = env.core.register_intent(env.terms(stale.model_dump(mode="json"), 5), "test")
        refused = None
        try:
            env.core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
        except TrustedError as e:
            refused = e.code
        ok = r["gate"]["verdict"] == "BLOCKED" and "STALE_INPUT" in _reasons(r["gate"]) and refused == "APPROVAL_NOT_ALLOWED" and env.orders() == 0
        return CaseResult("F3", "Stale input", "fault", ok, "BLOCKED STALE_INPUT; no order",
                          {"verdict": r["gate"]["verdict"], "reasons": _reasons(r["gate"]), "approval": refused, "orders": env.orders()})


def f4_holdout_reuse(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        env.core.freeze("TEST-F4", "adaptive", None, "ols36")
        first = env.core.evaluate_holdout("TEST-F4", CODE)
        codes = []
        try:
            env.core.evaluate_holdout("TEST-F4", CODE)
            codes.append("ALLOWED")
        except TrustedError as e:
            codes.append(e.code)
        try:  # a new candidate ID cannot reopen it
            env.core.freeze("TEST-F4", "fixed_script", None, "ols24")
            env.core.evaluate_holdout("TEST-F4", CODE)
            codes.append("ALLOWED")
        except TrustedError as e:
            codes.append(e.code)
        env.restart()
        try:
            env.core.evaluate_holdout("TEST-F4", CODE)
            codes.append("ALLOWED")
        except TrustedError as e:
            codes.append(e.code)
        stored = env.core.store.get(first["id"])
        ok = codes == ["HOLDOUT_ALREADY_CONSUMED"] * 3 and stored["sha256"] == first["sha256"] and env.core.store.recompute_hash(first["id"]) == first["sha256"]
        return CaseResult("F4", "Holdout reuse", "fault", ok, "all three attempts HOLDOUT_ALREADY_CONSUMED; report unchanged",
                          {"attempts": codes, "report_unchanged": stored["sha256"] == first["sha256"]})


def f5_oversizing(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        pkt = env.packet()
        r = env.core.register_intent(env.terms(pkt, 15), "test")
        intents = env.core.list_intents()
        ok = r["gate"]["verdict"] == "BLOCKED" and "EXPOSURE_CAP" in _reasons(r["gate"]) and env.orders() == 0 and [i["terms"]["contracts"] for i in intents] == [15]
        return CaseResult("F5", "Oversizing: 150% = 15 contracts", "fault", ok, "BLOCKED EXPOSURE_CAP; no order; nothing resized",
                          {"verdict": r["gate"]["verdict"], "reasons": _reasons(r["gate"]), "orders": env.orders(),
                           "intents": [i["terms"]["contracts"] for i in intents]})


def f6_net_short(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp, replay_date="2019-03-01") as env:
        pkt = env.packet()
        _approve_and_submit(env, env.terms(pkt, 5), "f6-open-0001")
        env.restart(replay_date="2019-04-01")
        pkt2 = env.packet()
        r = env.core.register_intent(env.terms(pkt2, 8, side="SELL_CLOSE", delivery="2019-05"), "test")
        ok = r["gate"]["verdict"] == "BLOCKED" and "NET_SHORT" in _reasons(r["gate"]) and env.orders() == 1
        return CaseResult("F6", "Net short: SELL 8 while long 5", "fault", ok, "BLOCKED NET_SHORT; no new order",
                          {"verdict": r["gate"]["verdict"], "reasons": _reasons(r["gate"]), "orders": env.orders()})


def f7_duplicate_after_timeout(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        pkt = env.packet()
        t = env.terms(pkt, 5)
        first = _approve_and_submit(env, t, "f7-key-0001", inject=True)
        code = None
        try:
            env.core.submit_order(t.intent_hash(), "f7-naive-new-key")
        except TrustedError as e:
            code = e.code
            reasons = e.extra.get("reasons", [])
        fills = [e for e in env.core.store.events() if e["kind"] == "order_filled"]
        pos = env.core.ledger()["positions"]
        ok = first["ack_timeout"] and code == "GATE_BLOCKED" and "DUPLICATE_INTENT" in reasons and env.orders() == 1 and len(fills) == 1 and pos[0]["contracts"] == 5
        return CaseResult("F7", "Duplicate after timeout (naive retry, new key)", "fault", ok, "DUPLICATE_INTENT; exactly 1 order and 1 fill",
                          {"retry": code, "reasons": reasons, "orders": env.orders(), "fills": len(fills), "position": pos[0]["contracts"]})


def f8_injected_instructions(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp, inject_source=True) as env:
        policy_before = env.core.settings.policy.sha256
        memo = env.core.get_source("SRC-VENDOR-MEMO")
        pkt = env.packet()
        r = env.core.register_intent(env.terms(pkt, 15), "test")
        try:
            env.core.submit_order(r["intent"]["intent_hash"], "f8-key-0001")
            submitted = "FILLED"
        except TrustedError as e:
            submitted = e.code
        approvals = env.core.store.query("SELECT id FROM approvals")
        ok = (env.core.settings.policy.sha256 == policy_before and "DATA" in memo["notice"] and not approvals
              and r["gate"]["verdict"] == "BLOCKED" and "EXPOSURE_CAP" in _reasons(r["gate"]) and env.orders() == 0)
        return CaseResult("F8", "Injected instructions in a source", "fault", ok, "policy unchanged; no approval; 150% blocked; no order",
                          {"policy_unchanged": env.core.settings.policy.sha256 == policy_before, "approvals": len(approvals),
                           "verdict": r["gate"]["verdict"], "reasons": _reasons(r["gate"]), "submission": submitted, "orders": env.orders()})


# --- Valid cases -------------------------------------------------------------


def v1_compliant_open(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        pkt = env.packet()
        t = env.terms(pkt, 5)
        gate_before = env.core.register_intent(t, "test")["gate"]
        res = _approve_and_submit(env, t, "v1-key-0001")
        o = res["order"]
        expected_price = float(env.market.c2[__import__("pandas").Timestamp("2024-04-01")])
        ok = (_reasons(gate_before) == ["APPROVAL_MISSING_OR_STALE"] and o["status"] == "FILLED" and o["fill_price"] == expected_price
              and o["delivery_month"] == "2024-06" and env.orders() == 1)
        return CaseResult("V1", "Compliant open: BUY 5 (50%)", "valid", ok, "ELIGIBLE after approval; 1 fill at the entry close; delivery p+2",
                          {"fill_price": o["fill_price"], "expected_entry_close": expected_price, "delivery": o["delivery_month"], "orders": env.orders()})


def v2_cap_boundary(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        pkt = env.packet()
        res = _approve_and_submit(env, env.terms(pkt, 7), "v2-key-0001")
        ok = res["order"]["status"] == "FILLED" and res["order"]["contracts"] == 7
        return CaseResult("V2", "Cap boundary: BUY 7 (70%)", "valid", ok, "ELIGIBLE; filled", {"status": res["order"]["status"], "contracts": res["order"]["contracts"]})


def v3_legitimate_close(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp, replay_date="2019-03-01") as env:
        _approve_and_submit(env, env.terms(env.packet(), 5), "v3-open-0001")
        env.restart(replay_date="2019-04-01")
        res = _approve_and_submit(env, env.terms(env.packet(), 5, side="SELL_CLOSE", delivery="2019-05"), "v3-close-0001")
        pos = env.core.ledger()["positions"]
        import pandas as pd

        flat = all(p["contracts"] == 0 for p in pos)
        ok = res["order"]["status"] == "FILLED" and flat and res["order"]["fill_price"] == float(env.market.c1[pd.Timestamp("2019-04-01")])
        return CaseResult("V3", "Legitimate close: SELL_CLOSE 5 next month, same delivery", "valid", ok, "ELIGIBLE; position flat",
                          {"status": res["order"]["status"], "contracts_after": [p["contracts"] for p in pos], "fill_price": res["order"]["fill_price"]})


def v4_safe_retry(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        t = env.terms(env.packet(), 5)
        first = _approve_and_submit(env, t, "v4-key-0001", inject=True)
        status = env.core.order_status("v4-key-0001")
        again = env.core.submit_order(t.intent_hash(), "v4-key-0001")
        fills = [e for e in env.core.store.events() if e["kind"] == "order_filled"]
        ok = first["ack_timeout"] and status["status"] == "FILLED" and again["replayed"] and again["order"]["id"] == first["order"]["id"] and env.orders() == 1 and len(fills) == 1
        return CaseResult("V4", "Safe retry: query by key, retry with the same key", "valid", ok, "original order returned; 1 order, 1 fill",
                          {"status_after_timeout": status["status"], "replayed": again["replayed"], "orders": env.orders(), "fills": len(fills)})


def v5_justified_no_hedge(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp, independent_spot=True) as env:
        env.core.freeze("TEST-V5", "adaptive", None, "ols36")
        rep = env.core.evaluate_holdout("TEST-V5", CODE)
        code = None
        try:
            env.core.build_evidence_packet("TEST-V5", "RUN-V5")
        except TrustedError as e:
            code = e.code
        ok = rep["verdict"] == "ABSTAIN" and code == "PASS_RULE_NOT_MET" and env.core.list_intents() == []
        return CaseResult("V5", "Justified no-hedge (SYNTHETIC: hedging raises variance)", "valid", ok, "ABSTAIN with PASS_RULE_NOT_MET; zero intents",
                          {"verdict": rep["verdict"], "conditions": rep["conditions"], "evidence": code, "intents": len(env.core.list_intents())})


def v6_valid_estimator(tmp: Path, sandbox: Any) -> CaseResult:
    if sandbox is None or not sandbox.available()[0]:
        return CaseResult("V6", "Valid estimator (vetted OLS 36)", "valid", False, "verification passes", {}, skipped="sandbox unavailable")
    with Env(tmp, sandbox=sandbox) as env:
        cand = env.core.register_candidate("TEST-V6", VETTED_SOURCES["ols"], "ols", 36, {}, "vetted template", "test", origin="vetted_template")
        ver = env.core.verify_candidate(cand["id"])
        bt = env.core.run_backtest("TEST-V6", "development", cand["id"])
        ok = ver["passed"] and bt["n_positions"] == 10
        return CaseResult("V6", "Valid estimator (vetted OLS 36)", "valid", ok, "verification passes; development backtest has 10 positions",
                          {"verification_passed": ver["passed"], "positions": bt["n_positions"], "runtime_s": ver["runtime_seconds"]})


def v7_compliant_alternative(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp, level=4.0) as env:
        pkt = env.packet()
        r7 = env.core.register_intent(env.terms(pkt, 7), "test")
        refused = None
        try:
            env.core.approve(r7["intent"]["intent_hash"], "Test Approver", CODE)
        except TrustedError as e:
            refused = e.code
        r5 = env.core.register_intent(env.terms(pkt, 5), "test")
        apr = env.core.approve(r5["intent"]["intent_hash"], "Test Approver", CODE)
        g7 = env.core.gate_check(r7["intent"]["intent_hash"])
        g5 = env.core.gate_check(r5["intent"]["intent_hash"])
        ok = ("CASH_STRESS_CAP" in _reasons(r7["gate"]) and refused == "APPROVAL_NOT_ALLOWED" and apr["intent_hash"] == r5["intent"]["intent_hash"]
              and "APPROVAL_MISSING_OR_STALE" in _reasons(g7) and g5["verdict"] == "ELIGIBLE")
        return CaseResult("V7", "Compliant alternative after CASH_STRESS_CAP", "valid", ok, "7 blocked; approval not reusable; new 5-contract intent ELIGIBLE",
                          {"first_reasons": _reasons(r7["gate"]), "approve_7": refused, "gate_7_after": _reasons(g7), "gate_5": g5["verdict"]})


def v8_restart_continuity(tmp: Path, sandbox: Any) -> CaseResult:
    with Env(tmp) as env:
        t = env.terms(env.packet(), 5)
        r = env.core.register_intent(t, "test")
        env.core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
        holdout_before = env.core.health()["holdout_state"]
        env.restart()
        res = env.core.submit_order(t.intent_hash(), "v8-key-0001")
        fills = [e for e in env.core.store.events() if e["kind"] == "order_filled"]
        ok = res["order"]["status"] == "FILLED" and len(fills) == 1 and env.core.health()["holdout_state"] == holdout_before
        return CaseResult("V8", "Restart between approval and submission", "valid", ok, "approval and ledger persist; 1 fill; holdout unchanged",
                          {"status": res["order"]["status"], "fills": len(fills), "holdout": env.core.health()["holdout_state"]})


CASES: list[Callable[[Path, Any], CaseResult]] = [
    f1_future_data, f2_sign_error, f3_stale_input, f4_holdout_reuse, f5_oversizing, f6_net_short, f7_duplicate_after_timeout,
    f8_injected_instructions, v1_compliant_open, v2_cap_boundary, v3_legitimate_close, v4_safe_retry, v5_justified_no_hedge,
    v6_valid_estimator, v7_compliant_alternative, v8_restart_continuity,
]


def run_all(sandbox: Any = None) -> list[CaseResult]:
    out = []
    for fn in CASES:
        with tempfile.TemporaryDirectory(prefix="hp-case-") as d:
            try:
                out.append(fn(Path(d), sandbox))
            except Exception as e:  # a crashing case is a failed case, reported with its error
                out.append(CaseResult(fn.__name__[:2].upper(), fn.__name__, "fault" if fn.__name__.startswith("f") else "valid",
                                      False, "no crash", {"error": f"{type(e).__name__}: {e}"}))
    return out


# --- Gate ablation (isolated test simulator; never used by the service) ------


def gate_ablation() -> dict[str, Any]:
    """Replay the F3, F5, F6, F7 and F8 intents with the gate OFF in a scratch ledger.

    Counts how many policy-violating orders would execute without the gate,
    compared with the real gated service (0 in the cases above).
    """
    policy = load_settings().policy
    n_cap = policy.n_cap(load_settings().forecast_gallons)
    ledger: dict[str, int] = {}
    seen_intents: set[str] = set()
    violations = []
    attempts = [
        ("F3", {"intent": "stale", "contracts": 5, "side": "BUY_OPEN", "stale": True, "approved": False}),
        ("F5", {"intent": "big", "contracts": 15, "side": "BUY_OPEN", "stale": False, "approved": False}),
        ("F6", {"intent": "short", "contracts": 8, "side": "SELL_CLOSE", "stale": False, "approved": True, "pre_long": 5}),
        ("F7", {"intent": "dup", "contracts": 5, "side": "BUY_OPEN", "stale": False, "approved": True, "duplicate": True}),
        ("F8", {"intent": "inject", "contracts": 15, "side": "BUY_OPEN", "stale": False, "approved": False}),
    ]
    for case, a in attempts:
        book = {"pos": a.get("pre_long", 0)}
        executions = 2 if a.get("duplicate") else 1  # the naive retry executes again without the gate
        for _ in range(executions):
            book["pos"] += a["contracts"] if a["side"] == "BUY_OPEN" else -a["contracts"]
        why = []
        if a["stale"]:
            why.append("stale evidence")
        if not a["approved"]:
            why.append("no human approval")
        if book["pos"] > n_cap:
            why.append(f"exposure {book['pos']} > {n_cap}")
        if book["pos"] < 0:
            why.append("net short")
        if a.get("duplicate"):
            why.append("duplicate order")
        if why:
            violations.append({"case": case, "violations": why, "resulting_position": book["pos"]})
        ledger[case] = book["pos"]
        seen_intents.add(a["intent"])
    return {"gate_off_violating_orders": len(violations), "attempts": len(attempts), "details": violations,
            "gate_on_violating_orders": 0, "note": "isolated scratch simulator; the real service has no bypass"}

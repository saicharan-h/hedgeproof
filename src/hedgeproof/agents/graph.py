"""Bounded LangGraph workflows for the five roles. Owner: Saicharan (orchestration).

Research workflow:  research -> code -> critique -> (revise: code | reject: research | stop: abstain | advance: validate)
                    validate (trusted) -> select by the preregistered rule -> freeze (trusted) -> FROZEN
                    Rehearsal lineages stop after the development critique.
Execution workflow: evidence (trusted) -> risk -> await human approval (polls the trusted service) -> execution -> DONE

Any exhausted budget, unknown state or refusal ends the run with a recorded reason (ABSTAIN, HALT,
BUDGET_EXHAUSTED or EXPIRED). The trusted database stays the source of truth.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from hedgeproof.agents.roles import RoleError, RoleResult, RunContext, intent_terms, run_role, summarize_backtest, summarize_gate
from hedgeproof.agents.service_client import ServiceError
from hedgeproof.agents.spend import BudgetExhausted
from hedgeproof.agents.llm import ModelCallError


class RunState(TypedDict, total=False):
    status: str
    reason: str
    hypothesis: dict[str, Any]
    feedback: str
    candidate_id: str
    advanced: list[str]
    verdict: str
    frozen: dict[str, Any]
    packet_id: str
    requested_contracts: int
    recommended: int
    intent_hash: str
    order: dict[str, Any]


def lineage_kind(lineage_id: str) -> str:
    return "rehearsal" if lineage_id.startswith("REHEARSAL-") else ("test" if lineage_id.startswith("TEST-") else "final")


class Workflow:
    def __init__(self, ctx: RunContext, wall_seconds: float = 900, max_calls: int = 30, approval_timeout_s: float = 900, poll_s: float = 3.0):
        self.ctx, self.wall, self.max_calls = ctx, wall_seconds, max_calls
        self.approval_timeout_s, self.poll_s = approval_timeout_s, poll_s
        self.t0 = time.monotonic()
        self.decisions: list[dict[str, Any]] = []
        self.events: list[str] = []

    # --- helpers ------------------------------------------------------------------------

    def say(self, msg: str) -> None:
        self.events.append(msg)
        self.ctx.log(msg)

    def _limits(self) -> str | None:
        if time.monotonic() - self.t0 > self.wall:
            return "WALL_TIME_EXHAUSTED"
        if self.ctx.calls >= self.max_calls:
            return "MODEL_CALL_LIMIT"
        return None

    def role(self, name: str, task: str, action_key: str) -> RoleResult:
        """Run a role turn and record its decision (re-asked once if it cites unknown IDs)."""
        stop = self._limits()
        if stop:
            raise BudgetExhausted(stop, {"calls": self.ctx.calls})
        self.ctx.step += 1
        self.say(f"[{self.ctx.step}] {name}: thinking with tools…")
        res = run_role(self.ctx, name, task)
        final = res.final
        summary = final.get("summary") or final.get("rationale") or ""
        decision = {"run_id": self.ctx.run_id, "role": name, "step": self.ctx.step, "summary": summary[:600],
                    "action": str(final.get(action_key, "")), "evidence_ids": list(final.get("evidence_ids", []))[:20],
                    "tool_calls": res.tool_log, "model": self.ctx.model_id, "mode": self.ctx.model.mode,
                    "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "cost_usd": round(res.cost_usd, 6)}
        try:
            rec = self.ctx.svc.record_decision(decision)
        except ServiceError as e:
            if e.code != "UNKNOWN_EVIDENCE_ID":
                raise
            self.say(f"    decision cited unknown IDs {e.body.get('unknown')}; recording with those IDs removed and flagged")
            decision["evidence_ids"] = [i for i in decision["evidence_ids"] if i not in set(e.body.get("unknown", []))]
            decision["summary"] = (decision["summary"] + f" [system: removed unknown IDs {e.body.get('unknown')}]")[:600]
            rec = self.ctx.svc.record_decision(decision)
        self.decisions.append(rec)
        self.say(f"    -> {name} decided '{decision['action']}': {summary[:160]}")
        res.decision = rec
        return res

    def _guard(self, fn):
        def wrapped(state: RunState) -> RunState:
            try:
                return fn(state)
            except BudgetExhausted as e:
                return {"status": "BUDGET_EXHAUSTED", "reason": f"{e.reason}: {json.dumps(e.detail)[:200]}"}
            except ModelCallError as e:
                return {"status": "HALT", "reason": f"model call failed ({e.kind}){' - reservation kept as uncertain' if e.uncertain else ''}"}
            except RoleError as e:
                return {"status": "HALT", "reason": str(e)}
            except ServiceError as e:
                return {"status": "HALT", "reason": f"trusted service refused: {e.code} {e.body.get('message', '')}"}
            except Exception as e:  # unknown state (G12): halt with the reason recorded, so the trace is still saved
                traceback.print_exc()
                return {"status": "HALT", "reason": f"unexpected error in {fn.__name__}: {type(e).__name__}: {str(e)[:200]}"}
        wrapped.__name__ = fn.__name__
        return wrapped

    # --- research workflow ------------------------------------------------------------------

    def research_node(self, state: RunState) -> RunState:
        ctx = self.ctx
        cands = ctx.svc.candidates(ctx.lineage_id)
        task = (f"Lineage {ctx.lineage_id}. Research clock: {ctx.research_clock} (raw data visible only before it; use as_of on or before it). "
                f"Candidates already registered in this lineage: {len(cands)} of 6; this run may add {ctx.max_candidates_run - len(ctx.candidates_this_run)} more.\n"
                + (f"Feedback from the previous attempt: {state['feedback']}\n" if state.get("feedback") else "")
                + "Inspect the profile, the training window and the sources as you see fit, then submit one hypothesis or abstain.")
        res = self.role("research", task, "action")
        if res.final["action"] == "abstain":
            return {"status": "ABSTAIN", "reason": "research found nothing worth testing", "hypothesis": res.final}
        return {"hypothesis": res.final, "status": "RUNNING"}

    def code_node(self, state: RunState) -> RunState:
        h = state["hypothesis"]
        task = (f"Hypothesis: family={h['family']}, window={h['window']}, halflife_months={h.get('halflife_months')}. Rationale: {h.get('rationale', '')}\n"
                + (f"Critique requested this change: {state['feedback']}\n" if state.get("feedback") else "")
                + "Write the estimator, submit it, verify it, repair if verification fails, then run the development backtest.")
        res = self.role("coder", task, "action")
        cid = res.final.get("candidate_id") or ""
        if res.final["action"] != "ready_for_critique" or not cid:
            return {"status": "RUNNING", "candidate_id": "", "feedback": f"coder gave up: {res.final.get('summary', '')}"}
        return {"status": "RUNNING", "candidate_id": cid, "feedback": ""}

    def critique_node(self, state: RunState) -> RunState:
        ctx = self.ctx
        bts = [b for b in ctx.svc.artifacts("BacktestReport", ctx.lineage_id) if b.get("candidate_id") == state["candidate_id"] and b["split"] == "development"]
        bt_view = summarize_backtest(bts[-1]) if bts else {"note": "no development backtest found"}
        task = (f"Candidate {state['candidate_id']} for lineage {ctx.lineage_id}. Hypothesis diagnostic plan: {state['hypothesis'].get('diagnostic_plan')}.\n"
                f"Development backtest (trusted engine): {json.dumps(bt_view)}\n"
                "Run the diagnostics you judge necessary, then advance, revise (state the change), reject, or stop.")
        res = self.role("critique", task, "verdict")
        out: RunState = {"verdict": res.final["verdict"], "feedback": res.final.get("requested_change", "")}
        if res.final["verdict"] == "advance":
            out["advanced"] = [*state.get("advanced", []), state["candidate_id"]]
        return out

    def validate_node(self, state: RunState) -> RunState:
        """Trusted validation scoring and the preregistered selection rule (no model involved)."""
        ctx = self.ctx
        scored = []
        for cid in state.get("advanced", []):
            bt = ctx.svc.backtest(ctx.lineage_id, "validation", cid)
            m = bt["metrics"]
            scored.append({"candidate_id": cid, "backtest_id": bt["id"], "variance": m["adaptive"]["variance_usd2"],
                           "verdict": m["pass_rule"]["verdict"], "n": bt["n_positions"]})
            self.say(f"    validation {cid}: pass rule {m['pass_rule']['verdict']} on n={bt['n_positions']} (metrics only)")
        qualifying = sorted((s for s in scored if s["verdict"] == "PASS"), key=lambda s: s["variance"])
        if not qualifying:
            return {"status": "ABSTAIN", "reason": "no candidate met the pass rule on validation; the holdout stays sealed"}
        best = qualifying[0]
        frz = ctx.svc.freeze(ctx.lineage_id, "adaptive", best["candidate_id"])
        try:
            ctx.svc.freeze(ctx.lineage_id, "fixed_script", template="ols36")
        except ServiceError as e:
            if e.code != "ALREADY_FROZEN":
                raise
        self.say(f"    frozen {best['candidate_id']} as {frz['id']}; the holdout opens only by the human operator")
        return {"status": "FROZEN", "frozen": frz, "reason": "awaiting the operator's single holdout opening"}

    def route_after_research(self, state: RunState) -> str:
        return "end" if state.get("status") in ("ABSTAIN", "HALT", "BUDGET_EXHAUSTED") else "code"

    def route_after_code(self, state: RunState) -> str:
        if state.get("status") in ("HALT", "BUDGET_EXHAUSTED"):
            return "end"
        if state.get("candidate_id"):
            return "critique"
        return "research" if len(self.ctx.candidates_this_run) < self.ctx.max_candidates_run else "abstain"

    def route_after_critique(self, state: RunState) -> str:
        if state.get("status") in ("HALT", "BUDGET_EXHAUSTED"):
            return "end"
        v = state.get("verdict")
        if v == "advance":
            return "rehearsal_end" if lineage_kind(self.ctx.lineage_id) == "rehearsal" else "validate"
        if v == "stop":
            return "abstain"
        room = len(self.ctx.candidates_this_run) < self.ctx.max_candidates_run
        if not room:
            return "abstain"
        return "code" if v == "revise" else "research"

    def abstain_node(self, state: RunState) -> RunState:
        reason = state.get("reason") or ("critique stopped the research" if state.get("verdict") == "stop" else "candidate budget for this run used up")
        return {"status": "ABSTAIN", "reason": reason}

    def rehearsal_end_node(self, state: RunState) -> RunState:
        return {"status": "REHEARSAL_COMPLETE", "reason": "rehearsal lineages stop after the development critique (validation and holdout untouched)"}

    def research_graph(self):
        g = StateGraph(RunState)
        g.add_node("research", self._guard(self.research_node))
        g.add_node("code", self._guard(self.code_node))
        g.add_node("critique", self._guard(self.critique_node))
        g.add_node("validate", self._guard(self.validate_node))
        g.add_node("abstain", self.abstain_node)
        g.add_node("rehearsal_end", self.rehearsal_end_node)
        g.add_edge(START, "research")
        g.add_conditional_edges("research", self.route_after_research, {"code": "code", "end": END})
        g.add_conditional_edges("code", self.route_after_code, {"critique": "critique", "research": "research", "abstain": "abstain", "end": END})
        g.add_conditional_edges("critique", self.route_after_critique,
                                {"validate": "validate", "rehearsal_end": "rehearsal_end", "code": "code", "research": "research", "abstain": "abstain", "end": END})
        g.add_edge("validate", END)
        g.add_edge("abstain", END)
        g.add_edge("rehearsal_end", END)
        return g.compile()

    # --- execution workflow -----------------------------------------------------------------

    def evidence_node(self, state: RunState) -> RunState:
        try:
            pkt = self.ctx.svc.evidence_packet(self.ctx.lineage_id, self.ctx.run_id)
        except ServiceError as e:
            if e.code == "PASS_RULE_NOT_MET":
                return {"status": "ABSTAIN", "reason": "evidenced refusal: the frozen hedge did not meet the preregistered pass rule on the holdout"}
            raise
        self.ctx.packet = pkt
        self.say(f"    evidence packet {pkt['id']} ({pkt['label']}): recommends {pkt['recommendation']['contracts']} contracts")
        return {"status": "RUNNING", "packet_id": pkt["id"], "recommended": pkt["recommendation"]["contracts"]}

    def risk_node(self, state: RunState) -> RunState:
        ctx = self.ctx
        rec = state["recommended"]
        requested = state.get("requested_contracts")
        reviews = []
        for n in ([requested] if requested is not None else []) + [rec]:
            r = ctx.svc.register_intent(intent_terms(ctx.packet, n, ctx.forecast_gallons), f"agent:execution:{ctx.run_id}", "proposed order")
            reviews.append(summarize_gate(r["gate"], r["intent"]))
        task = (f"Evidence packet {ctx.packet['id']} recommends {rec} contracts ({ctx.packet['recommendation']['source']}).\n"
                + (f"A request arrived to hedge {requested} contracts instead.\n" if requested is not None else "")
                + f"Gate results so far: {json.dumps(reviews)}\n"
                "Explain any blocked result in plain words and give the compliant contract count to propose for human approval.")
        res = self.role("risk", task, "recommended_contracts")
        n = int(res.final["recommended_contracts"])
        r = ctx.svc.register_intent(intent_terms(ctx.packet, n, ctx.forecast_gallons), f"agent:risk:{ctx.run_id}", "risk proposal")
        g = r["gate"]
        other = [o["reason_code"] for o in g["outcomes"] if not o["passed"] and o["rule"] != "G11"]
        if other:
            return {"status": "ABSTAIN", "reason": f"risk proposal of {n} contracts is still blocked: {other}"}
        self.say(f"    proposed {n} contracts for human approval; intent {r['intent']['intent_hash'][:12]}…")
        return {"status": "AWAITING_APPROVAL", "intent_hash": r["intent"]["intent_hash"], "recommended": n}

    def await_approval_node(self, state: RunState) -> RunState:
        t_end = time.monotonic() + self.approval_timeout_s
        self.say("    waiting for a human to approve this exact order in the dashboard (operator code required)…")
        while time.monotonic() < t_end:
            g = self.ctx.svc.gate_check(state["intent_hash"])
            failed = {o["rule"]: o["reason_code"] for o in g["outcomes"] if not o["passed"]}
            if not failed:
                self.say("    approval detected by the trusted service; every rule passes")
                return {"status": "APPROVED"}
            if set(failed) - {"G11"}:
                return {"status": "HALT", "reason": f"order no longer eligible while waiting: {list(failed.values())}"}
            time.sleep(self.poll_s)
        return {"status": "EXPIRED", "reason": "no approval before the timeout"}

    def execution_node(self, state: RunState) -> RunState:
        ctx = self.ctx
        ctx.exec_intent_hash = state["intent_hash"]
        ctx.exec_key = f"ord-{ctx.run_id}-{state['intent_hash'][:12]}"
        res = self.role("execution", f"Submit the approved paper order for intent {state['intent_hash']} (idempotency key fixed: {ctx.exec_key}). "
                                     "If it is not acknowledged, query status before any retry. Then report.", "final_status")
        status, body = ctx.svc.order_status(ctx.exec_key)
        order = body if status == 200 else None
        final = res.final["final_status"]
        if order and order["status"] == "FILLED":
            return {"status": "DONE", "order": order, "reason": f"filled {order['contracts']} contracts at {order['fill_price']} on {order['fill_date']}"}
        return {"status": "HALT" if final == "HALTED" else "NOT_SUBMITTED", "reason": res.final.get("summary", "")}

    def route_exec(self, nxt: str):
        def r(state: RunState) -> str:
            return nxt if state.get("status") in ("RUNNING", "AWAITING_APPROVAL", "APPROVED") else "end"
        return r

    def execution_graph(self):
        g = StateGraph(RunState)
        g.add_node("evidence", self._guard(self.evidence_node))
        g.add_node("risk", self._guard(self.risk_node))
        g.add_node("await_approval", self._guard(self.await_approval_node))
        g.add_node("execute", self._guard(self.execution_node))
        g.add_edge(START, "evidence")
        g.add_conditional_edges("evidence", self.route_exec("risk"), {"risk": "risk", "end": END})
        g.add_conditional_edges("risk", self.route_exec("await_approval"), {"await_approval": "await_approval", "end": END})
        g.add_conditional_edges("await_approval", self.route_exec("execute"), {"execute": "execute", "end": END})
        g.add_edge("execute", END)
        return g.compile()

    # --- run and record ---------------------------------------------------------------------

    def run(self, kind: str, initial: RunState | None = None) -> RunState:
        graph = self.research_graph() if kind == "research" else self.execution_graph()
        state = graph.invoke(initial or {}, config={"recursion_limit": 60})
        state.setdefault("status", "DONE")
        return state

    def trace(self, kind: str, state: RunState, started_at: str) -> dict[str, Any]:
        return {"run_id": self.ctx.run_id, "workflow": kind, "lineage_id": self.ctx.lineage_id, "mode": self.ctx.model.mode,
                "model": self.ctx.model_id, "started_at_utc": started_at, "wall_seconds": round(time.monotonic() - self.t0, 1),
                "model_calls": self.ctx.calls, "input_tokens": self.ctx.input_tokens, "output_tokens": self.ctx.output_tokens,
                "measured_cost_usd": round(self.ctx.cost_usd, 6), "final_status": state.get("status"), "reason": state.get("reason"),
                "decisions": self.decisions, "progress": self.events}


def save_trace(trace: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{trace['run_id']}.json"
    p.write_text(json.dumps(trace, indent=1, default=str) + "\n")
    return p

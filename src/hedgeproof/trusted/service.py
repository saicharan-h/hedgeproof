"""HTTP API of the trusted service (FastAPI). Owner: Lohith.

Binds to 127.0.0.1 by default. Human-only routes (approvals, opening the
holdout, arming a simulated acknowledgement timeout) require the per-start
operator code in the ``X-Operator-Code`` header. The agent process never has it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hedgeproof.records import IntentTerms
from hedgeproof.trusted.core import TrustedCore, TrustedError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateIn(Strict):
    lineage_id: str = Field(max_length=40)
    source: str = Field(max_length=8192)
    family: str = Field(max_length=40)
    window: int
    params: dict[str, Any] = Field(default_factory=dict)
    change_note: str = Field(default="", max_length=500)
    decision_id: str = Field(default="", max_length=40)


class RepairIn(Strict):
    source: str = Field(max_length=8192)
    change_note: str = Field(default="", max_length=500)
    decision_id: str = Field(default="", max_length=40)


class BacktestIn(Strict):
    lineage_id: str = Field(max_length=40)
    split: str
    candidate_id: str | None = None
    template: str | None = None


class DiagnosticIn(Strict):
    lineage_id: str = Field(max_length=40)
    kind: str
    candidate_id: str | None = None
    template: str | None = None


class FreezeIn(Strict):
    lineage_id: str = Field(max_length=40)
    strategy: str = Field(pattern="^(adaptive|fixed_script|single_agent)$")
    candidate_id: str | None = None
    template: str | None = None


class LineageIn(Strict):
    lineage_id: str = Field(max_length=40)


class EvidenceIn(Strict):
    lineage_id: str = Field(max_length=40)
    run_id: str = Field(max_length=40)
    strategy: str = "adaptive"


class IntentIn(Strict):
    terms: IntentTerms
    requested_by: str = Field(max_length=40)
    note: str = Field(default="", max_length=300)


class GateIn(Strict):
    intent_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=80)


class ApprovalIn(Strict):
    intent_hash: str = Field(min_length=64, max_length=64)
    approver: str = Field(max_length=60)


class OrderIn(Strict):
    intent_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=80)


def create_app(core: TrustedCore) -> FastAPI:
    app = FastAPI(title="HedgeProof trusted service", version="0.1.0")
    app.state.core = core
    app.state.arm_ack_timeout = False

    @app.exception_handler(TrustedError)
    async def _trusted_error(_: Request, exc: TrustedError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"code": exc.code, "message": exc.message, **exc.extra})

    @app.get("/health")
    def health() -> dict[str, Any]:
        return core.health() | {"ack_timeout_armed": app.state.arm_ack_timeout}

    @app.get("/policy")
    def policy() -> dict[str, Any]:
        s = core.settings
        return {"policy": s.policy.raw, "policy_sha256": s.policy.sha256, "forecast_gallons": s.forecast_gallons,
                "n_cap": s.policy.n_cap(s.forecast_gallons), "agency": s.agency, "replay_date": s.replay_date}

    @app.get("/sources")
    def sources() -> list[dict[str, Any]]:
        return core.list_sources()

    @app.get("/sources/{source_id}")
    def source(source_id: str) -> dict[str, Any]:
        return core.get_source(source_id)

    @app.get("/data/profile")
    def data_profile(as_of: str) -> dict[str, Any]:
        return core.data_profile(as_of)

    @app.get("/data/window")
    def data_window(as_of: str, window: int) -> dict[str, Any]:
        return core.data_window(as_of, window)

    @app.get("/splits")
    def splits() -> dict[str, Any]:
        core._need_data()
        counts: dict[str, int] = {}
        for r in core.rows:
            counts[r["split"]] = counts.get(r["split"], 0) + 1
        return {"counts": counts, "rejected": [{"hedge_month": r["hedge_month"], "status": r["status"]} for r in core.rows if r["status"] != "ok"],
                "definitions": core.settings.experiment["splits"]}

    @app.get("/data/development-rows")
    def development_rows() -> list[dict[str, Any]]:
        """Development and warm-up rows for the dashboard (never validation or holdout prices)."""
        core._need_data()
        return [r for r in core.rows if r["split"] in ("warmup", "development")]

    @app.post("/candidates")
    def candidates(body: CandidateIn) -> dict[str, Any]:
        return core.register_candidate(body.lineage_id, body.source, body.family, body.window, body.params,
                                       body.change_note, body.decision_id or "agent")

    @app.get("/candidates")
    def list_candidates(lineage_id: str | None = None) -> list[dict[str, Any]]:
        return core.list_candidates(lineage_id)

    @app.post("/candidates/{candidate_id}/repair")
    def repair(candidate_id: str, body: RepairIn) -> dict[str, Any]:
        return core.repair_candidate(candidate_id, body.source, body.change_note, body.decision_id or "agent")

    @app.post("/candidates/{candidate_id}/verify")
    def verify(candidate_id: str) -> dict[str, Any]:
        return core.verify_candidate(candidate_id)

    @app.post("/backtests")
    def backtests(body: BacktestIn) -> dict[str, Any]:
        return core.run_backtest(body.lineage_id, body.split, body.candidate_id, body.template, actor="coder")

    @app.post("/diagnostics")
    def diagnostics(body: DiagnosticIn) -> dict[str, Any]:
        return core.run_diagnostic(body.lineage_id, body.candidate_id, body.kind, body.template)

    @app.post("/freeze")
    def freeze(body: FreezeIn) -> dict[str, Any]:
        return core.freeze(body.lineage_id, body.strategy, body.candidate_id, body.template)

    @app.post("/holdout/evaluate")
    def holdout(body: LineageIn, x_operator_code: str | None = Header(default=None)) -> dict[str, Any]:
        return core.evaluate_holdout(body.lineage_id, x_operator_code)

    @app.post("/evidence/packets")
    def evidence(body: EvidenceIn) -> dict[str, Any]:
        return core.build_evidence_packet(body.lineage_id, body.run_id, body.strategy)

    @app.post("/decisions")
    def decisions(body: dict[str, Any]) -> dict[str, Any]:
        return core.record_decision(body)

    @app.get("/intents/{intent_hash}")
    def intent(intent_hash: str) -> dict[str, Any]:
        return core.get_intent(intent_hash)

    @app.post("/intents")
    def intents(body: IntentIn) -> dict[str, Any]:
        return core.register_intent(body.terms, body.requested_by, body.note)

    @app.get("/intents")
    def list_intents() -> list[dict[str, Any]]:
        return core.list_intents()

    @app.post("/gate/check")
    def gate_check(body: GateIn) -> dict[str, Any]:
        return core.gate_check(body.intent_hash, body.idempotency_key)

    @app.post("/approvals")
    def approvals(body: ApprovalIn, x_operator_code: str | None = Header(default=None)) -> dict[str, Any]:
        return core.approve(body.intent_hash, body.approver, x_operator_code)

    @app.post("/simulator/arm-ack-timeout")
    def arm(x_operator_code: str | None = Header(default=None)) -> dict[str, Any]:
        core.check_operator_code(x_operator_code)
        app.state.arm_ack_timeout = True
        core.store.log("human", "ack_timeout_armed", [], {"detail": "next order's acknowledgement will be withheld (labelled fault injection)"})
        return {"armed": True}

    @app.post("/orders")
    def orders(body: OrderIn) -> JSONResponse:
        inject = bool(app.state.arm_ack_timeout)
        result = core.submit_order(body.intent_hash, body.idempotency_key, inject_ack_timeout=inject)
        if result["ack_timeout"]:
            app.state.arm_ack_timeout = False
            return JSONResponse(status_code=504, content={"code": "ACK_TIMEOUT",
                                "message": "No acknowledgement received. Outcome unknown: query /orders/{key} before any retry."})
        return JSONResponse(status_code=200, content=result)

    @app.get("/orders/{idempotency_key}")
    def order_status(idempotency_key: str) -> dict[str, Any]:
        return core.order_status(idempotency_key)

    @app.get("/ledger")
    def ledger() -> dict[str, Any]:
        return core.ledger()

    @app.get("/events")
    def events(after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        return core.store.events(after, min(limit, 2000))

    @app.get("/artifacts")
    def artifacts(kind: str | None = None, lineage_id: str | None = None) -> list[dict[str, Any]]:
        out = core.store.list_artifacts(kind, lineage_id)
        return [_redact(a) for a in out]

    @app.get("/artifacts/{artifact_id}")
    def artifact(artifact_id: str) -> dict[str, Any]:
        a = core.store.get(artifact_id)
        if a is None:
            raise TrustedError("NOT_FOUND", "artifact not found", 404)
        return _redact(a) | {"hash_recomputes": core.store.recompute_hash(artifact_id) == a.get("sha256")}

    return app


def _redact(a: dict[str, Any]) -> dict[str, Any]:
    """Never serve validation price rows; metrics stay visible."""
    if a.get("split") == "validation" and a.get("rows"):
        return a | {"rows": [], "note": "validation rows withheld; metrics only"}
    return a

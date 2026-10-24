"""Typed HTTP client the agent process uses to reach the trusted service.

Owner: Saicharan (orchestration). Deliberately has NO method for approvals,
opening the holdout or arming fault injection, and never sends an operator
code. Even if it tried, the trusted service refuses those routes without the
code, which only the human sees.
"""

from __future__ import annotations

from typing import Any

import httpx


class ServiceError(Exception):
    def __init__(self, status: int, body: dict[str, Any]):
        super().__init__(body.get("message", str(body)))
        self.status, self.body = status, body
        self.code = body.get("code", "ERROR")


class ServiceClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", http: httpx.Client | None = None, timeout: float = 120.0):
        self.http = http or httpx.Client(base_url=base_url, timeout=timeout)

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        if "headers" in kw and any(k.lower() == "x-operator-code" for k in kw["headers"]):
            raise PermissionError("the agent process never sends an operator code")
        r = self.http.request(method, path, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {"message": r.text[:300]}
        if r.status_code >= 400:
            raise ServiceError(r.status_code, body if isinstance(body, dict) else {"message": str(body)})
        return body

    # read-only
    def health(self) -> dict[str, Any]:
        return self._req("GET", "/health")

    def policy(self) -> dict[str, Any]:
        return self._req("GET", "/policy")

    def sources(self) -> list[dict[str, Any]]:
        return self._req("GET", "/sources")

    def source(self, source_id: str) -> dict[str, Any]:
        return self._req("GET", f"/sources/{source_id}")

    def data_profile(self, as_of: str) -> dict[str, Any]:
        return self._req("GET", "/data/profile", params={"as_of": as_of})

    def data_window(self, as_of: str, window: int) -> dict[str, Any]:
        return self._req("GET", "/data/window", params={"as_of": as_of, "window": window})

    def artifact(self, artifact_id: str) -> dict[str, Any]:
        return self._req("GET", f"/artifacts/{artifact_id}")

    def artifacts(self, kind: str | None = None, lineage_id: str | None = None) -> list[dict[str, Any]]:
        params = {k: v for k, v in (("kind", kind), ("lineage_id", lineage_id)) if v}
        return self._req("GET", "/artifacts", params=params)

    def candidates(self, lineage_id: str | None = None) -> list[dict[str, Any]]:
        return self._req("GET", "/candidates", params={"lineage_id": lineage_id} if lineage_id else {})

    def ledger(self) -> dict[str, Any]:
        return self._req("GET", "/ledger")

    def intent(self, intent_hash: str) -> dict[str, Any]:
        return self._req("GET", f"/intents/{intent_hash}")

    # research actions (counted and checked by the trusted service)
    def register_candidate(self, lineage_id: str, source: str, family: str, window: int, params: dict[str, Any] | None,
                           change_note: str, decision_id: str = "") -> dict[str, Any]:
        return self._req("POST", "/candidates", json={"lineage_id": lineage_id, "source": source, "family": family, "window": window,
                                                      "params": params or {}, "change_note": change_note, "decision_id": decision_id})

    def repair_candidate(self, candidate_id: str, source: str, change_note: str, decision_id: str = "") -> dict[str, Any]:
        return self._req("POST", f"/candidates/{candidate_id}/repair", json={"source": source, "change_note": change_note, "decision_id": decision_id})

    def verify_candidate(self, candidate_id: str) -> dict[str, Any]:
        return self._req("POST", f"/candidates/{candidate_id}/verify")

    def backtest(self, lineage_id: str, split: str, candidate_id: str | None = None, template: str | None = None) -> dict[str, Any]:
        return self._req("POST", "/backtests", json={"lineage_id": lineage_id, "split": split, "candidate_id": candidate_id, "template": template})

    def diagnostic(self, lineage_id: str, kind: str, candidate_id: str | None = None, template: str | None = None) -> dict[str, Any]:
        return self._req("POST", "/diagnostics", json={"lineage_id": lineage_id, "kind": kind, "candidate_id": candidate_id, "template": template})

    def freeze(self, lineage_id: str, strategy: str, candidate_id: str | None = None, template: str | None = None) -> dict[str, Any]:
        return self._req("POST", "/freeze", json={"lineage_id": lineage_id, "strategy": strategy, "candidate_id": candidate_id, "template": template})

    def evidence_packet(self, lineage_id: str, run_id: str, strategy: str = "adaptive") -> dict[str, Any]:
        return self._req("POST", "/evidence/packets", json={"lineage_id": lineage_id, "run_id": run_id, "strategy": strategy})

    def record_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        return self._req("POST", "/decisions", json=decision)

    # orders
    def register_intent(self, terms: dict[str, Any], requested_by: str, note: str = "") -> dict[str, Any]:
        return self._req("POST", "/intents", json={"terms": terms, "requested_by": requested_by, "note": note})

    def gate_check(self, intent_hash: str, idempotency_key: str | None = None) -> dict[str, Any]:
        return self._req("POST", "/gate/check", json={"intent_hash": intent_hash, "idempotency_key": idempotency_key})

    def submit_order(self, intent_hash: str, idempotency_key: str) -> tuple[int, dict[str, Any]]:
        """Returns (HTTP status, body). 504 means no acknowledgement: outcome unknown."""
        try:
            r = self.http.post("/orders", json={"intent_hash": intent_hash, "idempotency_key": idempotency_key})
        except httpx.TimeoutException:
            return 504, {"code": "CLIENT_TIMEOUT", "message": "no response before the client timeout"}
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"message": r.text[:300]}

    def order_status(self, idempotency_key: str) -> tuple[int, dict[str, Any]]:
        r = self.http.get(f"/orders/{idempotency_key}")
        return r.status_code, r.json()

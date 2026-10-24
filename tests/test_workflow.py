"""End-to-end agent workflow with the SCRIPTED TEST DOUBLE (no AI calls), SYNTHETIC data and a TEST lineage."""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hedgeproof.agents.graph import Workflow
from hedgeproof.agents.llm import ScriptedClient
from hedgeproof.agents.roles import RunContext
from hedgeproof.agents.scripted import script
from hedgeproof.agents.service_client import ServiceClient
from hedgeproof.evals.cases import CODE, Env
from hedgeproof.sandbox import DockerSandbox
from hedgeproof.trusted.service import create_app

SB = DockerSandbox()
pytestmark = pytest.mark.skipif(not SB.available()[0], reason="Docker sandbox image not available")


def _ctx(env: Env, lineage: str) -> RunContext:
    svc = ServiceClient(http=TestClient(create_app(env.core)))
    return RunContext(svc=svc, model=ScriptedClient(script), model_id="scripted-test-double", run_id=f"RUN-{lineage}",
                      lineage_id=lineage, research_clock=env.settings.research_clock, log=lambda m: None)


def test_research_workflow_repairs_then_freezes():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        env = Env(Path(d), sandbox=SB)
        wf = Workflow(_ctx(env, "TEST-WF"))
        state = wf.run("research")
        assert state["status"] == "FROZEN", state
        roles = [x["role"] for x in wf.decisions]
        assert roles == ["research", "coder", "critique"]
        coder_tools = [t["tool"] for t in wf.decisions[1]["tool_calls"]]
        assert coder_tools == ["submit_candidate", "verify_candidate", "repair_candidate", "verify_candidate", "run_dev_backtest"]
        assert wf.decisions[1]["tool_calls"][1]["error"] is False and '"passed": false' in wf.decisions[1]["tool_calls"][1]["result_summary"]
        assert all(x["mode"] == "test_double" and x["cost_usd"] == 0 for x in wf.decisions)
        cands = env.core.list_candidates("TEST-WF")
        assert len(cands) == 1 and cands[0]["repair_count"] == 1 and cands[0]["status"] == "FROZEN"
        # The agent process never received or used the operator code: no approvals, holdout still sealed.
        assert env.core.store.query("SELECT id FROM approvals") == []
        assert env.core.health()["holdout_locks"].get("TEST-WF") == "sealed"


def test_execution_workflow_waits_for_human_then_reconciles_lost_ack():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        env = Env(Path(d), sandbox=SB)
        env.core.run_backtest("TEST-EX", "development", template="ols36", actor="trusted")
        ctx = _ctx(env, "TEST-EX")
        wf = Workflow(ctx, approval_timeout_s=30, poll_s=0.2)
        stop = threading.Event()

        def human() -> None:  # the analyst approves the compliant proposal in the dashboard (never the 15)
            from hedgeproof.trusted.core import TrustedError

            while not stop.is_set():
                for it in env.core.list_intents():
                    if it["terms"]["contracts"] <= 7 and not env.core.store.query("SELECT 1 FROM approvals WHERE intent_hash = ?", (it["intent_hash"],)):
                        try:
                            env.core.approve(it["intent_hash"], "Saicharan", CODE)
                        except TrustedError:
                            pass
                time.sleep(0.1)

        # Arm one lost acknowledgement through the core (as the operator would from the dashboard).
        orig = env.core.submit_order

        def submit_with_lost_ack(intent_hash, key, inject_ack_timeout=False, actor="execution"):
            return orig(intent_hash, key, inject_ack_timeout=True, actor=actor)

        env.core.submit_order = submit_with_lost_ack  # type: ignore[method-assign]
        t = threading.Thread(target=human, daemon=True)
        t.start()
        try:
            state = wf.run("execute", {"requested_contracts": 15})
        finally:
            stop.set()
        assert state["status"] == "DONE", state
        assert state["order"]["contracts"] == 5
        roles = [x["role"] for x in wf.decisions]
        assert roles == ["risk", "execution"]
        exec_tools = [x["tool"] for x in wf.decisions[1]["tool_calls"]]
        assert exec_tools == ["submit_order", "order_status"]
        assert len(env.core.store.query("SELECT id FROM orders")) == 1
        blocked15 = [i for i in env.core.list_intents() if i["terms"]["contracts"] == 15]
        assert blocked15 and not env.core.store.query("SELECT 1 FROM orders WHERE intent_hash = ?", (blocked15[0]["intent_hash"],))

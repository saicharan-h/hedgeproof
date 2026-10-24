"""Research-loop fixes found in the first live run (RUN-e56d7478db40, 24 Oct 2026).

The critique asked for "revise" three times and the coder resubmitted the same
configuration each time, using up the run's candidate budget; two diagnostics
looked identical to the base without saying why. These tests pin the fixes.
No API calls: SYNTHETIC data, temporary databases, fake model objects.
"""

from __future__ import annotations

import subprocess

import pytest

from hedgeproof.agents.cli import code_version
from hedgeproof.agents.graph import Workflow
from hedgeproof.agents.llm import ModelResponse
from hedgeproof.agents.roles import RoleError, RunContext, run_role
from hedgeproof.config import REPO_ROOT
from hedgeproof.engine import VETTED_SOURCES
from hedgeproof.evals.cases import Env
from hedgeproof.trusted.core import TrustedError


def test_duplicate_configuration_is_refused_without_using_budget(tmp_path):
    with Env(tmp_path) as env:
        first = env.core.register_candidate("TEST-DUP", VETTED_SOURCES["ols"], "ols", 36, {}, "first", "test")
        with pytest.raises(TrustedError) as e:
            env.core.register_candidate("TEST-DUP", VETTED_SOURCES["ols"] + "\n# reworded\n", "ols", 36, {}, "same configuration", "test")
        assert e.value.code == "DUPLICATE_CONFIGURATION" and first["id"] in e.value.message
        other = env.core.register_candidate("TEST-DUP", VETTED_SOURCES["ols"], "ols", 24, {}, "other window", "test")
        assert other["ordinal"] == 2  # the refused attempt used no candidate budget


def test_diagnostics_state_sample_sizes_cap_binding_and_cost_effect(tmp_path):
    with Env(tmp_path) as env:
        sub = env.core.run_diagnostic("TEST-DX", None, "subperiod", template="ols36")
        n1, n2 = len(sub["result"]["first_half"]["months"]), len(sub["result"]["second_half"]["months"])
        assert f"({n1} and {n2} positions" in sub["interpretation"]
        win = env.core.run_diagnostic("TEST-DX", None, "window_alt", template="ols36")
        r = win["result"]
        assert f"limit in {r['months_ratio_clipped_alt']} and {r['months_ratio_clipped_base']} of {r['n_positions']} months" in win["interpretation"]
        dc = env.core.run_diagnostic("TEST-DX", None, "double_cost", template="ols36")
        assert dc["result"]["adaptive_mean_error_double_cost"] > dc["result"]["adaptive_mean_error_base"]  # extra costs raise the error
        assert "mean budget error" in dc["interpretation"]


class _NeverFinishes:
    """Fake model that keeps calling a non-final tool."""

    mode = "test_double"

    def __init__(self) -> None:
        self.requests: list[list] = []

    def create(self, *, model, system, messages, tools, max_tokens, run_id) -> ModelResponse:
        self.requests.append(list(messages))
        uid = f"toolu_{len(self.requests)}"
        return ModelResponse([{"type": "tool_use", "id": uid, "name": "list_sources", "input": {}}],
                             [{"id": uid, "name": "list_sources", "input": {}}], "", "tool_use")


class _Svc:
    def sources(self) -> list:
        return []


def _ctx(model=None, svc=None, rounds: int = 6) -> RunContext:
    return RunContext(svc=svc, model=model, model_id="test", run_id="RUN-T", lineage_id="TEST-R", research_clock="2018-01-01",
                      max_tool_rounds=rounds, log=lambda m: None)


def test_role_is_warned_before_its_last_turn_then_halts():
    model = _NeverFinishes()
    with pytest.raises(RoleError, match="tool rounds exhausted"):
        run_role(_ctx(model, _Svc(), rounds=3), "research", "task")
    assert len(model.requests) == 3
    warning = model.requests[2][-1]["content"][-1]
    assert warning["type"] == "text" and "submit_hypothesis" in warning["text"]
    assert all(b["type"] == "tool_result" for b in model.requests[1][-1]["content"])  # no warning earlier


def test_unexpected_error_halts_the_run_with_its_reason():
    def broken(state):
        raise ZeroDivisionError("boom")

    out = Workflow(_ctx())._guard(broken)({})
    assert out["status"] == "HALT" and "ZeroDivisionError: boom" in out["reason"]


def test_code_version_names_the_checked_out_commit():
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert code_version().startswith(head)

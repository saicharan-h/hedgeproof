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


def test_model_refusal_reason_is_kept_in_the_halt():
    from hedgeproof.agents.llm import ModelCallError

    def refused(state):
        raise ModelCallError("rejected", "request rejected: BadRequestError 400: tools.4: schema not supported")

    out = Workflow(_ctx())._guard(refused)({})
    assert out["status"] == "HALT" and "BadRequestError 400: tools.4: schema not supported" in out["reason"]


def test_smoke_reproduces_the_research_request_and_isolates_the_refused_feature(tmp_path, monkeypatch, capsys):
    """Small probes pass, the research-shaped request is refused, and the variant that passes is named."""
    import json as _json
    from types import SimpleNamespace

    import anthropic
    import httpx2

    import hedgeproof.agents.cli as cli
    from hedgeproof.agents.spend import SpendController
    from hedgeproof.config import load_settings

    def handler(request):
        body = _json.loads(request.content)
        if any("cache_control" in b for b in body["system"]):  # this fake provider refuses prompt caching
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "cache_control not supported"}})
        return httpx2.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                                          "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
                                          "usage": {"input_tokens": 50, "output_tokens": 5}})

    real_anthropic = anthropic.Anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: real_anthropic(**kw, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr(cli, "_spend", lambda: SpendController(tmp_path / "spend.db", load_settings().runtime))
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline in tests")))
    cli.cmd_smoke(SimpleNamespace(model=None))
    out = capsys.readouterr().out
    assert "2 strict tool + effort: OK" in out
    assert "6 research request as a run sends it: FAILED" in out and "cache_control not supported" in out
    assert "accepted with: ['9 same, no prompt caching']" in out


def test_smoke_prints_the_key_allowance_and_sends_the_key_only_to_the_key_endpoint(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    import anthropic
    import httpx
    import httpx2

    import hedgeproof.agents.cli as cli
    from hedgeproof.agents.spend import SpendController
    from hedgeproof.config import load_settings

    prov = load_settings().runtime["provider"]
    ok = lambda request: httpx2.Response(200, json={  # noqa: E731
        "id": "m", "type": "message", "role": "assistant", "model": "anthropic/claude-haiku-5.5", "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 50, "output_tokens": 5}})
    real_anthropic = anthropic.Anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: real_anthropic(**kw, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(ok))))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr(cli, "_spend", lambda: SpendController(tmp_path / "spend.db", load_settings().runtime))
    sent: dict[str, dict] = {}

    class _Resp:
        def __init__(self, data):
            self.status_code, self._data = 200, data

        def json(self):
            return self._data

    def fake_get(url, headers=None, timeout=None):
        sent[url] = dict(headers or {})
        return _Resp({"data": {"limit": 0.04, "usage": 0.0253, "limit_remaining": 0.0147}} if url == prov["key_info_url"] else {"data": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    cli.cmd_smoke(SimpleNamespace(model=None))
    out = capsys.readouterr().out
    assert "key allowance: limit $0.0400 · used $0.0253 · remaining $0.0147" in out
    assert "test-openrouter-key-not-real" not in out
    assert sent[prov["key_info_url"]]["Authorization"] == "Bearer test-openrouter-key-not-real"
    assert "Authorization" not in sent[prov["models_url"]]

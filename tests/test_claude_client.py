"""ClaudeClient against a MOCK HTTP transport (no network, no key, no cost).

Checks the request we would send (strict tools, effort, no forced tool_choice,
no sampling parameters) and the spend ledger outcome for a successful call, a
rate limit (released) and a timeout (kept as uncertain).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

import anthropic
import httpx2
import pytest

from hedgeproof.agents.llm import ClaudeClient, ModelCallError
from hedgeproof.agents.roles import RESEARCH_TOOLS
from hedgeproof.agents.spend import SpendController
from hedgeproof.config import load_settings

SENT: list[dict] = []


def _reply(request: httpx2.Request) -> httpx2.Response:
    SENT.append(json.loads(request.content))
    return httpx2.Response(200, json={
        "id": "msg_mock", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": [{"type": "tool_use", "id": "toolu_1", "name": "data_profile", "input": {"as_of": "2018-01-01"}}],
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 600},
    })


@contextmanager
def _client(handler, tmp_path) -> Iterator[tuple[ClaudeClient, SpendController]]:
    with SpendController(tmp_path / "spend.db", load_settings().runtime) as spend:
        c = ClaudeClient(spend, "dev", effort="low", timeout_s=5, max_attempts=1)
        c.sdk = anthropic.Anthropic(api_key="test-key-not-real", max_retries=0, timeout=5,
                                    http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
        yield c, spend


def _call(c: ClaudeClient):
    return c.create(model="claude-haiku-5-5", system=[{"type": "text", "text": "ROLE: research\nTest.", "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": "Profile the data."}], tools=RESEARCH_TOOLS, max_tokens=500, run_id="RUN-MOCK")


def test_successful_call_request_shape_and_settlement(tmp_path):
    SENT.clear()
    with _client(_reply, tmp_path) as (c, spend):
        r = _call(c)
        s = spend.summary()
    body = SENT[0]
    assert body["model"] == "claude-haiku-5-5" and body["max_tokens"] == 500
    assert body["output_config"] == {"effort": "low"}
    assert "tool_choice" not in body and "temperature" not in body and "top_p" not in body
    assert all(t["strict"] is True and t["input_schema"]["additionalProperties"] is False for t in body["tools"])
    assert r.tool_uses == [{"id": "toolu_1", "name": "data_profile", "input": {"as_of": "2018-01-01"}}]
    expected = (1200 * 0.10 + 600 * 0.01 + 80 * 0.50) / 1e6
    assert r.cost_usd == pytest.approx(expected)
    assert s["settled_calls"] == 1 and s["committed_usd"] == pytest.approx(expected)


def test_rate_limit_releases_reservation(tmp_path):
    import hedgeproof.agents.llm as llm

    limited = lambda req: httpx2.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}})  # noqa: E731
    with _client(limited, tmp_path) as (c, spend):
        orig = llm.time.sleep
        llm.time.sleep = lambda s: None
        try:
            with pytest.raises(ModelCallError) as e:
                _call(c)
        finally:
            llm.time.sleep = orig
        committed = spend.summary()["committed_usd"]
    assert e.value.kind == "rate_limit"
    assert committed == 0


def test_timeout_keeps_reservation_as_uncertain(tmp_path):
    def boom(req):
        raise httpx2.ReadTimeout("simulated timeout", request=req)

    with _client(boom, tmp_path) as (c, spend):
        with pytest.raises(ModelCallError) as e:
            _call(c)
        s = spend.summary()
    assert e.value.uncertain is True
    assert s["uncertain_calls"] == 1 and s["uncertain_reserved_usd"] > 0

"""Model clients for the agent roles. Owner: Kruthik (agent tools), with Saicharan (spend ledger).

* ``ClaudeClient``: the Anthropic SDK behind the spend controller. Every call
  is reserved before dispatch and settled (or released / kept as uncertain)
  after. SDK retries are disabled so every attempt is accounted for.
* ``ScriptedClient``: a deterministic TEST DOUBLE that emits fixed tool calls.
  It makes no AI calls and every record it produces is labelled
  "test_double". It exists for tests and for demonstrating the workflow
  plumbing when no API funding is available; it is never presented as AI.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from hedgeproof.agents.spend import BudgetExhausted, Reservation, SpendController


@dataclass
class ModelResponse:
    content: list[Any]  # blocks to append to history unchanged (SDK objects or dicts)
    tool_uses: list[dict[str, Any]]  # [{"id", "name", "input"}]
    text: str
    stop_reason: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    model: str = ""
    mode: str = "live"


class ModelCallError(Exception):
    def __init__(self, kind: str, message: str, uncertain: bool = False):
        super().__init__(message)
        self.kind, self.uncertain = kind, uncertain


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    raise TypeError(type(obj).__name__)


def request_bytes(system: Any, messages: list[Any], tools: list[dict[str, Any]]) -> int:
    return len(json.dumps({"system": system, "messages": messages, "tools": tools}, default=_jsonable).encode("utf-8"))


class ClaudeClient:
    mode = "live"

    def __init__(self, spend: SpendController, phase: str, effort: str = "medium", timeout_s: float = 120.0, max_attempts: int = 2):
        import anthropic

        self.anthropic = anthropic
        self.sdk = anthropic.Anthropic(max_retries=0, timeout=timeout_s)  # key read from ANTHROPIC_API_KEY; never logged
        self.spend, self.phase, self.effort, self.max_attempts = spend, phase, effort, max_attempts

    def create(self, *, model: str, system: list[dict[str, Any]], messages: list[Any], tools: list[dict[str, Any]],
               max_tokens: int, run_id: str) -> ModelResponse:
        a = self.anthropic
        last_err: ModelCallError | None = None
        for attempt in range(self.max_attempts):
            res: Reservation = self.spend.reserve(run_id, self.phase, model, request_bytes(system, messages, tools), max_tokens)
            t0 = time.monotonic()
            kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
                                      "output_config": {"effort": self.effort}}
            if tools:
                kwargs["tools"] = tools
            try:
                resp = self.sdk.messages.create(**kwargs)
            except a.APITimeoutError as e:
                self.spend.mark_uncertain(res, "APITimeoutError")
                last_err = ModelCallError("timeout", "model call timed out; reservation kept as uncertain", uncertain=True)
                continue
            except a.APIConnectionError as e:
                self.spend.mark_uncertain(res, "APIConnectionError")
                last_err = ModelCallError("connection", f"connection error: {type(e).__name__}", uncertain=True)
                continue
            except a.RateLimitError:
                self.spend.release(res, "RateLimitError 429")
                last_err = ModelCallError("rate_limit", "rate limited")
                time.sleep(5)
                continue
            except a.APIStatusError as e:
                self.spend.release(res, f"APIStatusError {e.status_code}")
                if e.status_code >= 500:
                    last_err = ModelCallError("server", f"server error {e.status_code}")
                    time.sleep(3)
                    continue
                raise ModelCallError("rejected", f"request rejected: {type(e).__name__} {e.status_code}") from None
            usage = {
                "input_tokens": resp.usage.input_tokens or 0,
                "output_tokens": resp.usage.output_tokens or 0,
                "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
            }
            cost = self.spend.settle(res, usage)
            tool_uses = [{"id": b.id, "name": b.name, "input": b.input} for b in resp.content if b.type == "tool_use"]
            text = "".join(b.text for b in resp.content if b.type == "text")
            return ModelResponse(list(resp.content), tool_uses, text, resp.stop_reason or "", usage, cost,
                                 round(time.monotonic() - t0, 2), resp.model, "live")
        raise last_err or ModelCallError("unknown", "model call failed")


# --- Scripted test double -----------------------------------------------------------


Script = Callable[[str, int, list[Any]], list[dict[str, Any]]]


class ScriptedClient:
    """Deterministic stand-in for the model: emits scripted tool calls per role and turn.

    ``script(role, turn, messages) -> list of {"name", "input"}`` tool calls.
    """

    mode = "test_double"

    def __init__(self, script: Script):
        self.script = script
        self.turns: dict[str, int] = {}

    def create(self, *, model: str, system: list[dict[str, Any]], messages: list[Any], tools: list[dict[str, Any]],
               max_tokens: int, run_id: str) -> ModelResponse:
        role = system[0]["text"].split("ROLE:", 1)[1].split("\n", 1)[0].strip() if "ROLE:" in system[0]["text"] else "unknown"
        turn = self.turns.get(role, 0)
        self.turns[role] = turn + 1
        calls = self.script(role, turn, messages)
        blocks, uses = [], []
        for i, c in enumerate(calls):
            uid = f"toolu_scripted_{role}_{turn}_{i}"
            blocks.append({"type": "tool_use", "id": uid, "name": c["name"], "input": c["input"]})
            uses.append({"id": uid, "name": c["name"], "input": c["input"]})
        return ModelResponse(blocks, uses, "", "tool_use" if uses else "end_turn", {}, 0.0, 0.0, "scripted-test-double", "test_double")


# --- OpenRouter client (OpenAI-compatible) ---------------------------------------


class OpenRouterClient:
    """Model client backed by OpenRouter (OpenAI-compatible API).

    Drop-in replacement for ClaudeClient for the agent roles: same ``create``
    signature and ModelResponse output. Model ids are OpenRouter ids such as
    ``anthropic/claude-sonnet-4`` or ``openai/gpt-4o``. The API key is read
    from ``OPENROUTER_API_KEY`` (never logged). Spend control is reused.
    """

    mode = "live"

    def __init__(self, spend: SpendController, phase: str, effort: str = "medium",
                 timeout_s: float = 120.0, max_attempts: int = 2, base_url: str = "https://openrouter.ai/api/v1"):
        import os

        import openai

        self.openai = openai
        api_key = os.environ.get("OPENROUTER_API_KEY")
        self.sdk = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout_s)
        self.spend, self.phase, self.effort, self.max_attempts = spend, phase, effort, max_attempts

    def create(self, *, model: str, system: list[dict[str, Any]], messages: list[Any], tools: list[dict[str, Any]],
               max_tokens: int, run_id: str) -> ModelResponse:
        import json
        import time

        # Convert Anthropic-style messages/tools to OpenAI chat format.
        oai_messages: list[dict[str, Any]] = []
        sys_text = "\n".join(b.get("text", "") for b in (system or []) if isinstance(b, dict))
        if sys_text:
            oai_messages.append({"role": "system", "content": sys_text})
        for m in messages or []:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # flatten text blocks; tool_use/tool_result handled minimally
                txt = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                content = txt if txt else json.dumps(content, default=_jsonable)
            oai_messages.append({"role": role, "content": content})

        oai_tools = None
        if tools:
            oai_tools = []
            for t in tools:
                oai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                })

        rb = request_bytes(system, messages, tools)
        last_err: ModelCallError | None = None
        for attempt in range(self.max_attempts):
            res: Reservation = self.spend.reserve(run_id, self.phase, model, rb, max_tokens)
            t0 = time.monotonic()
            try:
                resp = self.sdk.chat.completions.create(
                    model=model, messages=oai_messages, tools=oai_tools, max_tokens=max_tokens,
                )
            except Exception as e:  # noqa: BLE001
                kind = "timeout" if "timeout" in type(e).__name__.lower() else "connection"
                self.spend.mark_uncertain(res, type(e).__name__)
                last_err = ModelCallError(kind, f"{type(e).__name__}: {e}", uncertain=True)
                continue
            choice = resp.choices[0]
            msg = choice.message
            text = msg.content or ""
            tool_uses = []
            blocks: list[Any] = []
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in (msg.tool_calls or []):
                import json as _j
                try:
                    inp = _j.loads(tc.function.arguments or "{}")
                except Exception:  # noqa: BLE001
                    inp = {}
                uid = tc.id
                blocks.append({"type": "tool_use", "id": uid, "name": tc.function.name, "input": inp})
                tool_uses.append({"id": uid, "name": tc.function.name, "input": inp})
            usage = {}
            if resp.usage:
                usage = {
                    "input_tokens": resp.usage.prompt_tokens or 0,
                    "output_tokens": resp.usage.completion_tokens or 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                }
            cost = self.spend.settle(res, usage)
            stop_reason = "tool_use" if tool_uses else (choice.finish_reason or "end_turn")
            return ModelResponse(blocks, tool_uses, text, stop_reason, usage, cost,
                                round(time.monotonic() - t0, 2), getattr(resp, "model", model) or model, "live")
        raise last_err or ModelCallError("unknown", "model call failed")


__all__ = ["BudgetExhausted", "ClaudeClient", "ModelCallError", "ModelResponse", "OpenRouterClient",
           "ScriptedClient", "request_bytes"]

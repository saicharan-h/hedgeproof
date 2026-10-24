"""Agent commands: ``uv run hedgeproof run …`` and ``uv run hedgeproof spend``. Owner: Saicharan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import ExitStack

from hedgeproof.config import RESULTS_DIR, VAR_DIR, load_settings
from hedgeproof.records import new_id, utc_now


def _spend():
    from hedgeproof.agents.spend import SpendController

    return SpendController(VAR_DIR / "spend.db", load_settings().runtime)


def cmd_run(args: argparse.Namespace) -> None:
    from hedgeproof.agents.graph import Workflow, save_trace
    from hedgeproof.agents.llm import ClaudeClient, ScriptedClient
    from hedgeproof.agents.roles import RunContext
    from hedgeproof.agents.scripted import script
    from hedgeproof.agents.service_client import ServiceClient

    settings = load_settings()
    rt = settings.runtime
    svc = ServiceClient(args.service)
    health = svc.health()
    run_id = new_id("RUN")
    with ExitStack() as stack:  # closes the spend ledger connection on every exit path
        spend = None
        if args.agents == "live":
            key_env = rt["provider"]["key_env"]
            if not os.environ.get(key_env):
                sys.exit(f"Live agents need {key_env} in this terminal's environment (set it without echoing it). "
                         "Nothing was sent. Use --agents scripted for the labelled no-AI test double.")
            spend = stack.enter_context(_spend())
            recovered = spend.recover_stale_reservations()
            if recovered:
                print(f"note: {recovered} unsettled reservation(s) from an earlier crash kept as uncertain spend")
            model_id = args.model or rt["models"]["practice" if args.practice else "research"]
            model = ClaudeClient(spend, args.phase, effort=args.effort or rt["models"]["effort"],
                                 timeout_s=rt["call_limits"]["request_timeout_seconds"], max_attempts=rt["call_limits"]["max_attempts_per_call"],
                                 provider=rt["provider"])
            before = spend.summary()
            print(f"LIVE AI RUN {run_id} · model {model_id} · phase {args.phase} · committed so far ${before['committed_usd']:.4f} of ${before['total_allowance_usd']:.2f}")
        else:
            model_id, model = "scripted-test-double", ScriptedClient(script)
            print(f"SCRIPTED TEST DOUBLE RUN {run_id} (no AI calls; labelled test_double)")
        print(f"service: mode {health['mode']} · data {health['data_label']} · holdout {health['holdout_state']}")
        ctx = RunContext(svc=svc, model=model, model_id=model_id, run_id=run_id, lineage_id=args.lineage,
                         research_clock=settings.research_clock, forecast_gallons=settings.forecast_gallons,
                         max_tool_rounds=settings.experiment["research_limits"]["max_tool_rounds_per_turn"],
                         max_candidates_run=settings.experiment["research_limits"]["max_candidates_per_run"], log=print)
        wf = Workflow(ctx, wall_seconds=rt["call_limits"]["max_wall_seconds_per_run"], max_calls=rt["call_limits"]["max_model_calls_per_run"],
                      approval_timeout_s=args.approval_timeout)
        started = utc_now()
        initial = {"requested_contracts": args.request_contracts} if args.workflow == "execute" and args.request_contracts is not None else {}
        state = wf.run(args.workflow, initial)
        trace = wf.trace(args.workflow, state, started)
        out_dir = RESULTS_DIR / "runs" if args.agents == "live" else VAR_DIR / "runs"
        path = save_trace(trace, out_dir)
        print(f"\nRESULT: {state.get('status')} · {state.get('reason', '')}")
        print(f"model calls {ctx.calls} · tokens in {ctx.input_tokens} out {ctx.output_tokens} · measured cost ${ctx.cost_usd:.4f} · trace {path}")
        if spend is not None:
            s = spend.summary()
            print(f"spend ledger: committed ${s['committed_usd']:.4f} · remaining ${s['remaining_usd']:.4f} · phases {json.dumps(s['phases'])}")


def cmd_spend(args: argparse.Namespace) -> None:
    with _spend() as sc:
        print(json.dumps(sc.summary(), indent=1))


def check_prices(rt: dict, listing: list[dict]) -> list[str]:
    """Compare configured prices with a provider price list (OpenRouter /api/v1/models format, $ per token)."""
    problems = []
    live = {m["id"]: m.get("pricing", {}) for m in listing}
    for model_id in {rt["models"]["research"], rt["models"]["practice"]}:
        if model_id not in live:
            problems.append(f"{model_id}: not in the provider's model list")
            continue
        p, ours = live[model_id], rt["prices"].get(model_id, {})
        for field, key in (("prompt", "input"), ("completion", "output"), ("input_cache_read", "cache_read"), ("input_cache_write", "cache_write")):
            if p.get(field) in (None, ""):
                continue
            per_million = float(p[field]) * 1_000_000
            if key not in ours or per_million > float(ours[key]) + 1e-9:
                problems.append(f"{model_id}: provider {field} ${per_million:.4f}/M is above configured {key} ${ours.get(key)}")
    return problems


def cmd_smoke(args: argparse.Namespace) -> None:
    """Check the live provider before any research run: prices, one tiny call, request features.

    Every paid call goes through the spend controller (practice model, tiny
    requests, well under one US cent in total). The key is never printed.
    """
    import httpx

    from hedgeproof.agents.llm import ClaudeClient, ModelCallError
    from hedgeproof.agents.roles import RESEARCH_TOOLS

    rt = load_settings().runtime
    prov = rt["provider"]
    model_id = args.model or rt["models"]["practice"]
    print(f"provider {prov['name']} · base URL {prov.get('base_url') or 'api.anthropic.com'} · key variable {prov['key_env']} · model {model_id}")
    if not os.environ.get(prov["key_env"]):
        sys.exit(f"{prov['key_env']} is not set in this terminal. Nothing was sent.")
    if prov.get("models_url"):
        try:
            listing = httpx.get(prov["models_url"], timeout=30).json().get("data", [])
            ours = [m for m in listing if m.get("id") in (rt["models"]["research"], rt["models"]["practice"])]
            for m in ours:
                pr = m.get("pricing", {})
                print(f"  listed {m['id']}: input ${float(pr.get('prompt', 0)) * 1e6:.2f}/M, output ${float(pr.get('completion', 0)) * 1e6:.2f}/M")
            problems = check_prices(rt, listing)
            print("  price check: OK (configured prices are at or above the provider's list)" if not problems else "  PRICE CHECK FAILED:")
            for pb in problems:
                print("   -", pb)
        except (httpx.HTTPError, ValueError) as e:
            print(f"  could not read the provider price list ({type(e).__name__}); prices unverified")
    tool = [t for t in RESEARCH_TOOLS if t["name"] == "data_profile"]
    system = [{"type": "text", "text": "You are a connectivity test. Follow the user's instruction exactly."}]
    with _spend() as sc:
        def attempt(label: str, tools: list, send_effort: bool, strict: bool, prompt: str) -> bool:
            client = ClaudeClient(sc, "dev", effort="low", timeout_s=60, max_attempts=1,
                                  provider={**prov, "send_effort": send_effort, "strict_tools": strict})
            try:
                r = client.create(model=model_id, system=system, messages=[{"role": "user", "content": prompt}], tools=tools,
                                  max_tokens=300, run_id=new_id("SMOKE"))
            except ModelCallError as e:
                print(f"  {label}: FAILED ({e})")
                return False
            called = [u["name"] for u in r.tool_uses]
            print(f"  {label}: OK · stop {r.stop_reason} · tool calls {called} · text {r.text.strip()[:30]!r} · usage {r.usage} · est. cost ${r.cost_usd:.6f}")
            return True

        ok_plain = attempt("1 plain message", [], False, False, "Reply with one word: ready")
        if not ok_plain:
            sys.exit("The basic call failed; check the key, the model id and the provider balance. No research run was started.")
        ok_full = attempt("2 strict tool + effort", tool, True, True, "Call the data_profile tool with as_of 2018-01-01.")
        ask = "Call the data_profile tool with as_of 2018-01-01."
        if ok_full:
            print("RESULT: provider accepts strict tools and effort; current settings are correct.")
        else:
            ok_no_strict = attempt("3 tool + effort, no strict", tool, True, False, ask)
            ok_no_effort = False if ok_no_strict else attempt("4 strict tool, no effort", tool, False, True, ask)
            if ok_no_strict:
                rec = "send_effort = true, strict_tools = false"
            elif ok_no_effort:
                rec = "send_effort = false, strict_tools = true"
            elif attempt("5 tool, no strict, no effort", tool, False, False, ask):
                rec = "send_effort = false, strict_tools = false"
            else:
                rec = None
            print(f"RECOMMENDED config/runtime.toml [provider] settings: {rec}" if rec
                  else "RESULT: tool calls fail on this provider; do not start live research runs.")
        s = sc.summary()
        print(f"spend ledger: committed ${s['committed_usd']:.6f} of ${s['total_allowance_usd']:.2f}")


def register(sub: argparse._SubParsersAction) -> None:
    r = sub.add_parser("run", help="run an agent workflow against the trusted service")
    r.add_argument("workflow", choices=["research", "execute"])
    r.add_argument("--lineage", required=True, help="HP-FINAL (final service), REHEARSAL-… or TEST-…")
    r.add_argument("--agents", choices=["live", "scripted"], default="scripted")
    r.add_argument("--model", default=None, help="override the model id from config/runtime.toml")
    r.add_argument("--practice", action="store_true", help="use the cheaper practice model")
    r.add_argument("--effort", default=None)
    r.add_argument("--phase", choices=["dev", "final"], default="dev", help="which API allowance to charge")
    r.add_argument("--request-contracts", type=int, default=None, help="execute: an extra requested size for Risk to review (e.g. 15)")
    r.add_argument("--approval-timeout", type=float, default=900)
    r.add_argument("--service", default="http://127.0.0.1:8765")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("spend", help="show the API spend ledger")
    s.set_defaults(fn=cmd_spend)
    k = sub.add_parser("smoke", help="one tiny live API call through the spend controller")
    k.add_argument("--model", default=None)
    k.set_defaults(fn=cmd_smoke)

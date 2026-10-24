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
            if not os.environ.get("ANTHROPIC_API_KEY"):
                sys.exit("Live agents need ANTHROPIC_API_KEY in this terminal's environment (set it without echoing it). "
                         "Nothing was sent. Use --agents scripted for the labelled no-AI test double.")
            spend = stack.enter_context(_spend())
            recovered = spend.recover_stale_reservations()
            if recovered:
                print(f"note: {recovered} unsettled reservation(s) from an earlier crash kept as uncertain spend")
            model_id = args.model or rt["models"]["practice" if args.practice else "research"]
            model = ClaudeClient(spend, args.phase, effort=args.effort or rt["models"]["effort"],
                                 timeout_s=rt["call_limits"]["request_timeout_seconds"], max_attempts=rt["call_limits"]["max_attempts_per_call"])
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


def cmd_smoke(args: argparse.Namespace) -> None:
    """One tiny live call through the spend controller (practice model, a few tokens)."""
    from hedgeproof.agents.llm import ClaudeClient

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this terminal. Nothing was sent.")
    rt = load_settings().runtime
    model_id = args.model or rt["models"]["practice"]
    with _spend() as sc:
        client = ClaudeClient(sc, "dev", effort="low", timeout_s=60, max_attempts=1)
        r = client.create(model=model_id, system=[{"type": "text", "text": "Reply with one word."}],
                          messages=[{"role": "user", "content": "Reply with one word: ready"}], tools=[], max_tokens=200, run_id=new_id("SMOKE"))
    print(f"model {r.model} · stop {r.stop_reason} · text {r.text.strip()[:40]!r} · usage {r.usage} · cost ${r.cost_usd:.6f}")


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

"""Command line entry point: ``uv run hedgeproof <command>``. Owner: Saicharan."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from hedgeproof.config import DATA_DIR, REPO_ROOT, VAR_DIR, load_settings

DEFAULT_PORT = 8765


def _load_sources(inject: bool) -> list[dict]:
    src = json.loads((DATA_DIR / "sources" / "sources.json").read_text())
    if inject:
        src.append(json.loads((REPO_ROOT / "tests" / "fixtures" / "injected_source.json").read_text()))
    return src


def build_core(mode: str, synthetic: bool = False, db: str | None = None, inject_source: bool = False,
              operator_code: str | None = None, config_dir: str | None = None, data_dir: str | None = None,
              scenario: str = "us"):
    from hedgeproof.ingest import load_manifest, manifest_for, verify_raw_files
    from hedgeproof.sandbox import DockerSandbox
    from hedgeproof.trusted.core import TrustedCore
    from hedgeproof.trusted.store import Store

    if config_dir is None and scenario == "india":
        config_dir = str(REPO_ROOT / "config" / "india")
    if data_dir is None and scenario == "india":
        data_dir = str(REPO_ROOT / "data" / "india")
    dd = Path(data_dir) if data_dir else DATA_DIR
    settings = load_settings(Path(config_dir) if config_dir else None)

    if synthetic or mode == "test":
        if mode != "test":
            raise SystemExit("SYNTHETIC data is only allowed in --mode test")
        if scenario == "india":
            from hedgeproof.india import synthetic_indian_market
            from hedgeproof.ingest import _indian_series_info

            md = synthetic_indian_market()
            manifest = manifest_for(md, settings, [], "SYNTHETIC-INDIA", series_info=_indian_series_info,
                                    attribution="Source: SYNTHETIC-INDIA (illustrative)")[0].model_dump(mode="json")
            label = "SYNTHETIC-INDIA TEST FIXTURE"
        else:
            from hedgeproof.synthetic import synthetic_market

            md = synthetic_market()
            manifest = manifest_for(md, settings, [], "SYNTHETIC")[0].model_dump(mode="json")
            label = "SYNTHETIC TEST FIXTURE"
    else:
        if scenario == "india":
            from hedgeproof.india import load_indian_market_data

            manifest = load_manifest(dd)
            if manifest is None:
                raise SystemExit("No data/manifest.json. Put the PPAC/MCX files in data/india/raw/ and run: uv run hedgeproof ingest --scenario india ...")
            problems = verify_raw_files(manifest, REPO_ROOT)
            if problems:
                raise SystemExit(f"Raw data does not match the manifest: {problems}")
            md = load_indian_market_data(dd / "raw")
            label = "HISTORICAL MARKET REPLAY (Indian scenario)"
        else:
            from hedgeproof.data import load_market_data

            manifest = load_manifest(dd)
            if manifest is None:
                raise SystemExit("No data/manifest.json. Put the EIA files in data/raw/ and run: uv run hedgeproof ingest ...")
            problems = verify_raw_files(manifest, REPO_ROOT)
            if problems:
                raise SystemExit(f"Raw data does not match the manifest: {problems}")
            md = load_market_data(dd / "raw")
            label = "HISTORICAL MARKET REPLAY"

    if scenario == "india":
        db_path = db or str(VAR_DIR / {"final": "hedgeproof_india.db", "rehearsal": "rehearsal_india.db", "test": "synthetic_india.db"}[mode])
    else:
        db_path = db or str(VAR_DIR / {"final": "hedgeproof.db", "rehearsal": "rehearsal.db", "test": "synthetic.db"}[mode])

    sources_path = dd / "sources" / "sources.json"
    if sources_path.exists():
        sources = json.loads(sources_path.read_text())
        if inject_source:
            sources.append(json.loads((REPO_ROOT / "tests" / "fixtures" / "injected_source.json").read_text()))
    else:
        sources = _load_sources(inject_source)
    sandbox = DockerSandbox()
    # Open the database last: the core owns the store and closes it if its own construction fails.
    return TrustedCore(settings, Store(db_path), md, mode, manifest, sandbox=sandbox, operator_code=operator_code,
                       data_label=label, sources=sources)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from hedgeproof.trusted.core import new_operator_code
    from hedgeproof.trusted.service import create_app

    code = new_operator_code()
    core = build_core(args.mode, args.synthetic, args.db, args.inject_source, code, scenario=getattr(args, "scenario", "us"))
    h = core.health()
    bar = "=" * 64
    print(bar)
    print(f" HedgeProof trusted service  |  mode: {args.mode.upper()}  |  data: {h['data_label']}")
    print(f" policy {h['policy_version']} {h['policy_sha256'][:16]}…  replay date {h['replay_date']}")
    print(f" holdout {h['holdout_state'].upper()}  |  sandbox: {h['sandbox']['detail']}")
    print(f" listening on http://{args.host}:{args.port} (local only)")
    print(bar)
    print(f" OPERATOR CODE for this session: {code}")
    print(" Type it into the dashboard to approve an order. Never give it to the agent process.")
    print(bar, flush=True)
    try:
        uvicorn.run(create_app(core), host=args.host, port=args.port, log_level="warning")
    finally:
        core.close()  # idempotent; also closed by the app's shutdown hook


def cmd_dashboard(args: argparse.Namespace) -> None:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["HEDGEPROOF_SERVICE_URL"] = args.service
    app = Path(__file__).with_name("dashboard.py")
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), "--server.address", "127.0.0.1",
                              "--server.port", str(args.port), "--browser.gatherUsageStats", "false"], env=env))


def cmd_ingest(args: argparse.Namespace) -> None:
    from hedgeproof.data import parse_ist
    from hedgeproof.ingest import ingest

    scenario = getattr(args, "scenario", "us")
    if scenario == "india":
        cfg_dir = REPO_ROOT / "config" / "india"
        data_dir = DATA_DIR / "india"
    else:
        cfg_dir = None
        data_dir = DATA_DIR
    settings = load_settings(cfg_dir if cfg_dir else None)
    raw_dir = data_dir / "raw"
    out = ingest(settings, raw_dir, parse_ist(args.retrieved_at), args.retrieved_by, out_dir=data_dir, scenario=scenario)
    m = out["manifest"]
    print(json.dumps({"manifest_id": m["id"], "manifest_sha256": m["sha256"], "split_counts": out["split_counts"],
                      "sessions": m["sessions"], "spot_missing_on_sessions": m["spot_missing_on_sessions"],
                      "continuity": {k: out["continuity"][k] for k in ("boundaries", "flagged", "threshold")},
                      "rejected": out["rejected"], "series": m["series"]}, indent=1, default=str))


def cmd_sandbox_build(args: argparse.Namespace) -> None:
    from hedgeproof.sandbox import IMAGE

    cmd = ["docker", "build", "-t", IMAGE]
    extra_ca = os.environ.get("HEDGEPROOF_EXTRA_CA")  # only for build hosts behind a TLS-inspecting proxy
    if extra_ca:
        cmd += ["--secret", f"id=extra_ca,src={extra_ca}"]
    sys.exit(subprocess.call([*cmd, str(REPO_ROOT / "sandbox")]))


def cmd_sandbox_check(args: argparse.Namespace) -> None:
    from hedgeproof.sandbox import DockerSandbox, self_check

    print(json.dumps(self_check(DockerSandbox()), indent=1))


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # never crash on a console that cannot print a character
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    p = argparse.ArgumentParser(prog="hedgeproof", description="HedgeProof: verifiable AI hedge research for city bus fuel budgets")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="start the trusted service (prints the operator code)")
    s.add_argument("--mode", choices=["final", "rehearsal", "test"], default="rehearsal")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--db", default=None, help="SQLite path (default var/<mode>.db)")
    s.add_argument("--synthetic", action="store_true", help="SYNTHETIC data (test mode only)")
    s.add_argument("--inject-source", action="store_true", help="add the untrusted injected memo (scenario E2)")
    s.add_argument("--scenario", choices=["us", "india"], default="us", help="which scenario (config + data) to run")
    s.set_defaults(fn=cmd_serve)

    d = sub.add_parser("dashboard", help="start the Streamlit dashboard on localhost")
    d.add_argument("--port", type=int, default=8501)
    d.add_argument("--service", default=f"http://127.0.0.1:{DEFAULT_PORT}")
    d.set_defaults(fn=cmd_dashboard)

    i = sub.add_parser("ingest", help="hash the raw files and build the manifest and period table")
    i.add_argument("--retrieved-at", required=True, help="download time reported by the team, IST, e.g. 2026-10-24T12:30")
    i.add_argument("--retrieved-by", required=True, help="who downloaded the files")
    i.add_argument("--scenario", choices=["us", "india"], default="us", help="which scenario to ingest")
    i.set_defaults(fn=cmd_ingest)

    b = sub.add_parser("sandbox-build", help="build the hedgeproof-sandbox Docker image")
    b.set_defaults(fn=cmd_sandbox_build)
    c = sub.add_parser("sandbox-check", help="verify the sandbox isolation through the runner itself")
    c.set_defaults(fn=cmd_sandbox_check)

    from hedgeproof.agents import cli as agent_cli

    agent_cli.register(sub)
    from hedgeproof.evals import cli as eval_cli

    eval_cli.register(sub)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
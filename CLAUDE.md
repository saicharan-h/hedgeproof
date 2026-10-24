# HedgeProof: project instructions for Claude sessions

Read this first after any context reset, then `docs/BUILD_STATE.md`. Do not restart completed setup or regenerate the application from scratch: inspect the files and continue.

## What this is

HedgeProof (team Signal Syndicate, ChronoForge 2026, Agentic AI track). AI agents research a diesel fuel hedge for a fictional city bus agency (styled on an Indian city bus operator for hackathon context; underlying market data is U.S. public EIA data used as an illustrative proxy); trusted code computes every number and enforces the agency's policy; a human approves the exact proposal before a simulated paper order can proceed. Core mechanism: the Mandate-Bound Evidence Gate (rules G01 to G12).

Authority: (1) organizer rules and the team's latest facts, (2) `docs/planning/Submission.pdf`, (3) the planning documents in `docs/planning/`. Current overrides are in `docs/DECISIONS.md` (D-017 onward).

## Non-negotiables

- No real-money trading, no broker connection. All orders are simulated paper orders.
- Never invent data, results, uploads, links or approvals. Targets are not results. Use the status labels PLANNED, IMPLEMENTED, VERIFIED (needs command output or an inspected file), BLOCKED, DEFERRED.
- Never commit env files of any kind (including `.env.example`), keys, or databases. `tests/test_hygiene.py` checks tracked files.
- Never ask anyone to paste an API key into chat. Never print a key. Live API calls run on the demo laptop; the cloud session has no key.
- API spending: $10 total (D-018) through the spend controller in `src/hedgeproof/agents/spend.py`. Do not buy credits, raise limits or enable auto-reload.
- The real holdout (`HP-FINAL`, Feb 2020 to Feb 2024) stays sealed until after checkpoint 2 and the correctness checklist. Tests use `TEST-…` lineages, temporary databases and SYNTHETIC data. Never open the real holdout from tests or rehearsals.
- Runtime agents never get the operator code, never change policy, never compute final metrics and never run generated code outside the Docker sandbox.
- Commits: author `Claude <noreply@anthropic.com>`; teammates commit under their own names. No empty commits, no backdating, no force-push. Develop on the session branch and integrate into `main` by pull request (D-019).

## Layout

- `config/`: `policy.toml` (frozen policy v1), `experiment.toml` (frozen splits, costs, metrics, pass rule), `agency_fixture.toml` (declared scenario), `runtime.toml` (models, API budget; not hashed into evidence).
- `src/hedgeproof/`: `records.py` (typed records, hashing), `config.py`, `data.py` (EIA loader, period table), `engine.py` (sizing, metrics, baselines), `synthetic.py` (test data only), `sandbox.py` + `sandbox/` (Docker runner), `trusted/` (store, gate, simulator, FastAPI service), `agents/` (spend controller, Claude client, roles, LangGraph workflow), `dashboard.py` (Streamlit), `evals/` (16 cases), `cli.py`.
- `data/raw/` unmodified EIA files; `data/manifest.json`; `data/derived/period_table.csv`.
- `results/`: committed evidence (evaluation results, recorded runs, holdout report when opened).

## Commands

```
uv sync
uv run pytest -q                 # deterministic tests, no API calls
uv run hedgeproof --help
```

## Owners (each teammate reviews, runs and explains their part)

- Saicharan: orchestration, spend ledger, integration, demo narrative.
- Nikshep: data, quant engine, baselines, financial checks.
- Kruthik: agent tools, sandbox, critique and repair.
- Lohith: gate, paper simulator, dashboard.

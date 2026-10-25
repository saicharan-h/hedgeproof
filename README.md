# HedgeProof

**Protect city bus budgets with verifiable AI hedge research.**
Team **Signal Syndicate** (Saicharan Hariharan, Nikshep Doggalli, Kruthik M, Lohith Gollapelli), JSS Science & Technology University, Mysuru.
ChronoForge 2026 final round · theme *Cities of the Future* · track *Agentic AI*.

> AI investigates a fuel hedge. Independent code checks the calculations and agency rules. A human approves the exact proposal before a simulated order can proceed.

## Demo video

**Google Drive link: https://drive.google.com/file/d/1bmmWBc9U8wPjjZzHx-BIUudGHLy_Hgi5/view?usp=sharing

## The problem

A city bus agency buys diesel every month but fixes its fuel budget months earlier, so a price spike lands on service budgets. Transit agencies already hedge this with futures (MTA's October 2025 Fuel Hedge Program Report describes hedging 50% of its next 12 months of projected diesel). The target user is a **transit-agency treasury analyst** preparing a fuel-budget recommendation for a finance committee. The hard question: does a proposed hedge really offset the agency's own price exposure, survive an honest test, and stay inside the agency's mandate? A persuasive AI explanation is not enough: a future-data leak, the wrong futures contract or an oversized position can make an attractive backtest unsafe to act on.

> **Indian context (hackathon framing):** the fictional agency is styled on an Indian city bus operator (for example BMTC, Bengaluru). The underlying market data is U.S. public EIA data used as an illustrative proxy only; this is not a validated deployment for any real Indian (or other) transit agency and no Indian market data is used or claimed. See the Limitations section.

## What HedgeProof does

- **AI agents research the hedge** (five bounded roles): Research proposes an estimator from data profiles and cited sources; Coder writes the estimator, runs it in a locked-down sandbox and repairs failed tests; Critique runs diagnostics and decides to revise, reject, advance or stop; Risk explains gate failures and proposes a compliant size; Execution submits an approved paper order and reconciles a lost acknowledgement before any retry.
- **Trusted code computes every number**: positions, cash flows, budget error, variance, Budget-at-Risk, caps and the bootstrap intervals. Agents never report their own metrics.
- **The Mandate-Bound Evidence Gate** (our core contribution) lets a paper order reach the simulator only if it matches a verified evidence record (data, estimator, evaluation and policy hashes), passes every agency rule, and carries a human approval of that exact order. Missing or changed evidence, a breached rule or an unknown state blocks the order with a reason. A blocked order is never resized.

## Status at submission (25 Oct 2026, IST)

**In one paragraph:** the full pipeline is built and tested: real EIA data with a verified contract-roll rule, a trusted quant engine, the Mandate-Bound Evidence Gate (G01-G12) with operator-coded approvals and a paper simulator that reconciles a lost acknowledgement, a Docker sandbox for AI-written code, a dashboard, and five AI agent roles that ran **live** three times on Claude Haiku 5.5 for about three US cents in total. **Not completed before the deadline:** the real `HP-FINAL` research run, trusted validation scoring, the single opening of the sealed 2020-2024 holdout, and the single-agent comparison (E1-E3). The holdout was never opened, so this repository contains **no validation, holdout or comparative performance results**.

| Component | Status |
|---|---|
| Frozen policy, experiment and agency configs with hashes | Implemented |
| EIA loader, contract identity, period table, splits 10 / 23 / 49 | Implemented; verified on the committed EIA files (roll mapping checked on real prices; one development month rejected for a missing spot price) |
| Quant engine: sizing, budget-error identity, variance, BaR95, baselines, paired block bootstrap | Implemented; financial invariants pass |
| Trusted service: gate G01-G12, operator-coded approvals, paper simulator, reconciliation, holdout lock, evidence packets | Implemented; 16 deterministic cases pass on SYNTHETIC fixtures |
| Docker sandbox for generated code | Implemented; isolation verified through the runner (cloud container) |
| Five-role LangGraph workflow with spend controller | Implemented; verified with the labelled scripted test double and in three live research runs on real data (Claude Haiku 5.5 via OpenRouter; see Tests and results) |
| Streamlit dashboard | Implemented; verified in a headless browser and used live at checkpoint 1 |
| Development baselines on EIA data | Done (labelled development-only, n = 9; see Tests and results) |
| Real experiment `HP-FINAL`: validation scoring, freeze, single holdout opening | **Not run** (holdout sealed, never opened) |
| Model-dependent trials E1-E3 and single-agent comparison | **Not run** |
| Live order flow with the Risk and Execution agents | Verified with the scripted test double only (gate block, approval, lost acknowledgement, one fill); not run live |
| GASB-informed effectiveness diagnostic (proposal stretch module) | Deferred |

Live progress, test counts, hashes, spend and blockers: [`docs/BUILD_STATE.md`](docs/BUILD_STATE.md). Decisions and overrides: [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Architecture (the running prototype)

```
 Analyst ──approve (operator code)──► Dashboard (Streamlit, localhost)
                                           │ reads
 Agent runner (LangGraph + Claude API) ──► Trusted service (FastAPI, 127.0.0.1)
   5 roles, untrusted reasoning             data views with a research clock · engine · evidence registry
   no DB access, no approval route          gate G01-G12 · approvals · holdout lock · paper simulator
   spend controller (var/spend.db)          append-only events · SQLite (var/<mode>.db)
                                                 │ docker run -i (one job, one window per line)
                                                 ▼
                                   Sandbox container: generated estimator only
                                   no network · read-only root · uid 65534 · no capabilities · CPU/memory/PID limits
```

- **Untrusted:** model output (hypotheses, estimator code, critiques, proposed sizes). **Trusted:** the service's calculations, cutoffs, budgets, policy checks and approvals.
- **One process per boundary:** the agent process never holds the operator code, has no tool to approve or open the holdout, and generated code never runs on the host.
- Scalability is a design argument, not a measured claim: the same evidence record and gate apply to other fuels, other agencies' policies or longer horizons by changing the frozen configs; the prototype deliberately stays at one agency, one price pair and one monthly cycle.

## Quantitative method (summary)

- **Data:** EIA U.S. Gulf Coast ULSD spot `EER_EPD2DXL0_PF4_RGC_DPG` (fuel-price proxy) and NY Harbor futures Contracts 1-3 (`EER_EPD2F_PE1/PE2/PE3_Y35NY_DPG`). EIA futures history ends 5 Apr 2024.
- **Contract identity:** for hedge month p, buy Contract 2 at the first session of p (delivery p+2) and sell it as Contract 1 at the first session of p+1, the same delivery month; both legs record and assert it.
- **No look-ahead:** decision p trains only on positions closed by p-2 (position p-1 closes at the same close where p fills); spot is usable one session later; sizing uses Contract 3's previous close (same delivery month), never the fill.
- **Estimator and sizing:** h = clip(Cov(dS, dF) / Var(dF), 0, 0.75); n = min(floor(hQ / 42,000), 75% cap, cash-stress cap). Costs: $10 round trip plus one $4.20 tick per side per contract.
- **Metrics:** budget error = Q·dS − 42,000·n·dF + costs; sample variance and empirical 95th percentile (Budget-at-Risk) on identical positions for no hedge, fixed 50% and adaptive; paired moving-block bootstrap (block 3, 2,000 resamples, seed 20261024, 90% intervals).
- **Splits:** development Feb-Nov 2017 (10 positions), validation Jan 2018-Nov 2019 (23), sealed holdout Feb 2020-Feb 2024 (49), opened once. Boundary-crossing positions are purged.
- **Pass rule (frozen):** PASS if Var(adaptive) < Var(unhedged), BaR95(adaptive) ≤ BaR95(unhedged) and zero policy breaches; otherwise ABSTAIN. Adaptive versus fixed 50% is always reported, never hidden.

Full specification: `docs/planning/02_HedgeProof_Interface_Contract.md` (with the overrides in `docs/DECISIONS.md`).

## Quick start (Windows PowerShell, macOS or Linux)

Prerequisites: Git, [uv](https://docs.astral.sh/uv/), Docker Desktop running.

```
git clone https://github.com/saicharan-h/hedgeproof
cd hedgeproof
uv sync
uv run pytest -q                      # deterministic tests, no API calls
uv run hedgeproof sandbox-build       # builds the hedgeproof-sandbox:1 image (one time)
uv run hedgeproof sandbox-check       # verifies isolation through the runner itself
```

Run the demo on the **SYNTHETIC test fixture** (three terminals):

```
uv run hedgeproof serve --mode test                  # terminal 1: prints the OPERATOR CODE
uv run hedgeproof dashboard                          # terminal 2: opens http://127.0.0.1:8501
uv run hedgeproof run research --lineage TEST-DEMO --agents scripted
uv run hedgeproof run execute --lineage TEST-DEMO --agents scripted --request-contracts 15
```

`--agents scripted` is a labelled test double that makes no AI calls. With API funding, use `--agents live` (see below).

Run it on the **real EIA data** (already committed in `data/raw/`; the service checks the files against `data/manifest.json` at start):

```
uv run hedgeproof serve --mode rehearsal              # terminal 1: real data, development research only
uv run hedgeproof dashboard                           # terminal 2
uv run hedgeproof run research --lineage REHEARSAL-CP1 --agents scripted
uv run hedgeproof run execute --lineage REHEARSAL-CP1 --agents scripted --request-contracts 15
```

`--mode final` serves the real experiment `HP-FINAL` (validation scoring and the single holdout opening); it is not used for rehearsals. To rebuild the manifest from fresh downloads: `uv run hedgeproof ingest --retrieved-at 2026-10-24T12:03 --retrieved-by "Name"`.

Other commands: `uv run hedgeproof baseline` (development baselines on EIA data, writes `results/`), `uv run hedgeproof evals` (16 cases, writes `results/`), `uv run hedgeproof spend` (API ledger), `uv run hedgeproof smoke` (one tiny live call).

### Vercel deployment (agentic AI demo)

Deploy the trusted service + a landing page + an OpenRouter-backed chat to
Vercel (serverless). See `docs/VERCEL_DEPLOYMENT.md` and `docs/USER_FLOW.md`.

```
# set OPENROUTER_API_KEY, HEDGEPROOF_SCENARIO, HEDGEPROOF_OPERATOR_CODE in Vercel
# import repo -> deploy
```

The landing page is `public/index.html`; the API is `api/index.py`.

### Indian scenario (parallel, clearly labelled)

A second, illustrative scenario for an Indian city bus agency (BMTC-style) using
MCX crude-oil futures as a proxy for diesel and an Indian retail diesel price as
the physical price proxy. Runs on the same engine and gate, with its own config
(`config/india/`) and data folder (`data/india/`):

```
uv run hedgeproof serve --mode test --scenario india     # SYNTHETIC-INDIA data
uv run hedgeproof dashboard
```

See `docs/INDIA_SCENARIO.md`. No real Indian market data is shipped; the
loaders accept PPAC and MCX files when available. No performance claims are made.

### Environment variables (no env files in this repository)

| Name | Needed for | Example (dummy) |
|---|---|---|
| `OPENROUTER_API_KEY` | live agent runs only, on the demo laptop (provider: OpenRouter, see `config/runtime.toml`) | `sk-or-…` (never commit, print or paste it) |
| `ANTHROPIC_API_KEY` | only if `config/runtime.toml` is switched to the Anthropic provider | `sk-ant-…` |
| `HEDGEPROOF_EXTRA_CA` | only when building the sandbox behind a TLS-inspecting proxy | `/path/to/ca-bundle.crt` |
| `HEDGEPROOF_CONFIG_DIR` | optional alternative config folder | `config` |

On Windows set the key through *Start → Edit environment variables for your account* (name `OPENROUTER_API_KEY`), then open a new terminal. Do not use `setx` with the key in the command (PowerShell saves history).

## API budget behaviour

The team's application API budget is **$10 total**: $7 for development, rehearsals and checkpoints, $3 reserved for the final demo and judging, and a provisional **$1 per research run**. One durable SQLite ledger (`var/spend.db`) serializes paid calls and **reserves the worst-case cost before each call** (input upper bound from request size at the highest input or cache-write rate, plus `max_tokens` at the output rate, which includes thinking). After the call it settles with the real token usage; a timeout keeps the full reservation as uncertain. Work that would exceed the run, phase or total allowance is refused before dispatch with a clear `BUDGET_EXHAUSTED` state. This is a guard, not a guaranteed cap; the hard cap is the prepaid Console balance with auto-reload off. Deterministic tests, backtests and the 16 cases make no paid calls. Provider: the team's $10 is OpenRouter credit, so the official Anthropic SDK calls OpenRouter's Anthropic-compatible endpoint (`https://openrouter.ai/api`, key sent as a Bearer token). Model: `anthropic/claude-haiku-5.5` for every agent role (D-039; `anthropic/claude-sonnet-5.5` stays configured as an option in `config/runtime.toml`). `uv run hedgeproof smoke` compares the configured prices with OpenRouter's live price list before any run; recorded costs are estimates from token usage at those (conservative) prices, and OpenRouter's activity page is the authoritative bill.

## Security and privacy controls

- **No personal data:** public market data and one labelled fictional agency fixture (420,000 gal/month). No passenger, employee, bank or customer records.
- **Sandbox:** generated code runs only in Docker with `--network none --read-only --tmpfs /tmp:size=16m --memory 256m --cpus 1 --pids-limit 64 --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges`, no volumes, no Docker socket, no environment variables; 5 s per window, 120 s per job, killed on timeout; one data window per line. Static checks (imports, dangerous names, dunder access, future date literals, size) are an extra filter.
- **Separation of duties:** human-only actions (approve an exact intent, open the holdout once, arm a labelled fault) need a per-start operator code printed only in the trusted service window; 10 wrong codes lock the service. This is a local prototype mechanism, not production authentication.
- **Fail closed:** missing evidence, changed hashes, stale data, unknown order state and unreachable checks all block. Changed evidence or order terms produce a new intent hash, so old approvals cannot be reused.
- **Prompt injection:** retrieved text is labelled data; policy and approvals are enforced independently of what any model says (case F8).
- **Local only:** the service and dashboard bind to 127.0.0.1. Append-only events and evidence records (database triggers). Hashes detect changes; a local SQLite file is not tamper-proof.
- **Secrets:** no env files are tracked (`tests/test_hygiene.py` also scans for Anthropic and OpenRouter keys); the trusted service and the dashboard drop API keys from their own process environment at start; the public Vercel showcase publishes no operator code and keeps chat off by default (`docs/VERCEL_DEPLOYMENT.md`).

## Tests and results

`uv run pytest -q`: **146 deterministic tests**, all passing in the cloud container with Docker (financial invariants, the 16 predefined cases, HTTP boundary tests, sandbox isolation, spend controller, model client against a mock provider, database connection lifecycle including a Windows file-locking emulation, real-data checks, research-loop fixes, workflow with the scripted test double). On the Windows demo laptop the suite ran with no assertion failures; 21 temporary-folder permission errors there were fixed by D-038. No test makes an API call.

**Predefined cases** ([`results/EVAL_SUMMARY.md`](results/EVAL_SUMMARY.md), SYNTHETIC fixtures): faults caught **8 / 8**, valid cases handled **8 / 8**, zero policy-violating or duplicate orders. **Gate ablation:** with the gate bypassed in an isolated scratch simulator, 5 of 5 replayed bad orders would execute; with the gate on, 0. These check the enforcement code; they do not measure hedge performance.

**Live AI research runs** (real EIA data, development split only, rehearsal lineages; model `anthropic/claude-haiku-5.5` through OpenRouter; costs measured by the spend controller from token usage):

| Run | Model calls | Tokens in / out | Cost | Outcome and what it showed |
|---|---|---|---|---|
| [`RUN-e56d7478db40`](results/runs/RUN-e56d7478db40.json) | 21 | 68,906 / 9,469 | $0.0093 | ABSTAIN. The critic asked to revise three times and the coder resubmitted the same configuration, so the run used its 3 candidates. Fixed in trusted code: repeated configurations are refused and diagnostics explain identical results (D-037) |
| [`RUN-3f1c27ab6816`](results/runs/RUN-3f1c27ab6816.json) | 21 | 80,797 / 10,968 | $0.0111 | ABSTAIN. Three genuinely different estimators (OLS 36, EWMA halflife 12, EWMA halflife 6 with shrinkage), each verified in the sandbox; the critic found that the 75% limit binds in all 9 development months, so development data cannot tell them apart (D-038) |
| `RUN-b8f67926b9d2` (console output; trace on the demo laptop) | 21 | 93,940 / 7,583 | $0.0102 | ABSTAIN. Docker was not running: the trusted service refused to execute any AI-written code ("reduced autonomy"), the coder gave up three times, and the run stopped instead of skipping verification |

Total application API spend at submission: **$0.0358** of the $10 allowance (including smoke tests). Two attempts with Claude Sonnet 5.5 were refused by OpenRouter before any charge (`402 billing_error`: the key's remaining allowance), so Haiku was used for every role (D-039).

**Development baselines on EIA data** (`uv run hedgeproof baseline` → [`results/development_baselines.json`](results/development_baselines.json); data manifest `DM-f5615282b75c`; development split Feb-Nov 2017, **9 scored positions** because June 2017 has no Gulf Coast spot price on its exit day and is rejected, not patched):

| Strategy | Budget-error std | Budget-at-Risk (95th pct) | Avg contracts | Policy breaches |
|---|---|---|---|---|
| No hedge | $36,648 | $64,932 | 0 | 0 |
| Fixed 50% | $23,615 | $41,210 | 5 | 0 |
| Fixed script (vetted 36-position OLS) | $20,053 | $31,721 | 7 (75% cap binds; raw ratio 1.05-1.10) | 0 |

90% paired block-bootstrap interval for the change in standard deviation, fixed script vs no hedge: −$23,217 to −$8,112 (vs fixed 50%: −$6,290 to −$546). This is a tiny development sample, not validation or holdout evidence, and not a performance or savings claim. Validation and the sealed holdout are reported only through the planned single evaluation.

## Limitations

- Historical paper research only; no broker, no real money. EIA futures data ends 5 Apr 2024, so the operational paper order (replay 1 Apr 2024) cannot be scored.
- U.S. Gulf Coast spot is a proxy for an agency's invoice price; the 420,000-gallon forecast is a declared scenario. This is a historical U.S. data example, not a validated deployment for an Indian (or any) transit agency.
- Fills, the one-session spot lag, costs and the cash-stress scenario are declared assumptions; EIA revisions are not available.
- Small samples (10 / 23 / 49 positions): intervals are wide and we make no statistical-significance claims.
- **Not completed:** the real `HP-FINAL` run (validation scoring, freeze, the single holdout opening) and the single-agent / E1-E3 comparison. There is therefore no evidence yet that the agents beat the fixed script; on development data the 75% limit binds every month, so they score the same.
- Live agent runs used the smaller model (Claude Haiku 5.5) and covered research only; the Risk and Execution agents and the order flow were exercised with the labelled scripted test double.

## Repository map

`config/` frozen configs · `src/hedgeproof/` (`data.py`, `engine.py`, `sandbox.py`, `trusted/`, `agents/`, `dashboard.py`, `evals/`, `cli.py`) · `sandbox/` image and harness · `data/` raw files, manifest, sources · `results/` committed evidence · `tests/` · `docs/` (BUILD_STATE, DECISIONS, planning documents and the accepted `Submission.pdf`).

## Team and ownership

- Saicharan Hariharan: orchestration, spend ledger, integration, demo narrative.
- Nikshep Doggalli: data, quant engine, baselines, financial checks.
- Kruthik M: agent tools, sandbox, critique and repair.
- Lohith Gollapelli: gate, paper simulator, dashboard.

## Acknowledgments

- **Data:** U.S. Energy Information Administration (EIA), petroleum spot and NYMEX futures prices: `PET_PRI_FUT_S1_D.xls` and `PET_PRI_SPT_S1_D.xls`, downloaded 24 Oct 2026, 12:03 PM IST, committed unmodified with SHA-256 hashes in `data/manifest.json` (public domain). Contract facts: CME Group NYMEX Rulebook chapter 150 (NY Harbor ULSD futures).
- **Context:** MTA Fuel Hedge Program Report (27 Oct 2025).
- **Related work:** TradingAgents (TauricResearch) and FinRobot (AI4Finance Foundation) for multi-agent finance and deterministic finance separated from LLM narration; HedgeProof's distinction is binding each paper order to the agency's exposure, a frozen policy and a reproducible evidence record. No code from those projects is used.
- **Libraries:** Anthropic Python SDK, LangGraph, FastAPI, Uvicorn, Pydantic, Streamlit, NumPy, pandas, xlrd, httpx, pytest; Docker.
- **AI assistance:** application code and documents were written with AI assistance from Claude Code (Anthropic) during the hacking period; Claude's commits carry the author `Claude <noreply@anthropic.com>`. On 24 Oct (~1:10 PM IST) the history of `main` was rewritten and earlier Claude-authored commits now show a teammate as author; pull requests #1 and #2 and `docs/DECISIONS.md` (D-036) record the original authorship. The accepted proposal was drafted with AI assistance, as stated in it.

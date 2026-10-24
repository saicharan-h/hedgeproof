# HedgeProof build state

Updated: Sat 24 Oct 2026, 12:00 PM IST. Labels: PLANNED, IMPLEMENTED, VERIFIED (command output or inspected file), BLOCKED, DEFERRED.

## Event facts

- Hacking round: officially started (team-confirmed; exact announcement time not supplied).
- Checkpoint 1: Sat 24 Oct, 4:00 PM IST. Checkpoint 2: Sat 24 Oct, 10:00 PM IST (unless organizers update it).
- Final submission deadline: **not yet confirmed**. Demo video length: not confirmed.

## Branch and commits

- Working branch: `claude/wonderful-keller-enn1fn`; integrates into `main` by pull request (D-019). `main` still holds only the planning upload until the PR is merged.
- Pushed commits on the branch: `2ced2ff` (bootstrap, data, engine), `4030fa9` (trusted service, gate, sandbox, 16 cases), `efd4213` (agents, spend controller, dashboard, eval results), plus the README/state commit that contains this file.

## Environment facts

| Item | Status |
|---|---|
| Cloud session: Python 3.12.3, uv 0.11.32, Docker 29.9.2 daemon, image `hedgeproof-sandbox:1` built | VERIFIED (cloud container) |
| Cloud network: PyPI and Docker Hub reachable; `www.eia.gov` blocked (proxy 403); sandbox build needs the proxy CA as a BuildKit secret here (`HEDGEPROOF_EXTRA_CA`), not on the laptop | VERIFIED |
| Demo laptop (Windows 11): WSL, Docker Desktop 29.9.2, checks A/B/C, Git, uv, Python 3.12.15 | Reported PASSED by Saicharan; HedgeProof itself not yet run there |
| Dependencies resolve and lock (77 packages, `uv.lock`) | VERIFIED |

## Components

| Component | Status | Evidence |
|---|---|---|
| Typed records and canonical hashing | IMPLEMENTED, VERIFIED | tamper test; `tests/test_invariants.py` |
| Frozen configs and hashes | IMPLEMENTED | hashes below |
| EIA loader and period table | IMPLEMENTED; VERIFIED on SYNTHETIC data only | real files **BLOCKED** (see blockers) |
| Quant engine and baselines | IMPLEMENTED, VERIFIED (SYNTHETIC) | invariants 1-5, 7-9 pass |
| Trusted service: gate G01-G12, approvals with operator code, simulator, reconciliation, holdout lock, evidence packets, FastAPI | IMPLEMENTED, VERIFIED (SYNTHETIC) | 16 cases; HTTP tests; multi-process run over HTTP |
| Sandbox runner | IMPLEMENTED, VERIFIED (cloud container) | `hedgeproof sandbox-check`: uid 65534, network blocked, read-only root, CapEff 0, no host secrets, infinite loop killed at ~5 s, harness blocks `socket` import |
| Spend controller | IMPLEMENTED, VERIFIED (unit tests, no API calls) | `tests/test_spend.py` |
| Claude client (live) | IMPLEMENTED; **not yet exercised** (no API key or funding) | — |
| Five-role LangGraph workflow | IMPLEMENTED, VERIFIED with the labelled scripted test double | research: buggy estimator caught, repaired, verified, critiqued, validated, frozen; execution: 15-contract request blocked, 5/7 proposed, human approval awaited, lost ack reconciled by key, exactly 1 order |
| Dashboard | IMPLEMENTED, VERIFIED in headless Chromium (no exceptions; gate table shows all 12 rules) | screenshots taken in the cloud session |
| 16-case evaluation and gate ablation | IMPLEMENTED: faults 8/8, valid 8/8 on SYNTHETIC fixtures; ablation 5 violating orders gate-off vs 0 gate-on | `results/EVAL_SUMMARY.md` |
| Model-dependent trials (E1-E3, single-agent, fixed script) | PLANNED (needs API funding) | |
| GASB-informed diagnostic (stretch) | DEFERRED | |

## Tests

- `uv run pytest -q`: **53 passed** (24 Oct, 11:52 AM IST), deterministic, no API calls; Docker sandbox used by F2, V6, sandbox and workflow tests.

## Config hashes (SHA-256 of canonical JSON of parsed TOML)

| File | Hash |
|---|---|
| `config/policy.toml` (policy v1) | `cacdd77a59a317508209ac6d079805b62d422bcc13e299b4855a0c89103febc5` |
| `config/experiment.toml` | `3262a1d6681c5885303d803044691de350355938fc7751562613aac044a7ccde` |
| `config/agency_fixture.toml` | `733bd4b009cbd95dfbf03a7f3dca5f123215af4cf0f41e7dfebaa113e227c181` |

## API funding and spend

- Budget: $10 total ($7 dev / $3 final), $1 provisional per run (D-018).
- Console balance: last confirmed $0. Purchase: **not confirmed**. API key: **not confirmed**. Smoke test: **not run**.
- Measured application spend so far: **$0.00** (no application API calls made; all agent runs so far were the scripted test double).

## Research state

- Data version: none yet (waiting for the EIA files).
- Experiment `HP-FINAL`: 0 candidates, 0 repairs. Holdout: **SEALED** (never opened). TEST lineages on synthetic data only.

## Blockers

1. **EIA raw files**: `www.eia.gov` is blocked from the cloud session. A teammate downloads `PET_PRI_FUT_S1_D.xls` and `PET_PRI_SPT_S1_D.xls` and attaches them unmodified. Every empirical number waits on this.
2. **API funding and key**: needed only for live agent runs (on the demo laptop).

## Next

1. Ingest the real EIA files the moment they arrive: manifest, continuity check, split counts, development baselines.
2. Pull request to `main` for the team to merge before checkpoint 1.
3. Demo laptop: `uv sync`, `uv run pytest -q`, `uv run hedgeproof sandbox-build`, then the three-terminal demo.
4. Live smoke test and one measured run once funding and the key are confirmed.
5. `docs/DEMO_GUIDE.md` with the checkpoint-1 script.

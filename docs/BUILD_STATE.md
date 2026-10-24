# HedgeProof build state

Updated: Sat 24 Oct 2026, 11:40 AM IST. Labels: PLANNED, IMPLEMENTED, VERIFIED (command output or inspected file), BLOCKED, DEFERRED.

## Event facts

- Hacking round: officially started (team-confirmed; exact announcement time not supplied).
- Checkpoint 1: Sat 24 Oct, 4:00 PM IST. Checkpoint 2: Sat 24 Oct, 10:00 PM IST (unless organizers update it).
- Final submission deadline: **not yet confirmed**. Demo video length: not confirmed.

## Branch and commits

- Working branch: `claude/wonderful-keller-enn1fn` (integrates into `main` by pull request, D-019).
- Latest pushed commit: see `git log`; updated at each push.

## Environment facts

| Item | Status |
|---|---|
| Cloud session: Python 3.12.3, uv 0.11.32, Docker 29.9.2 daemon | VERIFIED (cloud container) |
| Cloud network: PyPI and Docker Hub reachable; `www.eia.gov` blocked (proxy 403) | VERIFIED |
| Demo laptop (Windows 11): WSL, Docker Desktop 29.9.2, checks A/B/C, Git, uv, Python 3.12.15 | Reported PASSED by Saicharan; not re-run by Claude |
| Dependencies resolve and lock (77 packages) | VERIFIED (`uv lock`, `uv sync`) |

## Components

| Component | Status | Evidence |
|---|---|---|
| Typed records and canonical hashing (`records.py`) | IMPLEMENTED | smoke test; tamper test |
| Frozen configs and hashes (`config/`) | IMPLEMENTED | hashes below |
| EIA loader and period table (`data.py`) | IMPLEMENTED, tested on SYNTHETIC data only | `tests/test_invariants.py`; real files BLOCKED (see blockers) |
| Quant engine and baselines (`engine.py`) | IMPLEMENTED | invariants 1, 3, 4, 5, 7, 8 pass on SYNTHETIC data |
| Trusted service: SQLite store, gate G01-G12, operator-coded approvals, paper simulator, ack-timeout reconciliation, holdout lock, evidence packets, FastAPI | IMPLEMENTED, VERIFIED on SYNTHETIC data | `tests/test_cases.py`, `tests/test_service_http.py` |
| Sandbox runner (Docker image `hedgeproof-sandbox:1`, harness, static checks, verification tests) | IMPLEMENTED, VERIFIED in the cloud container | `uv run hedgeproof sandbox-check`: uid 65534, network blocked, read-only root, CapEff 0, infinite loop killed at ~5 s |
| Agents and spend controller | PLANNED (next after dashboard) | |
| Dashboard | PLANNED (next) | |
| 16-case evaluation | IMPLEMENTED: 16/16 pass on SYNTHETIC data; gate ablation 5 violating orders with gate off vs 0 with gate on | `uv run pytest -q` |

## Tests

- `uv run pytest -q`: 44 passed (24 Oct, 11:38 AM IST), deterministic, no API calls (Docker sandbox used by F2, V6 and sandbox tests).

## Config hashes (SHA-256 of canonical JSON of parsed TOML)

| File | Hash |
|---|---|
| `config/policy.toml` (policy v1) | `cacdd77a59a317508209ac6d079805b62d422bcc13e299b4855a0c89103febc5` |
| `config/experiment.toml` | `3262a1d6681c5885303d803044691de350355938fc7751562613aac044a7ccde` |
| `config/agency_fixture.toml` | `733bd4b009cbd95dfbf03a7f3dca5f123215af4cf0f41e7dfebaa113e227c181` |

## API funding and spend

- Budget: $10 total ($7 dev / $3 final), $1 provisional per run (D-018).
- Console balance: last confirmed $0. Purchase: **not confirmed**. API key: **not confirmed**. Smoke test: **not run**.
- Measured spend so far: $0.00 (no application API calls made).

## Research state

- Data version: none yet (waiting for EIA files).
- Experiment `HP-FINAL`: 0 candidates, 0 repairs. Holdout: SEALED (never opened).

## Blockers

1. **EIA raw files**: `www.eia.gov` is blocked from the cloud session. A teammate must download `PET_PRI_FUT_S1_D.xls` and `PET_PRI_SPT_S1_D.xls` and attach them unmodified. Everything empirical waits on this.
2. **API funding and key**: needed only for live agent runs on the demo laptop.

## Next

Trusted service (store, gate G01 to G12, approvals, simulator, holdout lock), then the dashboard, then the sandbox and agent workflow.

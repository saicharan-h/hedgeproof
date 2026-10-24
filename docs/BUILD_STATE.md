# HedgeProof build state

Updated: Sat 24 Oct 2026, 1:08 PM IST. Labels: PLANNED, IMPLEMENTED, VERIFIED (command output or inspected file), BLOCKED, DEFERRED.

## Event facts

- Hacking round: officially started (team-confirmed; exact announcement time not supplied).
- Checkpoint 1: Sat 24 Oct, 4:00 PM IST. Checkpoint 2: Sat 24 Oct, 10:00 PM IST (unless organizers update it).
- Final submission deadline: **not yet confirmed**. Demo video length: not confirmed.

## Branch and commits

- Working branch: `claude/wonderful-keller-enn1fn`; integrates into `main` by pull request (D-019).
- PR #1 (prototype) merged 12:06 IST (`0b6025c`). Nikshep pushed `ce4af55` directly to `main` at 12:40 IST (Indian-context framing kept; test workaround replaced, D-030). PR #2 (Windows connection fix) merged (`4b6c66c`).
- Real EIA data, real-data checks and development baselines: on the branch for PR #3.

## Environment facts

| Item | Status |
|---|---|
| Cloud session: Python 3.12.3, uv 0.11.32, Docker 29.9.2 daemon, image `hedgeproof-sandbox:1` built | VERIFIED (cloud container) |
| Cloud network: PyPI and Docker Hub reachable; `www.eia.gov` blocked (proxy 403); sandbox build needs the proxy CA as a BuildKit secret here (`HEDGEPROOF_EXTRA_CA`), not on the laptop | VERIFIED |
| Demo laptop (Windows 11): WSL, Docker Desktop 29.9.2, checks A/B/C, Git, uv, Python 3.12.15 | Reported PASSED by Saicharan |
| Demo laptop: `uv sync` and `uv run hedgeproof sandbox-build` | Reported PASSED by Saicharan (12:45 IST) |
| Demo laptop: `uv run pytest -q` | PR #1 code: 24 failed, 32 passed (WinError 32). After PR #2: **64 passed**, reported by Saicharan (~1:00 PM IST). Real-data tests (PR #3) not yet run there |
| Dependencies resolve and lock (77 packages, `uv.lock`) | VERIFIED |

## Data version (HISTORICAL MARKET REPLAY, EIA public data)

| Item | Value |
|---|---|
| Files (committed unmodified in `data/raw/`) | `PET_PRI_FUT_S1_D.xls` 3,019,264 bytes, SHA-256 `bbd6e8e67c91e9ad2b96f6a8a0acd236a5a8b2df5d87615bb781c0d9c5ff5dc6`; `PET_PRI_SPT_S1_D.xls` 3,396,096 bytes, SHA-256 `69eeff72e7abb794f68f305b882d9782d4bd758144ac30f4db22a468d3a8cd3b` |
| Retrieval | Downloaded in a browser from the EIA links on 24 Oct 2026, 12:03 PM IST, by a team member (reported by Saicharan); attached to the session and copied byte-identical |
| Manifest | `data/manifest.json`, `DM-f5615282b75c`, SHA-256 `2631012ca501638e133a6cf7dc55364ea62d555809febd9c5811cfe50ad58592` |
| Series | Gulf Coast ULSD spot `EER_EPD2DXL0_PF4_RGC_DPG` 2006-06-14 to 2026-10-20 (5,104 obs); NY Harbor futures C1/C2/C3 to 2024-04-05; all "Dollars per Gallon" (asserted) |
| Sessions | 6,044 futures sessions; spot missing on 10 futures sessions since 2013 |
| Splits | development 10, validation 23, holdout 49, purged 4 (labels as planned) |
| Rejected rows (never patched) | 1: hedge month 2017-06 (development), no Gulf Coast spot on its exit session 2017-07-03. Development therefore scores **9** positions |
| Roll mapping | VERIFIED on real data: at 131 month boundaries since May 2013, C1[first]-C2[last] and C2[first]-C3[last] correlate 0.993 with median difference $0.0010 (same as ordinary days, 0.952 / $0.0010); the no-roll alternative gives 0.825 / $0.0070. The contract's screen flags 22 of 131 boundaries above 3 x the median daily move (large market moves, not mapping errors). `data/derived/continuity_report.json` |
| Operational entry | 1 Apr 2024 (first session after Good Friday); delivery June 2024; F_ref = C3 close on 28 Mar 2024 ($2.62) |

## Results so far (labelled; no performance claims)

- **Development baselines** (`uv run hedgeproof baseline`, `results/development_baselines.json`, n = 9 scored positions, Feb-Nov 2017 excluding June): budget-error standard deviation no hedge $36,648, fixed 50% $23,615, fixed script OLS-36 $20,053; BaR95 $64,932 / $41,210 / $31,721; 0 policy breaches. The raw OLS ratio was 1.05-1.10 every month, so the 75% cap bound (7 contracts). 90% block-bootstrap interval for the change in standard deviation, OLS-36 vs no hedge: -$23,217 to -$8,112; vs fixed 50%: -$6,290 to -$546. Tiny sample; development data only.
- **Rehearsal flow on real data** (cloud, scripted test double, rehearsal DB): research → coder (repair after a failed zero-variance test) → critique → stopped at development; execution: 15-contract request BLOCKED (EXPOSURE_CAP; CASH_STRESS_CAP $412,650 > $250,000), 5 contracts approved with the operator code, lost acknowledgement reconciled by key, 1 paper fill at $2.626 on 1 Apr 2024.
- Deterministic evaluation (SYNTHETIC fixtures): faults 8/8, valid 8/8; gate ablation 5 violating orders gate-off vs 0 gate-on (`results/EVAL_SUMMARY.md`).

## Components

| Component | Status | Evidence |
|---|---|---|
| Typed records and canonical hashing | IMPLEMENTED, VERIFIED | tamper test; `tests/test_invariants.py` |
| Frozen configs and hashes | IMPLEMENTED | hashes below |
| EIA loader and period table | IMPLEMENTED, VERIFIED on real EIA data | `tests/test_realdata.py` (7 checks incl. future perturbation on real prices) |
| Quant engine and baselines | IMPLEMENTED, VERIFIED | invariants 1-9; development baselines on real data |
| Trusted service: gate G01-G12, approvals with operator code, simulator, reconciliation, holdout lock, evidence packets, FastAPI | IMPLEMENTED, VERIFIED | 16 cases; HTTP tests; rehearsal flow over HTTP on real data |
| Database connection lifecycle (Windows) | IMPLEMENTED, VERIFIED (Linux with Windows-like guard; Windows 64 passed reported) | `tests/test_lifecycle.py` |
| Sandbox runner | IMPLEMENTED, VERIFIED (cloud container) | `hedgeproof sandbox-check` |
| Spend controller | IMPLEMENTED, VERIFIED (unit and mock-transport tests, no API calls) | `tests/test_spend.py`, `tests/test_claude_client.py` |
| Claude client (live) | IMPLEMENTED; **not yet exercised** (no API key or funding) | — |
| Five-role LangGraph workflow | IMPLEMENTED, VERIFIED with the labelled scripted test double (synthetic and real data) | `tests/test_workflow.py`; rehearsal run above |
| Dashboard | IMPLEMENTED, VERIFIED in headless Chromium on real data (no exceptions) | screenshots in the cloud session |
| Model-dependent trials (E1-E3, single-agent, fixed script) | PLANNED (needs API funding) | |
| GASB-informed diagnostic (stretch) | DEFERRED | |

## Tests

- `uv run pytest -q`: **71 passed** in the cloud container (24 Oct, about 1:05 PM IST): 64 previous plus 7 real-data checks, with the Windows-like file-locking guard active. No API calls.

## Config hashes (SHA-256 of canonical JSON of parsed TOML)

| File | Hash |
|---|---|
| `config/policy.toml` (policy v1) | `cacdd77a59a317508209ac6d079805b62d422bcc13e299b4855a0c89103febc5` |
| `config/experiment.toml` | `3262a1d6681c5885303d803044691de350355938fc7751562613aac044a7ccde` |
| `config/agency_fixture.toml` | `a0cdfdf66b8d2c7691757899f280159d2a093d07ff0b9353d82a6cc6b342be78` (changed by `ce4af55` label/note edits; was `733bd4b0…`; no evidence existed yet) |

## API funding and spend

- Budget: $10 total ($7 dev / $3 final), $1 provisional per run (D-018).
- Console balance: last confirmed $0. Purchase: **not confirmed**. API key: **not confirmed**. Smoke test: **not run**.
- Measured application spend so far: **$0.00** (no application API calls; every agent run so far was the scripted test double).

## Research state

- Experiment `HP-FINAL`: not started (0 candidates, 0 repairs). Validation has not been consulted for any candidate. Holdout: **SEALED** (never opened). Rehearsal lineages on real data stop at development; TEST lineages use synthetic data only.

## Blockers

1. **API funding and key**: needed only for live agent runs (on the demo laptop). Everything else is unblocked.

## Next

1. Merge PR #3; on the laptop: `git pull`, `uv run pytest -q` (expect 71 passed), then rehearse the checkpoint-1 demo on real data (`docs/DEMO_GUIDE.md`).
2. If funding arrives: `hedgeproof smoke`, then one measured research run (practice model), then one with the research model.
3. Before checkpoint 2: the real `HP-FINAL` research run (live agents if funded), validation scoring, freeze; holdout stays sealed until after checkpoint 2.

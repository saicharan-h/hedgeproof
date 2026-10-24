# HedgeProof build state

Updated: Sat 24 Oct 2026, 1:37 PM IST. Labels: PLANNED, IMPLEMENTED, VERIFIED (command output or inspected file), BLOCKED, DEFERRED.

## Event facts

- Hacking round: officially started (team-confirmed; exact announcement time not supplied).
- Checkpoint 1: Sat 24 Oct, 4:00 PM IST. Checkpoint 2: Sat 24 Oct, 10:00 PM IST (unless organizers update it).
- Final submission deadline: **not yet confirmed**. Demo video length: not confirmed.

## Branch and commits

- Working branch: `claude/wonderful-keller-enn1fn`; integrates into `main` by pull request (D-019).
- PRs #1, #2 and #3 are merged. Around 1:10 PM IST `main` and this branch were **force-pushed with rewritten history**: Claude-authored commits now show Nikshep as author (D-036). The original commits are kept locally in `backup/original-claude-history` (not pushed).
- Nikshep's commits on `main`: `102f55e` (Indian scenario on SYNTHETIC-INDIA data, validators, Vercel showcase, OpenAI-format OpenRouter client, docs) and `234e927` (closes DB handles in his tests).
- On the branch for PR #4: OpenRouter provider for the agent workflow (D-034), Vercel showcase hardening (D-035), docs.

## Environment facts

| Item | Status |
|---|---|
| Cloud session: Python 3.12.3, uv 0.11.32, Docker 29.9.2 daemon, image `hedgeproof-sandbox:1` built | VERIFIED (cloud container) |
| Cloud network: PyPI and Docker Hub reachable; `www.eia.gov` and `openrouter.ai` blocked (proxy 403), so live model calls run only on the demo laptop; sandbox build needs the proxy CA as a BuildKit secret here (`HEDGEPROOF_EXTRA_CA`), not on the laptop | VERIFIED |
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
| OpenRouter provider (Anthropic SDK + base URL, key as Bearer, price check, feature probes) | IMPLEMENTED, VERIFIED offline (mock transport); live smoke test pending on the laptop | `tests/test_claude_client.py` |
| Indian scenario (Nikshep): configs, loader, SYNTHETIC-INDIA market, tests | IMPLEMENTED on synthetic data only (no Indian market data files exist) | `tests/test_india*.py` |
| Vercel showcase (Nikshep), hardened | IMPLEMENTED; deployment status unknown | `docs/VERCEL_DEPLOYMENT.md` |
| Model-dependent trials (E1-E3, single-agent, fixed script) | PLANNED (needs the OpenRouter key on the laptop) | |
| GASB-informed diagnostic (stretch) | DEFERRED | |

## Tests

- `uv run pytest -q`: **136 passed** in the cloud container (24 Oct, about 1:35 PM IST), including Nikshep's Indian-scenario and validator tests, the Docker sandbox tests and 4 new OpenRouter/deployment checks, with the Windows-like file-locking guard active. No API calls.

## Config hashes (SHA-256 of canonical JSON of parsed TOML)

| File | Hash |
|---|---|
| `config/policy.toml` (policy v1) | `f34a06bfb388d9b4061b6e8a2e1ed61c84ee1be487cb9df68c25da58654e6407` (currency fields added in `102f55e`; was `cacdd77a…`; no evidence or approvals existed yet) |
| `config/experiment.toml` | `3262a1d6681c5885303d803044691de350355938fc7751562613aac044a7ccde` |
| `config/agency_fixture.toml` | `3e2c41fb0295575f2508643b5424ab85900a323e05c79faf2af1f43c533eabae` (label and currency fields edited in `ce4af55` and `102f55e`; no evidence existed yet) |

## API funding and spend

- Budget: $10 total ($7 dev / $3 final), $1 provisional per run (D-018).
- Provider: **OpenRouter**. The team reports buying **$10 of OpenRouter credit** (24 Oct, ~1:20 PM IST). The usable balance after any purchase fee is **not yet confirmed** (read it on OpenRouter's credits page). Anthropic Console balance: $0, unused.
- OpenRouter key on the laptop (`OPENROUTER_API_KEY`): **not yet set**. Smoke test (`uv run hedgeproof smoke`): **not run**. OpenRouter prices and feature support (strict tools, effort): from web search only, **to be verified by the smoke test**.
- Measured application spend so far: **$0.00** (no application API calls; every agent run so far was the scripted test double).

## Research state

- Experiment `HP-FINAL`: not started (0 candidates, 0 repairs). Validation has not been consulted for any candidate. Holdout: **SEALED** (never opened). Rehearsal lineages on real data stop at development; TEST lineages use synthetic data only.

## Blockers

1. **OpenRouter key on the laptop** (needed only for live agent runs): create the key, set `OPENROUTER_API_KEY`, run `uv run hedgeproof smoke`.
2. **Attribution after the force-push** (D-036): team decision needed.

## Next

1. Merge PR #4; laptop: `git pull`, `uv sync`, `uv run pytest -q`.
2. Laptop: set the OpenRouter key (never in chat), run `uv run hedgeproof smoke`, share its output (it prints no key).
3. One measured live research run with the practice model (rehearsal lineage), then one with the research model; record cost and runtime.
4. Rehearse the checkpoint-1 demo (`docs/DEMO_GUIDE.md`).

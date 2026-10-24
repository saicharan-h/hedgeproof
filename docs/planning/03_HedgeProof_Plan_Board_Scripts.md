# HedgeProof final round: plan, task board, risks and scripts

Written Fri 23 Oct 2026, about 11:45 PM IST. **Phase: PREPARATION.** Every build item below is PLANNED; nothing is implemented. Times are IST. Checkpoints are fixed. The hacking start (T0) is not yet announced; this plan assumes T0 is about 10:30 AM, after the opening talk, and shifts with the real start.

---

## 1. Wall-clock plan, worked backward from the checkpoints

| When (IST) | Target state | Owners |
|---|---|---|
| Fri night | Access checks done (runbook section 2); contract understood; everyone asleep by 12:30 AM | All |
| Sat 09:15 to 09:50 | Pre-start call: re-run check A on the demo laptop; skim the contract | All |
| 10:00 | Opening talk; note-taker posts the official start, deadline, judging and links | Saicharan notes |
| T0 to T0+0:25 | Public repo, ignore rules first, README skeleton, BUILD_STATE, dependency lock, frozen config and hashes | Saicharan creates the repo; Claude pushes |
| T0+0:25 to T0+2:00 | Data manifest and contract mapping checked; deterministic unhedged and fixed-50% baselines; sandbox image and runner; gate skeleton with the 150% veto; minimal dashboard page | Nikshep, Kruthik, Lohith, with Claude in every slice |
| By about 14:00 | First full development slice: a real agent tool call, an engine result, a gate decision and a paper-ledger entry, all visible as events | Saicharan integrates |
| 13:00 to 14:30 | Lunch in two shifts of two | All |
| 14:00 to 15:15 | Stabilize checkpoint 1: fix, update BUILD_STATE, push, tag `checkpoint-1` | All |
| 15:15 to 15:45 | Rehearse the checkpoint-1 update (section 6), test screen sharing | Saicharan presents |
| **16:00** | **Checkpoint 1:** data and quant workflow, a visible agent action, and an actual 150% veto, with current and planned work kept distinct | All |
| 16:30 to 20:30 | Critique and Risk loops, repairs, diagnostics, evidence packets, holdout lock, the 16 cases, timeout reconciliation, validation backtests | All, per section 2 |
| 19:30 to 20:30 | Dinner in two shifts | All |
| 20:30 to 21:30 | Integration fixes, validation comparison, README update, checkpoint-2 rehearsal | All |
| **22:00** | **Checkpoint 2:** the integrated system on development and validation data; the holdout shown still sealed | All |
| 22:30 to 00:30 | Correctness checklist (section 1.1), then freeze all strategies, open the holdout once, commit the report, then the operational paper decision or an evidenced refusal | Saicharan runs; Nikshep checks the numbers |
| 00:30 to 04:30 | Shift A sleeps (Nikshep, Lohith). Shift B runs model trials, gate ablation and the results summary | Saicharan, Kruthik |
| 04:30 to 08:00 | Shift B sleeps (Saicharan, Kruthik). Shift A does the clean-checkout test on a second laptop, the backup recording, README, Q&A and study guide | Nikshep, Lohith |
| 08:00 to 08:30 | Final rehearsal on the presenting laptop | All |
| **08:30** | Feature freeze, at least 90 minutes before an assumed 10:00 cutoff: secret scan, final push, submission materials, backup demo ready | All |

### 1.1 Correctness checklist before the holdout is opened

- All 9 financial invariants pass.
- The 16-case suite has been run, and its results are committed.
- Data manifest hashes match the committed raw files.
- Policy, experiment and agency hashes are unchanged since T0+2h.
- Every candidate that will be scored is frozen.
- `git status` is clean, and the freeze commit is pushed.

Only then does Saicharan press "Open holdout" once. If a material bug is found afterwards, it is recorded, and any rerun is labeled as a post-unseal rerun, never as untouched out-of-sample evidence.

---

## 2. Ownership and acceptance tests per slice

Claude writes code in every slice. The named owner runs it, reviews it, extends the tests and explains it at judging.

| Slice | Owner | Done when (acceptance) | Integration point |
|---|---|---|---|
| S0 Bootstrap | Saicharan | Repo public; ignore rules in the first commit; `uv sync` and `uv run pytest` pass on at least two laptops; the env-file hygiene test passes | Everyone clones |
| N1 Data and mapping | Nikshep | Manifest with SHA-256 and missing-session counts; continuity report; invariants 2, 7 and 8 pass; split counts are 10, 23, 3 purged and 49 | `period_table(as_of)` |
| N2 Engine and baselines | Nikshep | Unhedged and fixed-50% development and validation metrics with units and n; invariants 1, 3 and 5 pass | `/backtests` |
| K1 Sandbox | Kruthik | Checks A to C hold inside the runner; the vetted 36-month OLS passes verification; network, file-write and infinite-loop samples fail safely | `/candidates/{id}/verify` |
| L1 Trusted core | Lohith | SQLite schema; insert-only events; G05 to G09; F5 (15 contracts gives EXPOSURE_CAP) and F6 pass; one Streamlit page shows policy and a gate result | `/intents`, `/gate/check` |
| S1 Orchestrator skeleton | Saicharan | LangGraph graph runs INIT to ABSTAIN with a labeled test-double model client; budget counters stop at their limits | Typed client |
| S2 First live slice | Saicharan with Kruthik | One run with real model calls: Research reads a profile, Coder submits, the sandbox verifies, a development backtest runs, and a 5-contract intent is gated and filled, with every step in the event log | Dashboard panel 2 |
| K2 Critique and repair | Kruthik | A failed verification leads to a repair; a diagnostic result changes the next action, shown in events | `/diagnostics` |
| L2 Approval and execution | Lohith | Approval token; timeout injection; F7 and V4 show exactly one order; ledger and evidence panels work | `/approvals`, `/orders` |
| N3 Diagnostics and holdout scoring | Nikshep | spot_lag_2, subperiod, double_cost and window_alt; bootstrap; holdout scoring tested on a TEST lineage | `/holdout/evaluate` |
| S3 Full graph and baselines | Saicharan | Freeze, holdout gate, evidence, intent, risk review, approval wait, submit and reconcile; single-agent and fixed-script runners; the 16-case runner writes `results/` | `evals/` |

Branching: short-lived branches named after the slice, merged into `main` after tests pass. Contracts change only through Saicharan. Commit after every working increment and before each checkpoint, with descriptive messages.

---

## 3. Task board

| Item | Status | Owner |
|---|---|---|
| RSVP Google Form | Waiting for the organizer to share it | Saicharan |
| Official hacking start time | Unknown; record at the opening talk | Note-taker |
| Submission deadline and requirements | Unknown | Note-taker |
| Judging time and format | Assumed 25 Oct about 10:00 AM IST; not confirmed | Note-taker |
| Checkpoint links and format | Unknown | Saicharan |
| Demo laptop OS and Docker checks A to C | Passed on the Windows 11 demo laptop (reported by Saicharan, 24 Oct 9:10 AM IST). Other laptops not reported | All |
| API credits, key and smoke test | Console balance $0 (24 Oct). $20 under consideration, not confirmed. Key and smoke test pending | Saicharan |
| Cloud environment `HedgeProof` (runbook 2.8) | Not created yet | Saicharan |
| GitHub usernames for collaborator invites | Pending | All |
| Repository `saicharan-h/hedgeproof` | Not created; create at T0 | Saicharan |
| Presenter | Proposed: Saicharan | Team |
| EIA raw files | Download at T0 on a laptop | Nikshep |
| Phase-1 NotebookLM source, video review | DEFERRED (not needed for the build) | n/a |

---

## 4. Risk register

| # | Risk | Containment | Early warning | Fallback |
|---|---|---|---|---|
| 1 | **Contract and timing errors.** A P&L mixes two delivery contracts, or a decision sees prices from its own fill time | Mapping rule from CME 150102.F and EIA definitions; delivery month recorded on both legs; continuity check at every roll; position p−1 excluded from training; one-session spot lag; future-perturbation invariant | Continuity flags above a handful, or invariant 2 or 4 failing | Reject affected positions and report the counts. Never patch prices |
| 2 | **Data access.** EIA is blocked from Claude's workspace, and futures stop at 5 Apr 2024 | Raw XLS committed at T0 from a laptop with hashes; every claim labeled historical replay | Download fails at T0 | A second teammate downloads it; or add `www.eia.gov` to a cloud environment's allowed domains |
| 3 | **LLM access, cost and nondeterminism** | Budgets in config; prompt caching; Haiku 5.5 for plumbing runs; the 16-case suite needs zero model calls; small disclosed trial counts; recorded replays clearly labeled | API balance was $0 on 24 Oct; smoke test fails; or measured spend runs ahead of the D-016 caps | Lower-cost model; fewer trials; deterministic evidence carries the claims |
| 4 | **Sandbox on the demo laptop** (Docker Desktop or WSL issues, image pulls) | Image pre-pulled tonight; restricted flags checked tonight; one small image | Check A fails on the demo laptop | Vetted templates only, labeled "reduced autonomy". Generated code never runs in the host |
| 5 | **Holdout integrity and a negative result** | Lineage-keyed transactional lock, tested only on TEST databases; opened once after checkpoint 2 and the correctness checklist; abstention is a valid, evidenced outcome | Anyone wants to "just peek" at holdout numbers | No peeking. If the pass rule fails, show the refusal and use the labeled operational fixture for the order flow |

The next risk, four-way integration under time pressure, is contained by the contract-first rule, one integrator and a vertical slice by 14:00.

---

## 5. Proposal-to-implementation checklist

Every item is PLANNED until a command result or inspected artifact proves otherwise.

| # | Commitment in Submission.pdf | Status | Notes |
|---|---|---|---|
| 1 | Five bounded roles; LangGraph state machine; shared LLM; typed tool calls | PLANNED | Contract sections 8 and 9 |
| 2 | At most 6 candidate configurations and 2 code repairs per candidate; every attempt logged | PLANNED | Enforced by the trusted service and config |
| 3 | EIA Gulf Coast diesel spot and NY Harbor futures | PLANNED | Series IDs checked 23 Oct |
| 4 | Enter the second-nearby on the first session; exit the same delivery month at the next first session | PLANNED | Rule checked against CME 150102.F and EIA definitions; data check at T0 |
| 5 | Features use only earlier available observations | PLANNED | Position p−1 excluded; one-session spot lag |
| 6 | h = clip(Cov/Var, 0, 0.75); n = floor(hQ/42,000); net-cost and budget formulas | PLANNED | Changed detail: backtest sizing also applies the cash-stress cap, because the agency could not hold more. Reported per month |
| 7 | Fit on 24 or 36 completed months; reject missing data or zero variance | PLANNED | |
| 8 | Stated fees and slippage; floor sizing preserves the cap | PLANNED | Assumed $10 round trip plus one tick per side |
| 9 | Variance, Budget-at-Risk and cash stress on identical dates, volumes and costs | PLANNED | |
| 10 | Docker: no network, read-only past-data window, resource limits | PLANNED | Flags verified in Claude's workspace. Changed detail: windows are streamed one at a time instead of mounted, which is stronger against look-ahead |
| 11 | FastAPI gate outside agent write access; SHA-256 hashes; transactional holdout lock; unique order IDs | PLANNED | |
| 12 | Splits: 2014 to 2017 development, 2018 to 2019 validation, February 2020 to March 2024 holdout; boundary positions purged | PLANNED | Changed detail: a position counts only if it opens and closes inside its split, giving 10, 23 and 49 positions |
| 13 | Freeze one candidate and the acceptance rules; evaluate once; no retuning | PLANNED | All frozen strategies are scored together in the single opening |
| 14 | Hard gate rules, unknown state halts, human approval | PLANNED | G01 to G12 |
| 15 | GASB-informed effectiveness diagnostic | DEFERRED | Stretch feature after the core passes |
| 16 | 16 predefined cases (8 valid, 8 faulty) and targets | PLANNED | Defined in contract 10.1 |
| 17 | Single agent with equal tools and budget; fixed script; gate ablation | PLANNED | Contract 10.3 and 10.4 |
| 18 | Sample counts, block-bootstrap intervals, false rejections, reproducibility, calls, runtime | PLANNED | |
| 19 | Frozen pass rule; otherwise abstain | PLANNED | Contract 3.10 |
| 20 | Demo sequence: research, estimator run, future-data block, 150% veto, sealed evaluation, approved paper order reconciled after a timeout | PLANNED | The paper order is placed at replay date 1 Apr 2024, after the holdout |
| 21 | MVP limits: historical paper research; declared forecast; spot proxy; futures end 5 Apr 2024 | PLANNED | End date verified 23 Oct |
| 22 | No live broker or paid feed; attribution; AI assistance disclosed | PLANNED | README credits section |

---

## 6. Decision log (made tonight; recorded in the repo's `docs/DECISIONS.md` at T0)

| ID | Decision | Reason |
|---|---|---|
| D-001 | Public repo `saicharan-h/hedgeproof` (pending team confirmation) | That account is already connected to Claude with push access |
| D-002 | Python 3.12 with uv. Candidate set resolved on Python 3.11 to 3.13 on 23 Oct: anthropic 2.2.0, langgraph 1.2.16, langgraph-checkpoint-sqlite 3.1.2, pydantic 2.14.1, fastapi 0.161.1, uvicorn 0.54.0, httpx 0.28.1, streamlit 1.66.1, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1, statsmodels 0.15.0, pyarrow 26.0.0, xlrd 2.0.2, pytest 9.1.1. Locked after the first working run | Checked compatibility, not assumed |
| D-003 | Use the Anthropic SDK directly inside LangGraph nodes, with no model wrapper library | Fewer layers, and an API surface checked against the installed package |
| D-004 | Default model `claude-opus-5-5` (effort medium), Haiku 5.5 for plumbing runs; final choice after the spend cap is known. **Superseded by D-016** | Quality of agent decisions within the budget |
| D-005 | Sandbox receives one window per line | Look-ahead is impossible by construction, not by inspection |
| D-006 | A position belongs to a split only if it opens and closes inside it | Clean, explainable purging |
| D-007 | Training for decision p uses positions up to p−2 | Position p−1 closes at the same instant the new entry fills |
| D-008 | Cash stress: a 25% one-month fall in the hedge contract, against a $250,000 cap, applied in backtest sizing and in the gate | A clearly specified, declared liquidity scenario; not a broker margin schedule |
| D-009 | Costs: $10 per contract round trip plus one tick ($4.20) per side | Declared assumption; the double-cost diagnostic tests it |
| D-010 | The operational paper decision uses replay date 1 Apr 2024, after every holdout position closed; its outcome is not scored | Keeps the holdout and the trade temporally coherent |
| D-011 | All frozen strategies are scored in the single holdout opening | One consumption, no reruns |
| D-012 | Approvals need a per-start token held by the human at the dashboard; the agent process has no approval route | Separation of duties in a prototype. This is not user authentication, and we say so |
| D-013 | Claude's commits are authored as `Claude <noreply@anthropic.com>`; each teammate commits under their own name | Truthful attribution in a history that is judged |
| D-014 | Raw EIA files are committed unmodified, with attribution | EIA content is public domain, and EIA is unreachable from Claude's workspace |
| D-015 | The cash-stress cap sizes with F_ref, Contract 3's close on the session before entry, which is the same delivery month the hedge buys | The fill price is not known when the order is sized, so using it would be a small look-ahead |
| D-016 | For a $20 API budget (24 Oct): Sonnet 5.5 at effort medium for showcase and comparison runs, Haiku 5.5 for practice runs, Opus 5.5 only if measured costs allow. A run stops at $1.00 measured; all runs stop at $15 total, keeping $5 for the live demo. At most 3 candidates per run (6 per experiment) and 2 repairs per candidate. Comparison trials use N = 2 per cell if a run costs $0.80 or less, otherwise N = 1, disclosed | The Console balance was $0, and Saicharan is considering $20. Deterministic work needs no AI calls, so the budget goes to agent runs only |

---

## 7. Draft talks (fill only with measured results)

Anything in square brackets is filled at the checkpoint from verified output, or deleted.

### 7.1 Checkpoint 1 update (about 75 seconds)

> **Problem.** A city bus agency buys diesel every month but fixes its budget months earlier, so a price spike lands on service budgets. Diesel futures can protect the budget, but only if the hedge matches the real exposure, survives an honest test and stays inside the agency's rules.
>
> **Working now.** [Only items verified by 15:15.] Our trusted engine loads EIA Gulf Coast diesel spot and NY Harbor ULSD futures with file hashes, maps every position to one delivery contract, and computes budget error for no hedge and a fixed 50% hedge on development data. Our Research agent called a real data tool, and our Coder agent wrote an estimator that ran in a locked-down Docker sandbox.
>
> **One observed result.** [For example: "On [n] development months, a fixed 50% hedge changed budget-error standard deviation from $[x] to $[y]."] The gate blocked a 150% request for fifteen contracts with reason EXPOSURE_CAP. Nothing was resized.
>
> **Limitation.** This is a historical paper replay. EIA futures data ends on 5 April 2024, and the gallons are a declared scenario.
>
> **Next.** Critique and Risk loops, the sealed holdout lock, timeout reconciliation, and the 16-case evaluation before checkpoint 2.

### 7.2 Checkpoint 2 update (about 85 seconds)

> **Since checkpoint 1.** [Verified items only.]
>
> **Live path.** Research, then Coder, then sandbox verification. [A failed test triggered a repair: measured detail.] Critique requested [diagnostic], and the agents [revised or advanced]. Validation result: [metrics with n = 23].
>
> **Gate.** [x of 8] faults blocked and [y of 8] valid cases handled so far, each with a reason code.
>
> **Holdout.** Still sealed; the dashboard shows the lock. We open it once tonight, after the correctness checks.
>
> **Limitation.** Small samples (23 validation months) and declared assumptions for fills, spot lag and cash stress.
>
> **Next.** Freeze, the single holdout evaluation, a paper order at the 1 April 2024 replay date with timeout reconciliation, baselines, the gate ablation, and the README.

### 7.3 Sixty-second pitch, for rehearsal tomorrow (no results claimed)

> City bus agencies set fuel budgets before they know what diesel will cost. New York's MTA, for example, reported hedging half of its next twelve months of diesel purchases. A hedge can protect a budget, but a leaked future price, the wrong futures contract or an oversized position turns a good-looking backtest into a liability. HedgeProof lets AI agents do the research work: they investigate the data, write an estimator, test it in a sandbox, challenge their own evidence and revise. But the agents never decide what counts. Independent code computes every number, opens the sealed test period exactly once, and enforces the agency's written policy. A paper order reaches our simulator only if it matches a verified evidence record and a human approved that exact order. When the evidence fails, HedgeProof refuses and explains why. That refusal is part of the product.

Later deliverables that need real results are PLANNED for after checkpoint 2: the three-minute demo script, the five-minute technical explanation, the judge Q&A and the team study guide.

---

## 8. Sources checked tonight (accessed 23 Oct 2026)

- CME Rulebook chapter 150, NY Harbor ULSD Futures. 150102.B: 42,000 gallons. 150102.C: $0.0001 per gallon. 150102.F: trading ends on the last business day of the month before delivery. 150101: Fungible Grade 62 ULSD. https://www.cmegroup.com/rulebook/NYMEX/1a/150.pdf
- CME contract specifications page for HO: 42,000 gallons, dollars and cents per gallon, code HO. https://www.cmegroup.com/markets/energy/refined-products/heating-oil.contractSpecs.html
- EIA futures table: series IDs, last date 5 Apr 2024, closing-price note. https://www.eia.gov/dnav/pet/pet_pri_fut_s1_d.htm
- EIA futures definitions: Contract 1 and Contracts 2 to 4, heating-oil expiry. https://www.eia.gov/dnav/pet/TblDefs/pet_pri_fut_tbldef2.asp
- EIA spot table: Gulf Coast ULSD series, latest value 20 Oct 2026. https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm
- EIA Today in Energy, 10 May 2013: the NYMEX switch to ULSD began with the May 2013 contract. https://www.eia.gov/todayinenergy/detail.php?id=11211
- EIA copyright and reuse: public domain, acknowledgment requested. https://www.eia.gov/about/copyrights_reuse.php
- Anthropic, Migrating to API version 2026-10-21: sampling parameters removed; Python SDK 2.0.0 and later send the new version. https://platform.claude.com/docs/en/api/migration-2026-10-21
- LangGraph overview: `StateGraph`, `START` and `END` usage. https://docs.langchain.com/oss/python/langgraph/overview
- Installed-package checks in a scratch environment: anthropic 2.2.0, langgraph 1.2.16, langgraph-checkpoint-sqlite 3.1.2.

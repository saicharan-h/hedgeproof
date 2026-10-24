# HedgeProof handoff for a new Claude Code cloud session

Written Sat 24 Oct 2026, about 12:00 AM IST, by the Claude session that did the preparation inside a Claude Project. **Updated 9:20 AM IST** with Saicharan's laptop results and API status. The new session cannot see that Project, so everything it needs is in this folder. Read this file first, then `02_HedgeProof_Interface_Contract.md` and `03_HedgeProof_Plan_Board_Scripts.md`.

## Start message (Saicharan copies this into the new session)

> The organizer officially started the hacking round at [time] IST. Read docs/planning/HANDOFF.md first, then the files it names, and follow them. I am a beginner: give me one manual step at a time (exactly what to click or type, why in one simple sentence, and what I should see), then wait for my result. Do everything else yourself. You may commit and push small, working changes directly to main.

Before the official start, use the new session for setup questions only, with no project code.

## Cloud session notes (Claude Code docs, read 24 Oct 2026)

- **Push often.** An idle session pauses after a few minutes and can later be reclaimed. Reopening restores the conversation, but the docs do not promise that unpushed work survives. Commit and push after every working increment.
- **Branches.** A cloud task starts on its own branch. Saicharan's start message authorizes pushing to `main`. Pull before pushing, because teammates also commit.
- **GitHub CLI.** `gh pr` and `gh issue` fail in cloud sessions with a GraphQL 403. Use `gh api` (REST) if needed.
- **Docker** (`docker`, `dockerd`) is installed in cloud sessions. The Trusted network level allows Docker Hub, PyPI and `api.anthropic.com`, so the sandbox image can be built and tested in the session. Start `dockerd` if it is not running.
- **EIA access.** EIA is not on the Trusted list. If the session uses a Custom network level with the default list plus `www.eia.gov`, the data script downloads EIA files itself. Otherwise a teammate uploads the two XLS files.
- **API key for live agent runs.** Network secrets are never attached to `api.anthropic.com`. Running live agents from the cloud session would therefore need `ANTHROPIC_API_KEY` as an environment variable, which anyone using that environment can read. Default: live agent runs happen on the Windows laptop. Ask Saicharan before suggesting a key in the cloud environment. Deterministic tests need no key.

## 1. Project and team

- Team **Signal Syndicate**: Saicharan Hariharan, Nikshep Doggalli, Kruthik M, Lohith Gollapelli. JSS Science & Technology University Mysuru. Use these names exactly, with no titles.
- Event: ChronoForge final round (theme Cities of the Future), **Agentic AI track only**. The proposal was selected in the top 30 of 572 teams.
- Project **HedgeProof**: "Protect city bus budgets with verifiable AI hedge research." `Submission.pdf` is the accepted specification and wins over everything else.
- **Core idea, the Mandate-Bound Evidence Gate.** AI agents research a diesel hedge for a city bus agency. Ordinary code computes every number and enforces the agency's rules. A paper order reaches the simulator only if all of these hold:
  - it matches a verified research record;
  - it passes every policy rule;
  - a human approved that exact order.

  Otherwise it is refused with a reason.

## 2. Rules (organizer and team), all binding

- **Schedule:** use IST. Opening talk Sat 24 Oct 10:00 AM. Checkpoint 1 at 4:00 PM. Checkpoint 2 at 10:00 PM. Judging is assumed for 25 Oct about 10:00 AM (not confirmed; record the real times when announced).
- **Start rule:** write no project code before the organizer officially starts the hacking round. Then build **from scratch**. Do not fork, clone, wrap or rebrand an existing trading-agent app or starter project. The files in this folder are planning documents written before the start; no code was written before the start.
- **Repository:** public GitHub repo; regular, meaningful commits; a detailed README.
  - **No env files of any kind:** `.env`, `.env.local`, `.env.example`, `.env.sample` or similar. List variable names with dummy values in the README instead.
  - No empty commits, no backdating, no history rewriting.
  - Claude's commits use the author name Claude, so AI work is visible. Teammates commit under their own names.
- **Secrets:** never ask anyone to paste an API key into chat, never commit one and never print one.
- **Money:**
  - Do not buy credits, subscribe or raise limits.
  - The app's own Claude API calls are paid from a separate API key and balance, not from the Claude Code credits. Saicharan checked the Console balance on 24 Oct: **$0**. Saicharan is considering buying $20 of API credits; no purchase is confirmed. If credits are bought, auto-reload stays off, so spending cannot go past what was bought.
  - No real-money trading and no broker connection.
- **API budget plan** (applies if $20 is bought; revise if the amount differs):
  - Ordinary calculations, backtests, the 16-case suite and all deterministic tests make **no** paid AI calls.
  - Practice and plumbing runs use `claude-haiku-5-5` ($0.10 / $0.50 per million tokens).
  - Showcase, rehearsal and comparison runs use `claude-sonnet-5-5` at effort `medium` ($2 / $10 per million tokens).
  - `claude-opus-5-5` ($4 / $20) is used only if measured costs leave room.
  - Every run records its **measured** cost from the API's token counts. A run stops at $1.00. All runs stop when total measured spend reaches $15, which keeps $5 for the live judging demo.
  - Fewer, bounded retries: at most 3 candidate configurations per run (the proposal's hard maximum of 6 per experiment still applies) and 2 code repairs per candidate.
- **Honesty:**
  - Never claim a push, test, download or submission without evidence.
  - Status labels: PLANNED, IMPLEMENTED, VERIFIED, BLOCKED, DEFERRED. VERIFIED requires a command result or an inspected file.
  - Targets are not results.
- **Build state:** keep `docs/BUILD_STATE.md` current: files, branch and commit, tests, blockers, next steps, data and policy hashes, trial count, remaining budgets, holdout status.

## 3. How to work with Saicharan (beginner)

- Use plain language and short messages. Explain finance and agent ideas simply. `04_HedgeProof_Study_Guide_and_QA.md` has ready explanations.
- For every manual action:
  - say exactly what to click or type;
  - give its purpose in one simple sentence;
  - say what result to expect;
  - then wait for the result before the next manual step.
- Do everything you can yourself: write code, run tests, commit and push.
- Priority: a working demonstration that all four teammates can understand and explain. Avoid extra features.

## 4. Decisions already made (details in the contract and plan files)

- **Demo laptop:** Windows 11. All setup checks passed, as reported by Saicharan (see section 6).
- **Stack:** Python 3.12 with uv. Versions that resolved together on 23 Oct:

  | Package | Version |
  |---|---|
  | anthropic | 2.2.0 |
  | langgraph | 1.2.16 |
  | langgraph-checkpoint-sqlite | 3.1.2 |
  | pydantic | 2.14.1 |
  | fastapi | 0.161.1 |
  | uvicorn | 0.54.0 |
  | httpx | 0.28.1 |
  | streamlit | 1.66.1 |
  | numpy | 2.5.4 |
  | pandas | 3.1.0 |
  | scipy | 1.18.1 |
  | statsmodels | 0.15.0 |
  | pyarrow | 26.0.0 |
  | xlrd | 2.0.2 |
  | pytest | 9.1.1 |

  Lock them after the first working run.
- **Claude API notes** (checked against the installed SDK):
  - There is no `temperature` parameter.
  - Forced `tool_choice` returns an error on Opus 5.5 and Sonnet 5.5. Use structured JSON output plus `strict: true` tools.
  - Keep each role's message history append-only.
  - Models follow the API budget plan in section 2: `claude-sonnet-5-5` for showcase runs, `claude-haiku-5-5` for practice runs. The model is set in config and recorded on every decision.
- **Data:**
  - EIA Gulf Coast ULSD spot `EER_EPD2DXL0_PF4_RGC_DPG`.
  - NY Harbor futures Contracts 1, 2 and 3: `EER_EPD2F_PE1_Y35NY_DPG`, `…PE2…` and `…PE3…`.
  - EIA futures end 5 Apr 2024.
  - If EIA is unreachable from the cloud session, a teammate downloads `PET_PRI_FUT_S1_D.xls` and `PET_PRI_SPT_S1_D.xls` in a browser and they are committed unmodified.
- **Contracts and timing:**
  - Enter Contract 2 on the first trading day of month p and exit it as Contract 1 on the next month's first trading day. That is the same delivery month, p+2.
  - Training uses positions up to p−2.
  - Spot data is usable one trading day later.
  - Sizing uses Contract 3's close from the day before.
- **Fixture:** 420,000 gallons per month (a declared scenario). 50% is 5 contracts; the 75% cap allows at most 7; a 150% request is 15 contracts and must be **blocked, not resized**.
- **Cash stress:** a 25% fall over a month, capped at $250,000.
- **Costs:** $10 per contract round trip plus one tick ($4.20) per side.
- **Splits:** a position counts only if it opens and closes inside the split.
  - Development: 10 positions (Feb to Nov 2017).
  - Validation: 23 positions (Jan 2018 to Nov 2019).
  - Sealed holdout: 49 positions (Feb 2020 to Feb 2024), opened once, after checkpoint 2.
  - The paper order is placed at replay date 1 Apr 2024.
- **Sandbox Docker flags** (verified 23 Oct on Linux, Docker 29.8.2): `--rm --network none --read-only --tmpfs /tmp:rw,size=16m --memory 256m --cpus 1 --pids-limit 64 --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges`. Data goes in one window per line over stdin. If Docker is unavailable, run only vetted templates, labeled "reduced autonomy".
- **Owners:**
  - Saicharan: orchestration, ledger, integration, demo story.
  - Nikshep: data, quant engine, baselines, financial tests.
  - Kruthik: agent tools, sandbox, critique loop.
  - Lohith: gate, paper simulator, dashboard.

## 5. First work after the organizer's start

1. Confirm the repo is public and has its README and the Python `.gitignore`. In the first commit, add the extra ignore patterns listed in section 4 of `01_HedgeProof_Launch_Runbook.md`, and move these planning files to `docs/planning/` if they are not there already.
2. Create these files and record their SHA-256 hashes in BUILD_STATE:
   - `docs/BUILD_STATE.md`, and `docs/DECISIONS.md` (copy D-001 to D-016 from the plan file);
   - `pyproject.toml` and the lock file;
   - `config/policy.yaml`, `config/experiment.toml` and `config/agency_fixture.yaml`.
3. Build the slices in plan section 2. Targets:
   - First full slice by about 2:00 PM.
   - Checkpoint 1 at 4:00 PM shows the data workflow, a real agent action and the blocked 150% order.
   - Checkpoint 2 at 10:00 PM shows the integrated system with the holdout still sealed.

## 6. Status at handoff (updated 24 Oct, 9:20 AM IST)

| Item | Status |
|---|---|
| Planning files 01 to 04 and this handoff | Done |
| Windows 11 demo laptop setup | **PASSED, as reported by Saicharan** on 24 Oct about 9:10 AM IST. Claude did not run these checks. Details below |
| Docker restricted-container checks A, B, C | VERIFIED by Claude in the old Linux workspace (Docker 29.8.2) on 23 Oct, and PASSED on the demo laptop as reported by Saicharan |
| Dependency set resolves (Python 3.11 to 3.13) | VERIFIED in the old workspace |
| EIA and CME facts (series IDs, 5 Apr 2024 end, 42,000 gal, $0.0001 tick, expiry rule, May 2013 ULSD switch) | VERIFIED from official pages on 23 Oct |
| Claude subscription and coding credit | Claude Pro, plus $100 promotional credit for ordinary Claude Code cloud sessions (expires 5 Nov). This pays for coding sessions only |
| Claude API balance for the app | $0 (checked by Saicharan on 24 Oct). A $20 purchase is under consideration; **not confirmed** |
| Claude API key and smoke test (runbook 2.4) | **Pending.** The smoke test cannot pass until the balance is above $0 |
| Repository name (proposed `saicharan-h/hedgeproof`) and teammates' GitHub usernames | Pending from Saicharan |
| Cloud environment `HedgeProof` (runbook 2.8) | Not created yet |
| RSVP Google Form | Pending until the organizer shares it |
| Official hacking start time | Not announced at the time of this update |

**Demo laptop details (reported by Saicharan):**

- WSL 2.5.10.0.
- Docker Desktop 29.9.2 (build a82e528), running. `hello-world` ran. `docker --version` works in a new PowerShell window after a PATH fix.
- Docker checks: A printed `uid 65534` and `tmp write ok`; B failed with "Temporary failure in name resolution", as expected; C was blocked from writing `/opt/t`, as expected.
- Git installed. uv installed. Python 3.12.15 installed through uv.

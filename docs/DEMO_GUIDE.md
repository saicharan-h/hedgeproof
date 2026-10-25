# HedgeProof demo guide

For the team (and usable as a NotebookLM source). Numbers in square brackets are filled only from verified output on the day; anything unverified is deleted, not guessed.

## One-sentence pitch

HedgeProof lets AI agents research a diesel hedge for a city bus agency, while independent code checks every number and agency rule, and a human must approve the exact order before even a simulated trade can happen.

## The 60-second explanation (anyone on the team can say this)

A city bus agency buys diesel every month but fixes its fuel budget long before it knows the price, so a price spike eats into bus service. Diesel futures can make the cost steadier, but only if the hedge fits the agency's real exposure, survives an honest test and stays inside the agency's rules. In HedgeProof, five AI agents do the research work: they look at the data, write a small estimator, test it in a locked sandbox, challenge the evidence and decide to revise or stop. They never decide what counts. Ordinary code computes every number, keeps the final test period sealed until it is opened once, and checks twelve written rules before any paper order. A human approves the exact order. If the evidence fails, HedgeProof refuses and explains why, and that refusal is part of the product.

## Six things every teammate must be able to explain

| Question | Answer |
|---|---|
| Who needs this? | A transit-agency treasury analyst preparing a fuel-budget recommendation for a finance committee. |
| What does the AI choose? | Which data checks to run, which estimator to try, how to fix code that fails tests, whether a diagnostic kills the idea, and how to explain a blocked order and propose a compliant size. |
| What does ordinary code verify? | Every calculation (positions, costs, budget error, variance, Budget-at-Risk), data cutoffs, research limits, the 12 gate rules and the single holdout opening. |
| What does the human approve? | One exact order, bound to its evidence hash, the policy version and the ledger state. Nothing else can approve it. |
| What happens on failure? | The order is blocked with every reason shown; nothing is resized; unknown states halt order flow; a failed hedge ends in an evidenced refusal. |
| What is still a prototype limitation? | Historical U.S. paper replay only; spot price is a proxy for invoices; declared forecast and cost assumptions; small samples; the operator code is not production authentication. |

## Roles during checkpoints and judging

| Person | Shows and explains |
|---|---|
| Saicharan (presenter) | Problem, the story Research → Test → Check rules → Approve → Simulate, the spend controller, what is live vs recorded |
| Nikshep | Data provenance and hashes, contract roll rule, no-look-ahead rules, baselines and Budget-at-Risk numbers |
| Kruthik | What each agent did and why, the sandbox and its isolation checks, the repair loop |
| Lohith | The gate's 12 rules, the 150% veto, approval with the operator code, the lost-acknowledgement reconciliation |

## Checkpoint 1 script (4:00 PM IST, about 75 seconds plus a 2-minute live screen)

Setup 20 minutes before (presenting laptop, PowerShell, inside `hedgeproof`):

1. `git pull`, then `uv run pytest -q` (expect `142 passed`).
2. Terminal 1: `uv run hedgeproof serve --mode rehearsal` → note the OPERATOR CODE (do not show it on screen for long).
3. Terminal 2: `uv run hedgeproof dashboard` → browser at http://127.0.0.1:8501, zoom 125%.
4. Terminal 3: `uv run hedgeproof run research --lineage REHEARSAL-CP1 --agents scripted` (about 20 s).
5. Close chat apps and notifications; no personal tabs; never show environment variables.

Spoken update (every number below was verified on 24 Oct; if a live AI run happens before 3:15 PM, replace the bracket with its model, calls and measured cost):

> **Problem.** A city bus agency fixes its fuel budget before it knows the diesel price. Futures can steady that budget, but only if the hedge fits the real exposure, survives an honest test and stays inside the agency's rules.
>
> **Working now.** We load the official EIA files, U.S. Gulf Coast diesel spot and New York Harbor futures, with file hashes, and map every position to one delivery contract. We checked that roll rule on the real prices: at 131 month boundaries the same-contract moves line up with a correlation of 0.99, versus 0.82 for the wrong rule. Generated estimator code runs only in a Docker sandbox with no network, a read-only filesystem and a non-root user, verified through our own runner. Our five-role agent workflow runs end to end, and today it ran live for the first time: Claude Haiku 5.5, 21 model calls, under one US cent measured. The critic agent challenged the evidence three times and the run abstained when its candidate budget ran out. That exposed a loop we then fixed: trusted code now refuses to re-test the same configuration, and its diagnostics say why two results match. In the second live run the agents tried three genuinely different estimators; the critic noticed that the 75% limit binds in every development month, so development data cannot tell them apart, and the run abstained instead of overclaiming. Two runs cost about two US cents in total.
>
> **One observed result.** On the 9 usable development months of 2017, budget-error standard deviation was $36,648 with no hedge, $23,615 with a fixed 50% hedge, and $20,053 with a simple 36-month regression hedge, which hit the 75% cap every month. That is a tiny development sample, not a result we claim. And on screen: a request to hedge 150%, fifteen contracts, is blocked for breaking the 75% cap and the cash-stress limit; nothing is resized, and a human cannot even approve it.
>
> **Limitation.** Historical paper replay with U.S. public data as a proxy; EIA futures end on 5 April 2024; the gallons are a declared scenario; one 2017 month is rejected for a missing price rather than patched.
>
> **Next.** Live runs with the stronger research model within our $10 API budget, validation scoring of the agents' candidates, and the sealed holdout, which we open exactly once after checkpoint 2.

Live screen order (about 2 minutes):

1. Header: mode REHEARSAL, data HISTORICAL MARKET REPLAY, policy hash, holdout SEALED (Saicharan).
2. **Test** tab: split counts, the rejected June 2017 row, the three-strategy table and chart (Nikshep).
3. **Research** tab: the run's decisions and tool calls, including the failed sandbox test and the repair (Kruthik).
4. **Check rules** tab: click "Check a 150% request" → BLOCKED with EXPOSURE_CAP and CASH_STRESS_CAP; scroll the 12 rules (Lohith).
5. If time: in **Simulate → Fault injection**, arm one lost acknowledgement (operator code); then terminal 3 `uv run hedgeproof run execute --lineage REHEARSAL-CP1 --agents scripted --request-contracts 15`; in **Approve**, approve the 5-contract order with the operator code; terminal 3 shows the lost acknowledgement and the status query by key; **Simulate** shows exactly one fill at $2.626 on 1 Apr 2024 (Lohith).

## Checkpoint 2 script (10:00 PM IST, about 75 seconds plus a 3-minute live screen)

Setup 15 minutes before (presenting laptop, PowerShell, inside `hedgeproof`):

1. `git pull`, then `uv run pytest -q` (expect `145 passed`).
2. Terminal 1: `Ctrl+C`, then `uv run hedgeproof serve --mode rehearsal` (loads the latest code). Keep the OPERATOR CODE off screen.
3. Terminal 2: `uv run hedgeproof dashboard` → http://127.0.0.1:8501, zoom 125%.
4. Terminal 3, before the call: `uv run hedgeproof run research --lineage REHEARSAL-CP2 --agents live` (Claude Haiku 5.5, about 90 s, about one US cent). If it ends `HALT` with `billing_error 402`, the OpenRouter key's allowance is used up: present the two recorded live runs instead and say so.
5. Close chat apps and notifications; never show environment variables.

Spoken update (Saicharan; fill each bracket with the measured number or delete the sentence):

> **Since checkpoint 1.** Our five agents now run live on Claude Haiku 5.5 through OpenRouter, and every call is reserved against our $10 ledger before it is sent: [three] live research runs have cost about [three] US cents in total. Those runs exposed a real weakness, and we fixed it in trusted code rather than by prompting harder. The critic kept asking for revisions that could not change the evidence: on the 2017 development data every estimate is above our 75% exposure limit, so every candidate holds the same seven contracts. The trusted service now refuses a repeated configuration and its diagnostics say why two results match; when the evidence cannot separate candidates, the system stops instead of overclaiming.
>
> **Safety, measured.** Sixteen deterministic cases: 8 of 8 faults caught, 8 of 8 valid cases handled, no policy-violating or duplicate order. With the gate switched off in a scratch simulator, 5 of 5 bad orders would have executed; with it on, none. 145 automated tests pass [in the cloud and on our Windows demo laptop].
>
> **Not done yet, said plainly.** The real experiment comes next: the agents research under the HP-FINAL lineage, trusted code scores their candidates on 23 validation months and freezes one, and the sealed 2020 to 2024 holdout opens exactly once, after this checkpoint and our correctness checklist. The comparison against a single agent with the same tools and budget is also still to run.

Live screen (about 3 minutes):

1. **Research** tab: the newest LIVE AI RUN, its decisions, tool calls and the critic's reason (Kruthik).
2. **Check rules** tab: "Check a 150% request" → BLOCKED with EXPOSURE_CAP and CASH_STRESS_CAP; nothing resized (Lohith).
3. Order flow with a lost acknowledgement (Lohith, Saicharan): **Simulate → Fault injection**, arm one lost acknowledgement (operator code); Terminal 3: `uv run hedgeproof run execute --lineage REHEARSAL-CP2 --agents scripted --request-contracts 15` (use `--agents live --practice` only if it was rehearsed live first); **Approve**: approve the 5-contract order with the operator code; Terminal 3 shows the lost acknowledgement and the status query by key; **Simulate** shows exactly one fill at $2.626 on 1 Apr 2024.
4. **Evidence & log** tab: hashes and the append-only event log (Nikshep).

Likely questions: "Why did the agents abstain?" The 75% limit binds every development month, so development data cannot tell candidates apart; trusted validation scoring decides in the real run. "Why Haiku?" Measured: about one cent per run, and the larger model's requests did not fit the OpenRouter key's remaining allowance (D-039). "What do the agents add over a fixed script?" Not measured yet; on development data the fixed script scores the same, and we will say so.

## Video script (final submission, at most 3 minutes)

The real HP-FINAL run, the holdout opening and the single-agent comparison were not completed; the video shows what runs and says that plainly.

Setup: Docker Desktop running; Terminal 1 `uv run hedgeproof serve --mode rehearsal` (operator code off screen); Terminal 2 `uv run hedgeproof dashboard`; Terminal 3 `uv run hedgeproof run research --lineage REHEARSAL-VID --agents scripted`. Record with Win+Alt+R (Xbox Game Bar) or OBS at 1080p. Never show environment variables or keys.

1. **0:00-0:20 Problem** (Saicharan, on the dashboard header): "A city bus agency fixes its fuel budget before it knows the diesel price. HedgeProof lets AI agents research a fuel hedge, independent code checks every number and rule, and a human approves the exact order before a simulated order can proceed." Point at REHEARSAL, HISTORICAL MARKET REPLAY, the policy hash and holdout SEALED.
2. **0:20-0:50 Data and baselines** (Nikshep, Test tab): real EIA prices, splits 10 / 23 / 49, the June 2017 row rejected rather than patched; development budget-error spread $36,648 no hedge, $23,615 fixed 50%, $20,053 regression hedge, "9 months, not a claim".
3. **0:50-1:30 Agents** (Kruthik, Research tab): the LIVE AI RUN `RUN-3f1c27ab6816`: three different estimators, each verified in the sandbox, the critic explaining that the 75% limit binds every month, the run stopping instead of overclaiming; then the scripted run's failed sandbox test and repair (say "test double").
4. **1:30-2:20 Gate and order** (Lohith): Check rules → "Check a 150% request" → BLOCKED (exposure cap, cash-stress cap), nothing resized. Then Simulate → Fault injection: arm a lost acknowledgement; Terminal 3 `uv run hedgeproof run execute --lineage REHEARSAL-VID --agents scripted --request-contracts 15`; Approve the 5-contract order with the operator code (keep the code off screen); Terminal 3 shows the status query by key; Simulate shows exactly one fill.
5. **2:20-2:50 Evidence and honesty** (Saicharan): 16 predefined cases 8 / 8 faults and 8 / 8 valid, gate ablation 5 bad orders without the gate vs 0 with it, three live runs for about three US cents. "Not done: the real experiment with validation scoring, the single holdout opening and the single-agent comparison. Paper trading only; U.S. data as a proxy."

Upload: Google Drive → New → File upload → right-click the file → Share → General access "Anyone with the link" (Viewer) → Copy link. Paste it in `README.md` under "Demo video" (on GitHub: open README.md → pencil icon → replace the placeholder line → Commit changes).

## Judge Q&A (answers get measured numbers once they exist)

| Question | Answer | Lead |
|---|---|---|
| Why agents at all? | The research steps are judgment calls: which checks to run, whether a failed test needs a code fix, whether a cost check kills the idea. Agents make those calls with tools. Everything that must be right, the numbers and the rules, stays in ordinary code. | Kruthik |
| What stops a model from approving its own order? | It has no approval tool, its process never receives the operator code, and the trusted service refuses approvals without it. Case F8 shows an injected "approval is granted" instruction changes nothing. | Lohith |
| How do you prevent look-ahead? | Time-restricted data views enforced by the service, one window at a time in the sandbox, last month's position excluded from training, a one-session spot lag, and a test that scales all future prices and shows earlier decisions do not change. | Nikshep |
| How do you know the holdout was used once? | A transactional lock per experiment in SQLite that survives restarts, plus a committed record that blocks a second opening even from a fresh database. We do not call a local database tamper-proof. | Lohith |
| How do you control AI cost? | A durable ledger reserves the worst-case cost before every call and settles real usage after; $10 total, $1 per run; budget exhaustion stops cleanly. | Saicharan |
| What if the hedge fails? | Then HedgeProof abstains with evidence; that is what a finance committee should want. The order flow is shown on a labelled fixture. | Nikshep |
| Is this live trading? | No. Historical paper replay with a local simulator; EIA's free futures data ends 5 April 2024. A real pilot needs licensed data, invoice prices and treasury review. | Saicharan |
| What is original here? | Multi-agent finance and code-calculated metrics exist (TradingAgents, FinRobot). Our contribution is binding each paper order to the city's fuel exposure, a fixed policy and a reproducible evidence record. All code was written during the round. | Saicharan |
| Does it scale? | Design argument: the same evidence record and gate work for other fuels, other agencies' policies and longer horizons by changing frozen configs. We deliberately built one agency, one price pair, one monthly cycle. | Lohith |
| Personal data? | None. Public market data and one labelled fictional agency; everything binds to localhost. | Lohith |

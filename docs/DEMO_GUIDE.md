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

1. `git pull`, then `uv run pytest -q` (expect `71 passed`).
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

## Checkpoint 2 and final scripts

Written after real results exist (planned: integrated research, critique, evidence, approval, reconciliation, safety tests; holdout still sealed at checkpoint 2).

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

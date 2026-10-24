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

Setup before the call (on the presenting laptop): terminal 1 `uv run hedgeproof serve --mode rehearsal` (or `--mode test` if real data is not ingested), terminal 2 `uv run hedgeproof dashboard`, browser at 125%, notifications off, no personal tabs, never show environment variables.

> **Problem.** A city bus agency fixes its fuel budget before it knows the diesel price. Futures can steady that budget, but only if the hedge fits the real exposure, survives an honest test and stays inside the agency's rules.
>
> **Working now.** [Only items verified by 3:15 PM.] Our trusted service computes every number and enforces twelve written rules. Generated estimator code runs only in a Docker sandbox with no network, a read-only filesystem and a non-root user; we verified that through the runner itself. Our five-role agent workflow runs end to end; [live AI run: say only if one ran, with model, calls and measured cost; otherwise: "today's agent runs on screen are a labelled scripted test double, because API funding is pending"].
>
> **One observed result.** [Real-data example, only if ingested: "On 10 development months, a fixed 50% hedge changed budget-error standard deviation from $[x] to $[y]."] On screen: a request to hedge 150% (15 contracts) is blocked with EXPOSURE_CAP; nothing is resized, and a human cannot even approve it.
>
> **Limitation.** Historical paper replay; EIA futures data ends 5 April 2024; the gallons are a declared scenario.
>
> **Next.** Real-data validation, live agent runs within our $10 API budget, critique diagnostics, and the sealed holdout, opened once after checkpoint 2.

Live screen order: dashboard header (mode, policy hash, holdout SEALED) → Test tab (data and baselines) → Check rules: click "Check a 150% request" (BLOCKED, every rule listed) → Research tab (agent decisions with tool calls and results) → Simulate tab (ledger).

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

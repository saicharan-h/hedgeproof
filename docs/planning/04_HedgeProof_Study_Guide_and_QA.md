# HedgeProof team study guide and judge Q&A (pre-start draft)

Written Fri 23 Oct 2026 for the Saturday morning read. This covers the ideas and the planned design only. There is no code yet, and there are no results. The code walkthrough and every measured number get added after we build. Worked numbers below are **illustrative arithmetic, not market data**.

---

## Part A. The ideas in plain language

### A1. The problem

A city bus agency buys diesel every month, but its finance office fixes the fuel budget long before it knows the price. If diesel jumps, the overspend comes out of reserves or service. Transit agencies already hedge this. MTA's 27 Oct 2025 Fuel Hedge Program Report describes hedging 50% of its next 12 months of projected diesel purchases.

### A2. What a futures hedge does

A NY Harbor ULSD futures contract (CME code HO) is an agreement on a price for 42,000 gallons of diesel delivered in a named month.

- The agency **buys** futures (a long position).
- If diesel prices rise, the futures gain, and that gain offsets the bigger fuel bill.
- If prices fall, the futures lose, but the fuel itself got cheaper.

The result is a **steadier** fuel cost, not a lower one on average. Hedging reduces the spread of budget surprises. It is not a way to make money, which is why we never judge it by trading profit.

### A3. Basis risk, and why we estimate a hedge ratio

The agency pays something close to a Gulf Coast diesel spot price, while the futures price is set for New York Harbor. The two move together but not perfectly. That mismatch is **basis risk**. So we estimate how many gallons of futures best offset one gallon of the agency's own price exposure:

- h = Cov(ΔS, ΔF) / Var(ΔF). This is the slope from regressing spot changes on futures changes over past holding months, and it is the hedge ratio that minimizes the variance of ΔS − h × ΔF.
- We clip h to the range 0 to 0.75, because the agency's policy never allows more than 75% of forecast gallons.
- Contracts: n = floor(h × Q / 42,000). With Q = 420,000 gallons, 50% is 5 contracts, and the 75% cap allows at most 7 (70%, because contracts are whole numbers).

### A4. Worked example (illustrative numbers only)

Inputs:

- Q = 420,000 gallons; budget price $2.50, so the budget is $1,050,000.
- n = 7 contracts, bought at $2.55.
- Costs: 7 × $18.40 = $128.80 (assumed fees and slippage).

| Case | Fuel price at purchase | Futures exit | Unhedged budget error | Hedge gain or loss | Hedged budget error |
|---|---|---|---|---|---|
| Prices rise | $2.80 | $2.83 | +$126,000 | +$82,320 gain | +$43,808.80 |
| Prices fall | $2.20 | $2.27 | −$126,000 | −$82,320 loss | −$43,551.20 |

Each line follows the same identity:

> hedged error = Q × ΔS − 42,000 × n × ΔF + costs

The hedge shrinks surprises in both directions. That is the whole point.

### A5. Which contract, and when (the "roll")

HO trading for a delivery month ends on the last business day of the month before it (CME rule 150102.F). EIA's Contract 1 is the nearest delivery month and Contract 2 the next one.

- **Enter:** on the first trading day of month p, we buy Contract 2. That is delivery month p+2.
- **Exit:** on the first trading day of month p+1, the old front month has expired, so delivery month p+2 is now Contract 1. We sell it there.

The entry and exit are the same contract, so the profit is real and not an artifact of splicing two different contracts together.

### A6. No peeking at the future

- **The fill:** a decision is made before the entry day's closing price, which is the fill, and uses only earlier data.
- **Spot lag:** spot prices are treated as usable one session after their date.
- **Last month's position:** it closes at the same instant the new position opens, so it is left out of the training data for that decision.
- **The sandbox:** it receives one data window at a time, so later data simply is not there when an earlier estimate is made.

### A7. Development, validation and the sealed holdout

- **Agents iterate on development data:** 10 positions in 2017, plus diagnostics over 2014 to 2017.
- **Candidates are compared on validation:** 23 positions in 2018 and 2019.
- **The holdout is opened exactly once:** 49 positions, February 2020 to February 2024.

The final test period is locked in the trusted database, keyed to the experiment, not to a candidate name. Renaming a candidate or restarting the service cannot reopen it. If the hedge fails the rule we wrote down in advance, we abstain and show why.

### A8. The numbers we report

- **Budget-error variance:** how widely monthly overspend and underspend vary. Lower is better.
- **Budget-at-Risk (BaR95):** the empirical 95th percentile of budget error. "In about 19 of 20 test months, the overspend was at most this much." With 23 or 49 months it is a rough estimate, never a guarantee.
- **Cash stress:** a long hedge can demand cash (margin) when prices fall, before the cheaper fuel arrives. We model a 25% fall in the hedge contract during the month and cap the cash need at $250,000. That is a declared assumption, not a broker's margin schedule.
- **Pass rule, frozen in advance:** lower variance than no hedge, no worse BaR than no hedge, and zero rule breaches. Otherwise we abstain. We also show whether the agents beat a plain 50% hedge, even if they do not.

### A9. The Mandate-Bound Evidence Gate

Before any paper order, trusted code checks each of these and reports every failed rule with a reason:

- Evidence: it exists, its hashes match, and it uses the current policy version.
- Inputs: the data is fresh.
- Instrument: the right contract.
- Position: no net short, at most 75% of forecast gallons, held one month only, inside the cash-stress cap.
- Duplicates: no duplicate order.
- Approval: a human approved this exact order.
- State: no order in an unknown state.

A blocked order is never quietly resized. A smaller order is a new request that needs its own check and its own approval.

### A10. What the agents actually decide

| Role | What it does |
|---|---|
| Research | Picks a hypothesis and estimator setup from source and data profiles |
| Coder | Writes the estimator, runs it in the sandbox, and repairs it when tests fail (2 repairs at most) |
| Critique | Asks for diagnostics (2-day spot lag, split halves, doubled costs, other window length) and decides to revise, reject, advance or stop |
| Risk | Explains a blocked order and proposes a compliant size |
| Execution | Submits the approved order, and after a timeout checks status before any retry |

None of them can compute the final numbers, change the policy, open the holdout twice or approve an order.

### A11. The eight faults we test, in plain words

1. Asking for data from the future.
2. An estimator with its sign flipped.
3. Stale data for the replay date.
4. Trying to reuse the holdout.
5. A 150% hedge.
6. A position that would go net short.
7. A retry that would create a second order after a timeout.
8. A source document that tells the agents to ignore the rules.

Each one must be blocked with the right reason. Eight valid cases check that we do not block sound work.

---

## Part B. Judge Q&A drafts (answers get measured numbers after the build)

| Question | Draft answer | Lead |
|---|---|---|
| Why agents at all? | The research steps are judgment calls: which data checks to run, whether a failed test needs a code fix, whether a cost check kills the idea. Agents make those calls with tools. Everything that must be right, the numbers and the rules, stays in ordinary code | Kruthik |
| Why five roles? | Each role has a different tool set and a different thing it may not do. The Coder cannot judge its own work, and the Risk role cannot approve. Separation makes the trail auditable | Saicharan |
| Why hedging, and why cities? | Fuel is a large, volatile line in a transit budget, and agencies already hedge it. The cost of a bad hedge lands on public service | Saicharan |
| What do you add over a fixed script? | We compare against a fixed script and a single agent with the same tools, model and budget, and report flaws caught, valid cases accepted, calls and cost. If the script does as well, we will say so | Saicharan |
| How do you prevent data leakage? | Time-restricted data views enforced by the service, one-window-at-a-time sandbox input, last month's position excluded from training, a one-session spot lag, and a test that perturbs future data and shows earlier decisions do not change | Nikshep |
| How do contract rolls work? | Enter Contract 2, exit the same delivery month as Contract 1 a month later; checked against CME 150102.F and EIA definitions; every position stores its delivery month | Nikshep |
| How certain are your numbers? | Small samples (23 and 49 months), reported with counts and preregistered block-bootstrap intervals. We do not claim statistical certainty | Nikshep |
| What enforces the policy if the model misbehaves? | A separate service with its own database applies twelve fixed rules. The agent process has no route to change policy or approve, and an injected-instruction test shows a document cannot either | Lohith |
| How do we know the holdout was used once? | A transactional lock in SQLite keyed to the experiment, which survives restarts, plus the committed report with hashes. We do not call a local database tamper-proof | Lohith |
| Is this live trading? | No. Historical paper replay with a local simulator. EIA's free futures data ends 5 April 2024. A real pilot would need licensed data, invoice prices and treasury review | Saicharan |
| What is original here? | Multi-agent finance and code-calculated metrics are known ideas (TradingAgents, FinRobot). Our contribution is binding each paper order to the city's actual fuel exposure, a fixed policy and a reproducible evidence record. The code is written from scratch during the round | Saicharan |
| Does it scale? | The same gate and evidence record apply to other fuels, other agencies' policies and longer horizons. The prototype deliberately stays at one agency, one price pair and one monthly cycle | Lohith |
| What if the hedge fails? | Then the product refuses with evidence, which is the behavior a finance committee should want. The order flow is then shown on a labeled fixture | Nikshep |
| Who did what? | Filled in from the commit history at the end. AI assistance is disclosed in the README, and Claude's commits carry their own author name | All |

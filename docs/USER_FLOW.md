# User flows and use cases

This document explains how a person actually uses HedgeProof, end to end, with
concrete examples. It complements `README.md` (what it is) and
`docs/DEMO_GUIDE.md` (how to demo it).

## Actors

| Actor | What they do | What they never do |
|---|---|---|
| **Analyst** (human) | Reviews evidence, approves an exact order, reads results | Never runs generated code; never sees the operator code in the agent process |
| **Agent process** (untrusted) | Proposes estimators, runs them in the sandbox, critiques, proposes sizes, submits approved paper orders | Never computes final metrics; never changes policy; never approves; never opens the holdout |
| **Trusted service** (FastAPI) | Computes every number, enforces G01-G12, holds the DB and operator code | Never runs model code; never calls the LLM |
| **Sandbox** (Docker) | Runs generated estimator code only, one window per line, no network | Never touches the host, the DB or the operator code |

## Flow 1: Research (offline, scripted, no AI calls)

Goal: produce a candidate estimator and an evidence packet on the development split.

1. Start the trusted service on the test fixture:
   `uv run hedgeproof serve --mode test` (prints the OPERATOR CODE).
2. Start the dashboard: `uv run hedgeproof dashboard` (http://127.0.0.1:8501).
3. Run the research workflow:
   `uv run hedgeproof run research --lineage TEST-DEMO --agents scripted`
4. What happens (scripted test double, no API calls):
   - Research role profiles the data and proposes an OLS estimator (window 36).
   - Coder writes the estimator, submits it, verifies it (known-answer + property + sandbox), repairs a seeded sign error, verifies again, runs the development backtest.
   - Critique runs diagnostics (window sensitivity, spot lag, cost stress) and advances.
   - The candidate is frozen; a `FreezeRecord` is stored.
5. Dashboard tab 1 shows the agent decisions and the candidate. Tab 2 shows the development backtest (10 positions).

## Flow 2: Check the rules (Mandate-Bound Evidence Gate)

Goal: prove that only a compliant, approved, evidence-backed order can reach the simulator.

1. The agent workflow (execute) builds an evidence packet on the replay date (2024-04-01) and proposes a size.
2. Risk role explains any gate failure and proposes a compliant size (5 contracts here, the 75% cap).
3. Dashboard tab 3 ("Check rules"):
   - "Check recommended order (5 contracts)" → ELIGIBLE after approval, otherwise APPROVAL_MISSING_OR_STALE.
   - "Check a 150% request (15 contracts)" → BLOCKED EXPOSURE_CAP. The order is NOT resized; a smaller order is a new request with its own approval.
   - Any contract count can be checked; the gate returns all 12 rules with pass/fail and reasons.
4. Every check is recorded in the append-only event log (tab 6).

## Flow 3: Approve and simulate (human in the loop)

Goal: a human approves the exact order, then a paper order is submitted and reconciled.

1. Dashboard tab 4 ("Human approval"): select the order, enter approver name and the operator code (from the service window), tick the review box, click "Approve this exact order". Approval is bound to the exact intent hash, policy hash and ledger version.
2. Back in tab 3, "Check recommended order" now shows ELIGIBLE.
3. The execute workflow submits the order with an idempotency key. The simulator fills it at the entry close (2024-04-01), delivery month 2024-06.
4. Fault injection (labelled test): arm one lost acknowledgement (operator code needed). The next order fills but its ack is withheld; retrying with the same key returns the original order (no duplicate, no second fill). This is verified by `V4` and `F7`.

## Flow 4: Sealed holdout (opened once)

Goal: honest final evaluation, never before checkpoint 2.

1. After all invariants pass and the 16 cases are committed, the operator opens the holdout once per lineage using the operator code.
2. The holdout report (49 positions, Feb 2020 - Feb 2024) is stored with its hash; reopening is refused (`HOLDOUT_ALREADY_CONSUMED`).
3. Verdict is PASS or ABSTAIN with conditions. No savings are claimed.

## Use cases

### UC-1: "Is this hedge safe to act on?"
Analyst inputs a candidate size. The gate returns BLOCKED/ELIGIBLE with the specific rule and reason. Example: 15 contracts (150% of forecast) → `EXPOSURE_CAP`, not resized.

### UC-2: "Did the agent leak future data?"
F1 case: a request for data after the research clock raises `FUTURE_DATA_REQUEST` / `SEALED_PERIOD`, no artifact created, event logged. The agent can only see sessions strictly before the research clock.

### UC-3: "What if the evidence changed after approval?"
F3 case: a stale evidence packet (data end date moved) makes the gate return `STALE_INPUT` and approval returns `APPROVAL_NOT_ALLOWED`. Changed evidence produces a new intent hash, so old approvals cannot be reused.

### UC-4: "Prompt injection in a source"
F8 case: an injected source tries to override policy and push a 150% order. Policy hash unchanged, no approval created, 150% blocked, no order. Retrieved text is labelled data, never instructions.

### UC-5: "Lost acknowledgement, no duplicate order"
F7/V4: an order fills but its ack is lost. Querying by key shows FILLED; retrying with the same key returns the original order. A naive retry with a new key is blocked by `DUPLICATE_INTENT`.

### UC-6: "Indian scenario"
Run `uv run hedgeproof serve --mode test --scenario india`. Same flow, MCX crude proxy, INR, litres. See `docs/INDIA_SCENARIO.md`.

### UC-7: "Vercel deployment (agentic AI demo)"
Deploy to Vercel. The landing page shows health/policy metrics and an OpenRouter-backed chat panel. `POST /api/chat` keeps the API key server-side. The trusted service runs on SYNTHETIC data (ephemeral). See `docs/VERCEL_DEPLOYMENT.md`.

## Vercel user flow (deployed)

1. Push to GitHub; import the repo in Vercel.
2. Set env vars: `OPENROUTER_API_KEY`, `HEDGEPROOF_SCENARIO` (us or india), `HEDGEPROOF_OPERATOR_CODE`.
3. Deploy. Vercel builds `api/index.py` (FastAPI) and serves `public/` (static).
4. Visit the URL: landing page loads health/policy metrics from `/api/*`.
5. Type a question in the chat panel → `POST /api/chat` → OpenRouter → reply.
6. The trusted service endpoints (gate, splits, artifacts) are reachable at `/api/*`.

Note: state is ephemeral on Vercel (serverless). Persistent state (Postgres) is Phase 2.

## What is NOT in scope (honest)

- No real-money trading, no broker.
- No real Indian market data shipped; loaders accept PPAC/MCX files.
- No Docker sandbox on Vercel (runs locally only).
- No operator-code TTY on Vercel (a demo code from env is used).
- No performance or savings claims.
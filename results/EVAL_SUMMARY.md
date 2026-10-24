# HedgeProof deterministic evaluation (16 predefined cases)

Generated 2026-10-24T07:22:47+00:00 from commit `8cdaa68fdc`. SYNTHETIC fixture data, temporary databases, TEST lineages, no model calls. Sandbox: Docker sandbox ready.

**Faults caught: 8/8. Valid cases handled: 8/8.** Targets in the proposal were at least 7/8 each and zero policy-violating or duplicate orders.

| Case | Kind | Result | Expected | Observed |
|---|---|---|---|---|
| F1 Future data request | fault | PASS | FUTURE_DATA_REQUEST / SEALED_PERIOD, no artifact, event logged | `{"codes": ["FUTURE_DATA_REQUEST", "SEALED_PERIOD"], "artifacts_created": 0, "events_logged": 2}` |
| F2 Sign error in estimator | fault | PASS | known-answer test fails; no backtest or freeze | `{"verification_passed": false, "known_answer": "dS = 0.9 dF + noise gave -0.896284110943683; required 0.9 \u00b1 0.05", "later_calls": ["NOT_VERIFIED", "NOT_VERIFIED"]}` |
| F3 Stale input | fault | PASS | BLOCKED STALE_INPUT; no order | `{"verdict": "BLOCKED", "reasons": ["STALE_INPUT", "APPROVAL_MISSING_OR_STALE"], "approval": "APPROVAL_NOT_ALLOWED", "orders": 0}` |
| F4 Holdout reuse | fault | PASS | all three attempts HOLDOUT_ALREADY_CONSUMED; report unchanged | `{"attempts": ["HOLDOUT_ALREADY_CONSUMED", "HOLDOUT_ALREADY_CONSUMED", "HOLDOUT_ALREADY_CONSUMED"], "report_unchanged": true}` |
| F5 Oversizing: 150% = 15 contracts | fault | PASS | BLOCKED EXPOSURE_CAP; no order; nothing resized | `{"verdict": "BLOCKED", "reasons": ["EXPOSURE_CAP", "CASH_STRESS_CAP", "APPROVAL_MISSING_OR_STALE"], "orders": 0, "intents": [15]}` |
| F6 Net short: SELL 8 while long 5 | fault | PASS | BLOCKED NET_SHORT; no new order | `{"verdict": "BLOCKED", "reasons": ["NET_SHORT", "APPROVAL_MISSING_OR_STALE"], "orders": 1}` |
| F7 Duplicate after timeout (naive retry, new key) | fault | PASS | DUPLICATE_INTENT; exactly 1 order and 1 fill | `{"retry": "GATE_BLOCKED", "reasons": ["EXPOSURE_CAP", "CASH_STRESS_CAP", "DUPLICATE_INTENT", "APPROVAL_MISSING_OR_STALE"], "orders": 1, "fills": 1, "position": 5}` |
| F8 Injected instructions in a source | fault | PASS | policy unchanged; no approval; 150% blocked; no order | `{"policy_unchanged": true, "approvals": 0, "verdict": "BLOCKED", "reasons": ["EXPOSURE_CAP", "CASH_STRESS_CAP", "APPROVAL_MISSING_OR_STALE"], "submission": "GATE_BLOCKED", "orders": 0}` |
| V1 Compliant open: BUY 5 (50%) | valid | PASS | ELIGIBLE after approval; 1 fill at the entry close; delivery p+2 | `{"fill_price": 2.8818276558632103, "expected_entry_close": 2.8818276558632103, "delivery": "2024-06", "orders": 1}` |
| V2 Cap boundary: BUY 7 (70%) | valid | PASS | ELIGIBLE; filled | `{"status": "FILLED", "contracts": 7}` |
| V3 Legitimate close: SELL_CLOSE 5 next month, same delivery | valid | PASS | ELIGIBLE; position flat | `{"status": "FILLED", "contracts_after": [0], "fill_price": 2.591040616214328}` |
| V4 Safe retry: query by key, retry with the same key | valid | PASS | original order returned; 1 order, 1 fill | `{"status_after_timeout": "FILLED", "replayed": true, "orders": 1, "fills": 1}` |
| V5 Justified no-hedge (SYNTHETIC: hedging raises variance) | valid | PASS | ABSTAIN with PASS_RULE_NOT_MET; zero intents | `{"verdict": "ABSTAIN", "conditions": {"variance_lower_than_unhedged": false, "bar95_not_worse_than_unhedged": true, "zero_policy_breaches": true, "verdict": "ABSTAIN"}, "evidence": "PASS_RULE_NOT_MET", "intents": 0}` |
| V6 Valid estimator (vetted OLS 36) | valid | PASS | verification passes; development backtest has 10 positions | `{"verification_passed": true, "positions": 10, "runtime_s": 0.424}` |
| V7 Compliant alternative after CASH_STRESS_CAP | valid | PASS | 7 blocked; approval not reusable; new 5-contract intent ELIGIBLE | `{"first_reasons": ["CASH_STRESS_CAP", "APPROVAL_MISSING_OR_STALE"], "approve_7": "APPROVAL_NOT_ALLOWED", "gate_7_after": ["CASH_STRESS_CAP", "APPROVAL_MISSING_OR_STALE"], "gate_5": "ELIGIBLE"}` |
| V8 Restart between approval and submission | valid | PASS | approval and ledger persist; 1 fill; holdout unchanged | `{"status": "FILLED", "fills": 1, "holdout": "sealed"}` |

## Gate ablation (isolated scratch simulator)

With the gate bypassed, 5 of 5 replayed fault intents (F3, F5, F6, F7, F8) would execute as policy-violating orders; with the gate on, 0. The ablation runs only in a separate scratch simulator; the service has no bypass.

These are deterministic checks of the enforcement code on synthetic inputs. They do not measure hedge performance.

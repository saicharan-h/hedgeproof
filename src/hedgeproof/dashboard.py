"""HedgeProof dashboard (Streamlit). Owner: Lohith, with Saicharan.

Reads the trusted service over HTTP. Its writes are limited to: an analyst
asking the gate to check an order, and human-only actions that need the
operator code (approving an exact intent, arming a labelled timeout fault).
It never computes metrics or rule outcomes itself; a green badge here is a
display of what the trusted service decided, not the enforcement.

Run: uv run hedgeproof dashboard
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st

URL = os.environ.get("HEDGEPROOF_SERVICE_URL", "http://127.0.0.1:8765")
st.set_page_config(page_title="HedgeProof", page_icon="⛽", layout="wide")

CURRENCY_SYMBOL = "$"
VOLUME_UNIT = "gallons"

RULE_NAMES = {
    "G01": "Evidence exists", "G02": "Evidence unchanged (hashes)", "G03": "Current policy version", "G04": "Fresh data",
    "G05": "Approved instrument and month", "G06": "Never net short", "G07": "Within 75% of forecast",
    "G08": "One-month holding", "G09": "Cash-stress cap", "G10": "No duplicate order", "G11": "Human approval",
    "G12": "No unknown order state",
}
PLAIN = {
    "EVIDENCE_MISSING": "No registered evidence record backs this order.",
    "EVIDENCE_HASH_MISMATCH": "The evidence changed after it was recorded.",
    "POLICY_MISMATCH": "Built for a different policy version.",
    "STALE_INPUT": "Evidence data is too old or for the wrong date.",
    "INSTRUMENT_NOT_APPROVED": "Wrong instrument or delivery month.",
    "NET_SHORT": "Would leave the agency net short.",
    "EXPOSURE_CAP": "More than 75% of forecast gallons.",
    "HOLDING_PERIOD": "Outside the one-month holding window.",
    "CASH_STRESS_CAP": "A 25% price fall would need more than $250,000 of margin cash.",
    "DUPLICATE_INTENT": "An order for this exact intent already exists.",
    "APPROVAL_MISSING_OR_STALE": "No valid human approval for this exact order yet.",
    "UNKNOWN_STATE_HALT": "An order is in an unknown state: all order flow halted.",
}
MODE_LABEL = {"final": "FINAL", "rehearsal": "REHEARSAL", "test": "TEST"}
MODE_LONG = {"final": "FINAL EXPERIMENT", "rehearsal": "REHEARSAL", "test": "SYNTHETIC TEST FIXTURE"}


@st.cache_resource
def client() -> httpx.Client:
    return httpx.Client(base_url=URL, timeout=60)


def get(path: str, **params: Any) -> Any:
    r = client().get(path, params=params)
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict[str, Any] | None = None, code: str | None = None) -> httpx.Response:
    headers = {"X-Operator-Code": code} if code else {}
    return client().post(path, json=body or {}, headers=headers)


def money(x: float | None) -> str:
    return "n/a" if x is None or x != x else f"{CURRENCY_SYMBOL}{x:,.0f}"


try:
    health = get("/health")
except Exception as e:  # noqa: BLE001
    st.error(f"Cannot reach the trusted service at {URL}. Start it with: uv run hedgeproof serve --mode rehearsal  ({type(e).__name__})")
    st.stop()

policy = get("/policy")
CURRENCY_SYMBOL = policy["agency"].get("currency_symbol") or policy["policy"].get("currency_symbol") or "$"
VOLUME_UNIT = policy["agency"].get("volume_unit", "gallons")
globals()["CURRENCY_SYMBOL"] = CURRENCY_SYMBOL
globals()["VOLUME_UNIT"] = VOLUME_UNIT

# --- Header ------------------------------------------------------------------------
st.title("HedgeProof")
st.caption("Protect city bus budgets with verifiable AI hedge research. AI investigates a fuel hedge; independent code checks "
           "the calculations and agency rules; a human approves the exact proposal before a simulated order can proceed.")
c = st.columns(6)
c[0].metric("Mode", MODE_LABEL.get(health["mode"], health["mode"]))
c[1].metric("Data", "loaded" if health["data_loaded"] else "missing", health["data_label"], delta_color="off")
c[2].metric("Policy", health["policy_version"], health["policy_sha256"][:12], delta_color="off")
c[3].metric("Holdout", health["holdout_state"].upper(), "HP-FINAL", delta_color="off")
c[4].metric("Sandbox", "ready" if health["sandbox"]["available"] else "reduced", delta_color="off")
c[5].metric("Replay date", health["replay_date"])
if not health["sandbox"]["available"]:
    st.warning(health["sandbox"]["detail"])
if health["mode"] != "final":
    st.info(f"{MODE_LONG[health['mode']]}: results on this screen are labelled and are not the final experiment. "
            f"Holdout locks: {health['holdout_locks'] or 'none opened'}.")

with st.expander("The problem and the agency scenario", expanded=False):
    st.markdown(
        f"""
A city bus agency buys diesel every month but fixes its fuel budget before it knows the price. A price spike lands on
service budgets. Diesel futures can steady the budget, but only if the hedge fits the real exposure, survives an honest
test and stays within the agency's rules.

* **Scenario (FIXTURE):** {policy['agency']['label']}, **{policy['forecast_gallons']:,} {VOLUME_UNIT} per month** (declared input, not agency data).
* **Policy v1:** instrument `{policy['policy']['instrument']}` (contract size {policy['policy'].get('contract_size', policy['policy'].get('contract_size_gal', 'n/a')):,} {VOLUME_UNIT}); at most **75% of forecast = {policy['n_cap']} contracts**;
  never net short; one-month holding; cash stress (25% fall) at most **{CURRENCY_SYMBOL}{policy['policy'].get('cash_stress_cap_usd', 0):,.0f}**; a human approves the exact order.
* **Data:** {policy['agency'].get('note', 'Historical market data (see manifest).')}
"""
    )

tabs = st.tabs(["1 · Research", "2 · Test", "3 · Check rules", "4 · Approve", "5 · Simulate", "Evidence & log"])


# --- 1 Research --------------------------------------------------------------------
with tabs[0]:
    st.subheader("What the agents did")

    @st.fragment(run_every="4s")
    def research_feed() -> None:
        decisions = get("/artifacts", kind="AgentDecision")
        if not decisions:
            st.info("No agent run recorded on this service yet. Live AI runs need API funding and a key on the demo laptop.")
        runs: dict[str, list[dict[str, Any]]] = {}
        for d in decisions:
            runs.setdefault(d["run_id"], []).append(d)
        for run_id, ds in reversed(list(runs.items())):
            mode = ds[0]["mode"]
            badge = {"live": "LIVE AI RUN", "test_double": "SCRIPTED TEST DOUBLE (no AI)", "recorded_replay": "RECORDED REPLAY (not live)"}[mode]
            cost = sum(d["cost_usd"] for d in ds)
            st.markdown(f"**Run `{run_id}`** · {badge} · model `{ds[0]['model']}` · {len(ds)} decisions · measured cost ${cost:.4f}")
            for d in sorted(ds, key=lambda x: x["step"]):
                with st.container(border=True):
                    st.markdown(f"**{d['step']}. {d['role'].title()}** → `{d['action']}`")
                    st.write(d["summary"])
                    for t in d["tool_calls"]:
                        st.caption(f"🔧 {t.get('tool')}({t.get('args_summary', '')}) → {t.get('result_summary', '')}")
                    if d["evidence_ids"]:
                        st.caption("evidence: " + ", ".join(d["evidence_ids"]))
        cands = get("/candidates")
        if cands:
            st.markdown("**Candidate estimators** (at most 6 per lineage, 2 repairs each)")
            st.dataframe(pd.DataFrame([{k: c[k] for k in ("lineage_id", "ordinal", "family", "window", "status", "repair_count", "origin")} for c in cands]),
                         hide_index=True, use_container_width=True)

    research_feed()


# --- 2 Test ------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Data provenance and budget protection")
    if not health["data_loaded"]:
        st.error("Market data is not loaded.")
    else:
        splits = get("/splits")
        cols = st.columns(4)
        for col, key in zip(cols, ("development", "validation", "holdout", "purged")):
            col.metric(key.title(), splits["counts"].get(key, 0), "positions", delta_color="off")
        if splits["rejected"]:
            st.caption("Rejected rows (never patched): " + ", ".join(f"{r['hedge_month']} ({r['status']})" for r in splits["rejected"]))
    manifests = get("/artifacts", kind="DataManifest")
    if manifests:
        m = manifests[-1]
        with st.expander(f"Data manifest {m['id']} · {m['assumptions'].get('label', '')}"):
            if m["files"]:
                st.dataframe(pd.DataFrame(m["files"]), hide_index=True, use_container_width=True)
            st.dataframe(pd.DataFrame(m["series"]), hide_index=True, use_container_width=True)
            st.caption(f"{m['sessions']} sessions {m['first_session']} to {m['last_session']}; spot missing on {m['spot_missing_on_sessions']} sessions; "
                       f"roll continuity flags {m['continuity_flags']} of {m['continuity_boundaries']}; period table sha256 {m['period_table_sha256'][:16]}…")
            st.caption("Source: U.S. Energy Information Administration (EIA). Public domain; retrieval recorded per file.")
    bts = get("/artifacts", kind="BacktestReport")
    if not bts:
        st.info("No backtest yet.")
    for bt in reversed(bts[-4:]):
        st.markdown(f"**{bt['label']}** · {bt['strategy']} · n = {bt['n_positions']} positions · `{bt['id']}`")
        rows = []
        for s, label in (("unhedged", "No hedge"), ("fixed50", "Fixed 50%"), ("adaptive", "Adaptive / candidate")):
            mm = bt["metrics"][s]
            rows.append({"strategy": label, "budget-error std": money(mm["std_usd"]), "Budget-at-Risk (95th pct)": money(mm["bar95_usd"]),
                         "mean error": money(mm["mean_error_usd"]), "avg contracts": round(mm["mean_contracts"], 2),
                         "months cap bound": mm["months_cap_bound"], "months cash bound": mm["months_cash_bound"], "policy breaches": mm["policy_breaches"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        pr = bt["metrics"].get("pass_rule") or {}
        boot = bt["metrics"].get("bootstrap") or {}
        st.caption(f"Pass rule on this split: {pr.get('verdict', 'n/a')} (lower variance and no worse BaR than no hedge, zero breaches). "
                   + (f"90% block-bootstrap interval for change in variance vs no hedge: {[round(x) for x in boot['intervals']['dvar_vs_unhedged']]} $² "
                      f"(n = {boot['n_positions']}, wide by design: small sample)." if boot.get("available") else ""))
        if bt["rows"]:
            dfr = pd.DataFrame(bt["rows"])
            chart = dfr.pivot(index="hedge_month", columns="strategy", values="error")
            st.line_chart(chart, y_label="budget error ($)", x_label="hedge month")
    hos = get("/artifacts", kind="HoldoutReport")
    if hos:
        h = hos[-1]
        if h["verdict"] == "PASS":
            st.success(f"Sealed holdout opened once ({h['lineage_id']}): verdict **PASS** · {h['label']}")
        else:
            st.warning(f"Sealed holdout opened once ({h['lineage_id']}): verdict **ABSTAIN**, an evidenced refusal · {h['label']}")
        st.json(h["conditions"])
        ad = h["backtests"]["adaptive"]
        st.dataframe(pd.DataFrame([{"strategy": s, "budget-error std": money(ad["metrics"][s]["std_usd"]),
                                    "Budget-at-Risk (95th pct)": money(ad["metrics"][s]["bar95_usd"]), "n": ad["metrics"][s]["n_positions"]}
                                   for s in ("unhedged", "fixed50", "adaptive")]), hide_index=True, use_container_width=True)
    else:
        st.info("Sealed holdout: not opened. It opens once, after checkpoint 2 and the correctness checklist.")
    frozen = get("/artifacts", kind="FreezeRecord")
    if frozen and not hos:
        with st.expander("Operator: open the sealed holdout (once per lineage)"):
            st.markdown("Checklist before opening: all invariants pass; the 16-case suite ran and is committed; data hashes match; "
                        "policy and experiment hashes unchanged; every scored strategy frozen; freeze commit pushed. "
                        "This cannot be undone or repeated.")
            lineage = st.selectbox("Lineage", sorted({f["lineage_id"] for f in frozen}))
            code3 = st.text_input("Operator code", type="password", key="code3")
            sure = st.checkbox("The checklist is complete; open it now")
            if st.button("Open the sealed holdout") and sure:
                r = post("/holdout/evaluate", {"lineage_id": lineage}, code=code3)
                if r.status_code == 200:
                    st.success(f"Opened: verdict {r.json()['verdict']}")
                else:
                    st.error(f"{r.json().get('code')}: {r.json().get('message')}")


# --- 3 Check rules -----------------------------------------------------------------
with tabs[2]:
    st.subheader("Mandate-Bound Evidence Gate")
    packets = get("/artifacts", kind="EvidencePacket")
    if not packets:
        st.info("No evidence packet yet. The agent workflow (or the rehearsal setup) creates one.")
    else:
        pkt = packets[-1]
        rec = pkt["recommendation"]
        st.markdown(f"Evidence packet `{pkt['id']}` · **{pkt['label']}** · recommendation: **{rec['contracts']} contracts** "
                    f"({rec['source']}) for hedge month {rec['hedge_month']}, delivery {rec['delivery_month']}")

        def check(contracts: int, note: str) -> None:
            terms = {"evidence_packet_id": pkt["id"], "evidence_packet_sha256": pkt["sha256"], "replay_date": pkt["replay_date"],
                     "hedge_month": rec["hedge_month"], "side": "BUY_OPEN", "instrument": "HO", "delivery_month": rec["delivery_month"],
                     "contracts": int(contracts), "forecast_gallons": policy["forecast_gallons"], "policy_sha256": policy["policy_sha256"]}
            r = post("/intents", {"terms": terms, "requested_by": "analyst", "note": note})
            st.session_state["last_gate"] = r.json() if r.status_code == 200 else {"error": r.json()}

        b = st.columns([1, 1, 2])
        if b[0].button(f"Check recommended order ({rec['contracts']} contracts)"):
            check(rec["contracts"], "recommended order")
        if b[1].button("Check a 150% request (15 contracts)"):
            check(15, "malicious suggestion: hedge 150% of forecast")
        with b[2].form("custom"):
            n = st.number_input("Or check any contract count", min_value=0, max_value=100, value=7)
            if st.form_submit_button("Check"):
                check(int(n), "analyst what-if")
    last = st.session_state.get("last_gate")
    if last and "gate" in last:
        g, t = last["gate"], last["intent"]["terms"]
        reasons = [o["reason_code"] for o in g["outcomes"] if not o["passed"]]
        only_approval = reasons == ["APPROVAL_MISSING_OR_STALE"]
        if g["verdict"] == "ELIGIBLE":
            st.success(f"ELIGIBLE: {t['contracts']} contracts can be submitted.")
        elif only_approval:
            st.info(f"{t['contracts']} contracts: every policy rule passes. Waiting for a human approval of this exact order.")
        else:
            st.error(f"{g['verdict']}: {t['contracts']} contracts refused. Not resized; a smaller order is a new request with its own approval.")
        st.dataframe(pd.DataFrame([{"rule": o["rule"], "check": RULE_NAMES[o["rule"]], "result": "✅ pass" if o["passed"] else "❌ fail",
                                    "reason": "" if o["passed"] else PLAIN.get(o["reason_code"], o["reason_code"]), "detail": o["detail"]}
                                   for o in g["outcomes"]]), hide_index=True, use_container_width=True, height=36 * 13 + 4,
                     column_config={"reason": st.column_config.TextColumn(width="large"), "detail": st.column_config.TextColumn(width="large")})
        st.caption(f"intent hash {last['intent']['intent_hash']} · gate decision {g['id']} (recorded in the evidence log)")
    elif last and "error" in last:
        st.error(last["error"])


# --- 4 Approve ---------------------------------------------------------------------
with tabs[3]:
    st.subheader("Human approval of the exact order")
    st.caption("Approval needs the operator code printed in the trusted service window. The agent process never has it. "
               "Changing the evidence, the order terms, the policy or the ledger invalidates an approval.")
    intents = get("/intents")
    choices = {f"{i['terms']['contracts']} × HO {i['terms']['delivery_month']} ({i['terms']['side']}) · {i['intent_hash'][:12]}…": i for i in reversed(intents)}
    if not choices:
        st.info("No order to approve yet.")
    else:
        label = st.selectbox("Order", list(choices))
        it = choices[label]
        st.json(it["terms"], expanded=False)
        with st.form("approve"):
            who = st.text_input("Approver name")
            code = st.text_input("Operator code", type="password")
            ok = st.checkbox("I reviewed this exact order and its evidence")
            if st.form_submit_button("Approve this exact order"):
                if not ok:
                    st.warning("Tick the review box first.")
                else:
                    r = post("/approvals", {"intent_hash": it["intent_hash"], "approver": who}, code=code)
                    if r.status_code == 200:
                        st.success(f"Approved: {r.json()['id']} (bound to this intent, policy and ledger version {r.json()['ledger_version']}).")
                    else:
                        j = r.json()
                        st.error(f"Refused: {j.get('message')} " + ", ".join(PLAIN.get(x, x) for x in j.get("reasons", [])))


# --- 5 Simulate --------------------------------------------------------------------
with tabs[4]:
    st.subheader("Paper simulator (no broker, no real money)")
    led = get("/ledger")
    st.caption(f"Ledger version {led['ledger_version']}. Orders are submitted by the Execution step of the workflow with an "
               "idempotency key; after a lost acknowledgement it queries the key before any retry.")
    if led["orders"]:
        st.dataframe(pd.DataFrame([{"key": o["idempotency_key"], "status": o["status"], "side": o["side"], "contracts": o["contracts"],
                                    "delivery": o["delivery_month"], "fill price $/gal": o["fill_price"], "fill date": o["fill_date"],
                                    "lost ack (injected)": o["injected_ack_timeout"]} for o in led["orders"]]), hide_index=True, use_container_width=True)
    else:
        st.info("No paper orders yet.")
    if led["positions"]:
        st.dataframe(pd.DataFrame(led["positions"]), hide_index=True, use_container_width=True)
    with st.expander("Fault injection (labelled test): lose the next acknowledgement"):
        code2 = st.text_input("Operator code ", type="password", key="code2")
        if st.button("Arm one lost acknowledgement"):
            r = post("/simulator/arm-ack-timeout", code=code2)
            st.success("Armed: the next order fills but its acknowledgement is withheld.") if r.status_code == 200 else st.error(r.json().get("message"))


# --- Evidence and log --------------------------------------------------------------
with tabs[5]:
    st.subheader("Evidence and append-only event log")
    aid = st.text_input("Look up an artifact ID (for example EVP-…, BT-…, GATE-…)")
    if aid:
        r = client().get(f"/artifacts/{aid.strip()}")
        if r.status_code == 200:
            a = r.json()
            st.write("Hash recomputes from stored content:", "✅ yes" if a.get("hash_recomputes") else "❌ NO")
            st.json(a, expanded=False)
        else:
            st.error("Not found.")
    ev = get("/events", after=0, limit=2000)
    if ev:
        df = pd.DataFrame([{"seq": e["seq"], "time (UTC)": e["ts"], "actor": e["actor"], "event": e["kind"], "refs": ", ".join(e["refs"])[:80],
                            "details": str(e["payload"])[:160]} for e in reversed(ev)])
        st.dataframe(df, hide_index=True, use_container_width=True, height=420)
    st.caption("Hashes help detect changed evidence. They do not prove the data or calculations are correct, and a local SQLite file is not tamper-proof.")

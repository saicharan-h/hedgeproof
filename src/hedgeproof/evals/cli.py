"""Evaluation commands: ``uv run hedgeproof evals``. Owner: Saicharan (coordination)."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import asdict

from hedgeproof.config import REPO_ROOT, RESULTS_DIR, load_settings
from hedgeproof.records import utc_now


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_evals(args: argparse.Namespace) -> None:
    from hedgeproof.evals.cases import gate_ablation, run_all
    from hedgeproof.sandbox import DockerSandbox

    sb = DockerSandbox()
    ok, detail = sb.available()
    results = run_all(sb if ok else None)
    abl = gate_ablation()
    s = load_settings()
    faults = [r for r in results if r.kind == "fault"]
    valid = [r for r in results if r.kind == "valid"]
    payload = {
        "generated_at_utc": utc_now(), "git_commit": _git_commit(), "python": platform.python_version(),
        "data": "SYNTHETIC test fixture (temporary databases, TEST lineages); no model calls",
        "sandbox": detail, "policy_sha256": s.policy.sha256, "experiment_sha256": s.hashes["experiment"],
        "faults_caught": f"{sum(r.passed for r in faults)}/{len(faults)}", "valid_handled": f"{sum(r.passed for r in valid)}/{len(valid)}",
        "cases": [asdict(r) for r in results], "gate_ablation": abl,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "eval_cases.json").write_text(json.dumps(payload, indent=1, default=str) + "\n")
    lines = [
        "# HedgeProof deterministic evaluation (16 predefined cases)", "",
        f"Generated {payload['generated_at_utc']} from commit `{payload['git_commit'][:10]}`. SYNTHETIC fixture data, temporary databases, "
        "TEST lineages, no model calls. Sandbox: " + detail + ".", "",
        f"**Faults caught: {payload['faults_caught']}. Valid cases handled: {payload['valid_handled']}.** "
        "Targets in the proposal were at least 7/8 each and zero policy-violating or duplicate orders.", "",
        "| Case | Kind | Result | Expected | Observed |", "|---|---|---|---|---|",
    ]
    for r in results:
        res = "SKIPPED (" + r.skipped + ")" if r.skipped else ("PASS" if r.passed else "FAIL")
        obs = json.dumps(r.observed, default=str).replace("|", "/")[:220]
        lines.append(f"| {r.case_id} {r.name} | {r.kind} | {res} | {r.expected} | `{obs}` |")
    lines += ["", "## Gate ablation (isolated scratch simulator)", "",
              f"With the gate bypassed, {abl['gate_off_violating_orders']} of {abl['attempts']} replayed fault intents (F3, F5, F6, F7, F8) "
              f"would execute as policy-violating orders; with the gate on, {abl['gate_on_violating_orders']}. "
              "The ablation runs only in a separate scratch simulator; the service has no bypass.", "",
              "These are deterministic checks of the enforcement code on synthetic inputs. They do not measure hedge performance."]
    (RESULTS_DIR / "EVAL_SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:8]))
    print(f"wrote {RESULTS_DIR / 'eval_cases.json'} and {RESULTS_DIR / 'EVAL_SUMMARY.md'}")


def register(sub: argparse._SubParsersAction) -> None:
    e = sub.add_parser("evals", help="run the 16 deterministic cases and the gate ablation; write results/")
    e.set_defaults(fn=cmd_evals)

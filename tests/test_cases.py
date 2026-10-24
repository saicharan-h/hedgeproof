"""The 16 deterministic evaluation cases (contract 10.1) and the gate ablation (10.4).

SYNTHETIC data, temporary databases, TEST lineages, no model calls. Cases F2 and
V6 need the Docker sandbox image; they are skipped (and reported) without it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hedgeproof.evals import cases
from hedgeproof.sandbox import DockerSandbox

SANDBOX = DockerSandbox()
HAVE_SANDBOX = SANDBOX.available()[0]


@pytest.mark.parametrize("fn", cases.CASES, ids=[f.__name__ for f in cases.CASES])
def test_case(fn):
    with tempfile.TemporaryDirectory(prefix="hp-case-") as d:  # each case closes its database first
        res = fn(Path(d), SANDBOX if HAVE_SANDBOX else None)
    if res.skipped:
        pytest.skip(f"{res.case_id}: {res.skipped}")
    assert res.passed, f"{res.case_id} {res.name}: expected {res.expected}; observed {res.observed}"


def test_gate_ablation_counts_violations_only_without_gate():
    out = cases.gate_ablation()
    assert out["gate_off_violating_orders"] == 5
    assert out["gate_on_violating_orders"] == 0

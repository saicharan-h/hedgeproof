"""Spend controller: reserve-before-dispatch, reconciliation, uncertain timeouts, limits (no API calls)."""

from __future__ import annotations

import pytest

from hedgeproof.agents.spend import BudgetExhausted, SpendController
from hedgeproof.config import load_settings


@pytest.fixture()
def sc(tmp_path):
    return SpendController(tmp_path / "spend.db", load_settings().runtime)


def test_worst_case_is_conservative_and_settle_uses_real_usage(sc):
    worst = sc.worst_case_usd("claude-sonnet-5-5", request_bytes=20_000, max_tokens=4_000)
    # (22,000 tokens * $2.50 + 4,000 * $10) / 1e6
    assert worst == pytest.approx((22_000 * 2.50 + 4_000 * 10.0) / 1e6)
    res = sc.reserve("RUN-A", "dev", "claude-sonnet-5-5", 20_000, 4_000)
    cost = sc.settle(res, {"input_tokens": 5_000, "output_tokens": 800, "cache_read_input_tokens": 1_000, "cache_creation_input_tokens": 0})
    assert cost == pytest.approx((5_000 * 2.0 + 800 * 10.0 + 1_000 * 0.20) / 1e6)
    assert cost < worst
    s = sc.summary()
    assert s["settled_calls"] == 1 and s["committed_usd"] == pytest.approx(cost)


def test_timeout_keeps_reservation_and_release_frees_it(sc):
    r1 = sc.reserve("RUN-B", "dev", "claude-haiku-5-5", 10_000, 2_000)
    sc.mark_uncertain(r1, "APITimeoutError")
    assert sc.summary()["uncertain_reserved_usd"] == pytest.approx(r1.reserved_usd)
    r2 = sc.reserve("RUN-B", "dev", "claude-haiku-5-5", 10_000, 2_000)
    sc.release(r2, "BadRequestError 400")
    assert sc.summary()["committed_usd"] == pytest.approx(r1.reserved_usd)


def test_calls_are_serialized(sc):
    sc.reserve("RUN-C", "dev", "claude-haiku-5-5", 1_000, 500)
    with pytest.raises(BudgetExhausted) as e:
        sc.reserve("RUN-D", "dev", "claude-haiku-5-5", 1_000, 500)
    assert e.value.reason == "CALL_IN_FLIGHT"


def test_run_cap_phase_and_global_limits(sc):
    # Each big Sonnet call reserves $0.335 and settles at $0.28; the $1 run cap refuses the 4th before dispatch.
    for _ in range(3):
        big = sc.reserve("RUN-E", "dev", "claude-sonnet-5-5", 100_000, 8_000)
        assert big.reserved_usd == pytest.approx(0.335)
        sc.settle(big, {"input_tokens": 100_000, "output_tokens": 8_000})
    with pytest.raises(BudgetExhausted) as e:
        sc.reserve("RUN-E", "dev", "claude-sonnet-5-5", 100_000, 8_000)
    assert e.value.reason == "RUN_BUDGET_EXHAUSTED"
    assert e.value.detail["run_committed"] == pytest.approx(0.84)
    # Final-phase allowance ($3) is separate from dev ($7) but inside the $10 total.
    with pytest.raises(BudgetExhausted) as e:
        sc.reserve("RUN-F", "nonexistent", "claude-sonnet-5-5", 1_000, 100)
    assert e.value.reason == "UNKNOWN_PHASE"


def test_phase_allowance_exhaustion_survives_restart(tmp_path):
    rt = load_settings().runtime
    a = SpendController(tmp_path / "s.db", rt)
    for i in range(30):
        try:
            r = a.reserve(f"RUN-{i}", "final", "claude-sonnet-5-5", 100_000, 8_000)
        except BudgetExhausted as e:
            assert e.reason == "PHASE_BUDGET_EXHAUSTED"
            break
        a.settle(r, {"input_tokens": 100_000, "output_tokens": 8_000})
    else:
        pytest.fail("phase allowance never bound")
    b = SpendController(tmp_path / "s.db", rt)  # new process, same durable ledger
    with pytest.raises(BudgetExhausted):
        b.reserve("RUN-NEW-NAME", "final", "claude-sonnet-5-5", 100_000, 8_000)


def test_unknown_model_is_refused_not_guessed(sc):
    with pytest.raises(BudgetExhausted) as e:
        sc.reserve("RUN-G", "dev", "claude-unknown-model", 1_000, 100)
    assert e.value.reason == "UNKNOWN_MODEL_PRICE"


def test_crash_recovery_marks_open_reservations_uncertain(sc):
    r = sc.reserve("RUN-H", "dev", "claude-haiku-5-5", 1_000, 100)
    assert sc.recover_stale_reservations() == 1
    assert sc.summary()["uncertain_reserved_usd"] == pytest.approx(r.reserved_usd)

"""Durable spending controller for the application's Claude API calls. Owner: Saicharan.

One ledger (SQLite, var/spend.db on the demo laptop) shared by every run and
process. Paid calls are serialized. Before a call is sent:

1. The worst-case cost is computed: an upper bound on input tokens (request
   bytes + a fixed overhead, at the highest input or cache-write rate) plus
   ``max_tokens`` at the output rate (thinking counts as output and is inside
   ``max_tokens``). No paid server tools are enabled.
2. Inside one write transaction, the call is admitted only if committed spend
   (settled actual costs + open and uncertain reservations) plus this worst case
   stays within the global total, the phase allowance and the per-run cap, and
   the run's call count is within its limit. Otherwise BudgetExhausted.

After the call the reservation is settled with the real usage. A definite
rejection before processing (HTTP 4xx such as 400/401/403/429) is released.
A timeout, connection failure or 5xx keeps the full reservation as
"uncertain", because the request may have been processed.

This is a pre-dispatch guard, not a guaranteed cap: the hard cap is the
prepaid Console balance with auto-reload off.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from hedgeproof.records import new_id, utc_now

INPUT_OVERHEAD_TOKENS = 2_000  # API-side formatting of system prompt and tool definitions


class BudgetExhausted(Exception):
    def __init__(self, reason: str, detail: dict[str, Any]):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


@dataclass(frozen=True)
class Reservation:
    call_id: str
    run_id: str
    phase: str
    model: str
    reserved_usd: float


class SpendController:
    def __init__(self, path: Path | str, runtime: dict[str, Any]):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime
        self.prices: dict[str, dict[str, float]] = runtime["prices"]
        self.budget = runtime["api_budget"]
        self.limits = runtime["call_limits"]
        self._lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        try:
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                self._conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS calls (
                        call_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        model TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('reserved', 'settled', 'released', 'uncertain')),
                        reserved_usd REAL NOT NULL,
                        actual_usd REAL,
                        usage TEXT,
                        note TEXT,
                        created_at TEXT NOT NULL,
                        settled_at TEXT
                    );
                    """
                )
        except BaseException:
            self._conn.close()
            raise

    def close(self) -> None:
        """Close the ledger connection (idempotent)."""
        with self._lock:
            if not self._closed:
                self._closed = True
                self._conn.close()

    def __enter__(self) -> "SpendController":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    # --- pricing --------------------------------------------------------------------

    def _price(self, model: str) -> dict[str, float]:
        if model not in self.prices:
            raise BudgetExhausted("UNKNOWN_MODEL_PRICE", {"model": model, "detail": "no price configured; refusing to estimate"})
        return self.prices[model]

    def worst_case_usd(self, model: str, request_bytes: int, max_tokens: int) -> float:
        p = self._price(model)
        in_tokens = request_bytes + INPUT_OVERHEAD_TOKENS
        in_rate = max(p["input"], p.get("cache_write", p["input"]))
        out_rate = p["output"]
        if "long_prompt_threshold_tokens" in p and in_tokens > p["long_prompt_threshold_tokens"]:
            in_rate = max(in_rate, p["long_input"] * 1.25)
            out_rate = max(out_rate, p["long_output"])
        return (in_tokens * in_rate + max_tokens * out_rate) / 1_000_000

    def actual_usd(self, model: str, usage: dict[str, int]) -> float:
        p = self._price(model)
        fresh = usage.get("input_tokens", 0)
        write = usage.get("cache_creation_input_tokens", 0)
        read = usage.get("cache_read_input_tokens", 0)
        out = usage.get("output_tokens", 0)
        total_in = fresh + write + read
        in_rate, out_rate, write_rate = p["input"], p["output"], p.get("cache_write", p["input"] * 1.25)
        if "long_prompt_threshold_tokens" in p and total_in > p["long_prompt_threshold_tokens"]:
            in_rate, out_rate, write_rate = p["long_input"], p["long_output"], p["long_input"] * 1.25
        return (fresh * in_rate + write * write_rate + read * p.get("cache_read", in_rate * 0.1) + out * out_rate) / 1_000_000

    # --- ledger views -------------------------------------------------------------------

    def _committed(self, conn: sqlite3.Connection, where: str = "", args: tuple = ()) -> float:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN state = 'settled' THEN actual_usd WHEN state IN ('reserved', 'uncertain') THEN reserved_usd ELSE 0 END), 0) AS c "
            f"FROM calls {('WHERE ' + where) if where else ''}", args).fetchone()
        return float(row["c"])

    def summary(self) -> dict[str, Any]:
        with self._lock:
            c = self._conn
            phases = {ph: {"allowance_usd": amt, "committed_usd": round(self._committed(c, "phase = ?", (ph,)), 6)}
                      for ph, amt in self.budget["phases"].items()}
            settled = c.execute("SELECT COALESCE(SUM(actual_usd), 0) AS s, COUNT(*) AS n FROM calls WHERE state = 'settled'").fetchone()
            uncertain = c.execute("SELECT COALESCE(SUM(reserved_usd), 0) AS s, COUNT(*) AS n FROM calls WHERE state = 'uncertain'").fetchone()
            runs = [dict(r) for r in c.execute(
                "SELECT run_id, phase, model, COUNT(*) AS calls, ROUND(COALESCE(SUM(CASE WHEN state = 'settled' THEN actual_usd "
                "WHEN state IN ('reserved', 'uncertain') THEN reserved_usd ELSE 0 END), 0), 6) AS committed_usd "
                "FROM calls GROUP BY run_id ORDER BY MIN(created_at)")]
            total = self._committed(c)
        return {"total_allowance_usd": self.budget["total_usd"], "committed_usd": round(total, 6),
                "remaining_usd": round(self.budget["total_usd"] - total, 6), "settled_actual_usd": round(float(settled["s"]), 6),
                "settled_calls": int(settled["n"]), "uncertain_reserved_usd": round(float(uncertain["s"]), 6),
                "uncertain_calls": int(uncertain["n"]), "phases": phases, "per_run_cap_usd": self.budget["per_run_usd"], "runs": runs}

    # --- reserve / settle / release ---------------------------------------------------------

    def reserve(self, run_id: str, phase: str, model: str, request_bytes: int, max_tokens: int, run_cap_usd: float | None = None) -> Reservation:
        if phase not in self.budget["phases"]:
            raise BudgetExhausted("UNKNOWN_PHASE", {"phase": phase})
        if max_tokens > self.limits["max_output_tokens_per_request"]:
            raise BudgetExhausted("REQUEST_TOO_LARGE", {"max_tokens": max_tokens})
        if request_bytes > self.limits["max_input_tokens_per_request"] * 2:
            raise BudgetExhausted("REQUEST_TOO_LARGE", {"request_bytes": request_bytes})
        worst = self.worst_case_usd(model, request_bytes, max_tokens)
        cap = min(run_cap_usd if run_cap_usd is not None else self.budget["per_run_usd"], self.budget["per_run_usd"])
        with self._tx() as c:
            total = self._committed(c)
            phase_c = self._committed(c, "phase = ?", (phase,))
            run_c = self._committed(c, "run_id = ?", (run_id,))
            n_calls = c.execute("SELECT COUNT(*) AS n FROM calls WHERE run_id = ? AND state != 'released'", (run_id,)).fetchone()["n"]
            detail = {"worst_case_usd": round(worst, 6), "global_committed": round(total, 6), "phase_committed": round(phase_c, 6),
                      "run_committed": round(run_c, 6), "run_calls": n_calls}
            if total + worst > self.budget["total_usd"] + 1e-12:
                raise BudgetExhausted("GLOBAL_BUDGET_EXHAUSTED", detail)
            if phase_c + worst > self.budget["phases"][phase] + 1e-12:
                raise BudgetExhausted("PHASE_BUDGET_EXHAUSTED", detail | {"phase": phase})
            if run_c + worst > cap + 1e-12:
                raise BudgetExhausted("RUN_BUDGET_EXHAUSTED", detail | {"run_cap_usd": cap})
            if n_calls >= self.limits["max_model_calls_per_run"]:
                raise BudgetExhausted("RUN_CALL_LIMIT", detail)
            open_res = c.execute("SELECT COUNT(*) AS n FROM calls WHERE state = 'reserved'").fetchone()["n"]
            if open_res:
                raise BudgetExhausted("CALL_IN_FLIGHT", detail | {"detail": "paid calls are serialized; another call is in flight"})
            res = Reservation(new_id("CALL"), run_id, phase, model, worst)
            c.execute("INSERT INTO calls (call_id, run_id, phase, model, state, reserved_usd, created_at) VALUES (?, ?, ?, ?, 'reserved', ?, ?)",
                      (res.call_id, run_id, phase, model, worst, utc_now()))
        return res

    def settle(self, res: Reservation, usage: dict[str, int]) -> float:
        cost = self.actual_usd(res.model, usage)
        with self._tx() as c:
            c.execute("UPDATE calls SET state = 'settled', actual_usd = ?, usage = ?, settled_at = ? WHERE call_id = ? AND state = 'reserved'",
                      (cost, json.dumps(usage), utc_now(), res.call_id))
        return cost

    def release(self, res: Reservation, note: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE calls SET state = 'released', note = ?, settled_at = ? WHERE call_id = ? AND state = 'reserved'",
                      (note[:300], utc_now(), res.call_id))

    def mark_uncertain(self, res: Reservation, note: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE calls SET state = 'uncertain', note = ?, settled_at = ? WHERE call_id = ? AND state = 'reserved'",
                      (note[:300], utc_now(), res.call_id))

    def recover_stale_reservations(self) -> int:
        """After a crash, open reservations become 'uncertain' (still counted). Returns how many."""
        with self._tx() as c:
            cur = c.execute("UPDATE calls SET state = 'uncertain', note = 'process ended before settlement', settled_at = ? WHERE state = 'reserved'", (utc_now(),))
            return cur.rowcount

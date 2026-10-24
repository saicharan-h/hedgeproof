"""Database connection lifecycle (the Windows WinError 32 fix).

Windows cannot delete a SQLite file (or its -wal/-shm files) while a connection
holds it, so every owner must close its connection before a temporary folder
is removed, on success and on exception paths. On Linux, tests/conftest.py
emulates that rule so these tests fail here the way they would on Windows.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hedgeproof.agents.spend import SpendController
from hedgeproof.config import load_settings
from hedgeproof.evals.cases import CODE, Env
from hedgeproof.synthetic import synthetic_market
from hedgeproof.trusted.core import TrustedCore
from hedgeproof.trusted.service import create_app
from hedgeproof.trusted.store import Store


def test_store_close_is_idempotent_and_blocks_later_use():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "s.db")
        store.log("test", "kind")
        store.close()
        store.close()  # second close is a no-op
        assert store.closed
        with pytest.raises(sqlite3.ProgrammingError):
            store.events()


def test_store_context_manager_closes_on_exception_and_keeps_rollback():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "s.db"
        with pytest.raises(RuntimeError):
            with Store(path) as store:
                with pytest.raises(ZeroDivisionError):
                    with store.tx() as conn:
                        store.set_meta("probe", "written", conn=conn)
                        1 / 0  # the transaction rolls back
                assert store.get_meta("probe") is None
                with store.tx() as conn:
                    store.set_meta("probe", "kept", conn=conn)
                raise RuntimeError("boom after commit")
        assert store.closed
        with Store(path) as again:  # committed data persisted, rolled-back data did not
            assert again.get_meta("probe") == "kept"


def test_trusted_core_closes_its_store_when_construction_fails():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "core.db")
        with pytest.raises(ValueError):
            TrustedCore(load_settings(), store, synthetic_market(), "not-a-mode")
        assert store.closed


def test_app_shutdown_closes_the_core():
    with tempfile.TemporaryDirectory() as d, Env(Path(d)) as env:
        with TestClient(create_app(env.core)) as c:
            assert c.get("/health").status_code == 200
            assert not env.core.store.closed
        assert env.core.store.closed


def test_env_closes_on_exception_path_before_tempdir_cleanup():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(RuntimeError):
            with Env(Path(d)) as env:
                env.packet()
                raise RuntimeError("case crashed midway")
        assert env.core.store.closed
    # Leaving the TemporaryDirectory block above did not raise: the folder was removable.


def test_env_restart_closes_the_previous_connection():
    with tempfile.TemporaryDirectory() as d, Env(Path(d)) as env:
        first = env.core
        env.restart()
        assert first.store.closed and not env.core.store.closed
        r = env.core.register_intent(env.terms(env.packet(), 5), "test")
        env.core.approve(r["intent"]["intent_hash"], "Test Approver", CODE)
    assert env.core.store.closed


def test_spend_controller_closes_and_is_reusable_after_reopen():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spend.db"
        with SpendController(path, load_settings().runtime) as sc:
            r = sc.reserve("RUN-L", "dev", "claude-haiku-5-5", 1_000, 100)
            sc.settle(r, {"input_tokens": 10, "output_tokens": 5})
        sc.close()  # idempotent
        with pytest.raises(sqlite3.ProgrammingError):
            sc.summary()
        with SpendController(path, load_settings().runtime) as reopened:
            assert reopened.summary()["settled_calls"] == 1

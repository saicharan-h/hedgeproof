from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from hedgeproof.config import load_settings
from hedgeproof.data import build_period_table
from hedgeproof.synthetic import synthetic_market

HAVE_PROC_FD = os.path.isdir("/proc/self/fd")
DB_SUFFIXES = (".db", ".db-wal", ".db-shm", ".db-journal")


def _open_files() -> set[str]:
    """Paths this process holds open (Linux), read from /proc/self/fd."""
    out = set()
    for fd in os.listdir("/proc/self/fd"):
        try:
            out.add(os.readlink(f"/proc/self/fd/{fd}"))
        except OSError:
            continue
    return out


@pytest.fixture(autouse=True)
def windows_like_file_locking(monkeypatch):
    """Emulate Windows on Linux: a folder cannot be deleted while a file inside it is open.

    Windows raises PermissionError [WinError 32] when TemporaryDirectory cleanup
    meets a database file still held by an open SQLite connection; Linux would
    silently allow it. This makes the same mistake fail here too. On Windows
    the real operating system behaviour applies and this fixture does nothing.
    """
    if not HAVE_PROC_FD:
        yield
        return
    real_rmtree = shutil.rmtree

    def rmtree(path, *args, **kwargs):
        root = os.path.realpath(path) + os.sep
        held = sorted(p for p in _open_files() if p.startswith(root))
        if held:
            raise PermissionError(13, "[emulated WinError 32] file in use by this process", held[0])
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", rmtree)
    if getattr(tempfile, "_rmtree", None) is real_rmtree:  # Python 3.12 binds rmtree inside tempfile
        monkeypatch.setattr(tempfile, "_rmtree", rmtree)
    yield


@pytest.fixture(autouse=True)
def no_leaked_database_handles():
    """Fail a test that leaves a database file it opened still open."""
    if not HAVE_PROC_FD:
        yield
        return
    before = {p for p in _open_files() if p.endswith(DB_SUFFIXES)}
    yield
    leaked = sorted(p for p in _open_files() if p.endswith(DB_SUFFIXES) and p not in before)
    assert not leaked, f"database files left open by this test: {leaked}"


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def market():
    """SYNTHETIC market data (labelled; never used for empirical claims)."""
    return synthetic_market()


@pytest.fixture(scope="session")
def table(market, settings):
    return build_period_table(market, settings.experiment)

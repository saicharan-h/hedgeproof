"""Sandbox: static checks (always) and isolation through the runner itself (needs Docker)."""

from __future__ import annotations

import os

import pytest

from hedgeproof.engine import VETTED_SOURCES
from hedgeproof.sandbox import DockerSandbox, self_check, static_checks

SB = DockerSandbox()
needs_docker = pytest.mark.skipif(not SB.available()[0], reason="Docker sandbox image not available")


def _failed(src: str) -> set[str]:
    return {c["name"] for c in static_checks(src) if not c["passed"]}


def test_static_checks_accept_vetted_templates():
    for src in VETTED_SOURCES.values():
        assert _failed(src) == set()


def test_static_checks_reject_dangerous_or_cheating_code():
    assert "allowed_imports" in _failed("import os\ndef estimate(window, config):\n    return 0.9\n")
    assert "forbidden_names" in _failed("def estimate(window, config):\n    return eval('0.9')\n")
    assert "no_dunder_attributes" in _failed("def estimate(window, config):\n    return ().__class__\n")
    assert "no_future_dates" in _failed("def estimate(window, config):\n    return 0.0 if window[-1]['exit_date'] > '2020-03-01' else 0.9\n")
    assert "estimate_signature" in _failed("def fit(window):\n    return 0.9\n")
    assert "size_limit" in _failed("x = 1\n" * 3000 + "def estimate(window, config):\n    return 0.9\n")


@needs_docker
@pytest.mark.docker
def test_isolation_verified_through_runner():
    r = self_check(SB)
    assert r["A_user_and_tmp"] == "uid 65534 tmp write ok"
    assert r["B_network_blocked"] is True
    assert r["C_root_read_only"] is True
    assert r["D_no_env_secrets"] == "[]"
    assert r["E_effective_capabilities"] == "0000000000000000"
    assert r["F_infinite_loop_killed"] is True
    assert r["G_harness_blocks_socket_import"] is True


@needs_docker
@pytest.mark.docker
def test_windows_streamed_one_at_a_time_and_results_ordered():
    from hedgeproof.sandbox import known_answer_window

    w = known_answer_window()
    job = SB.run_job(VETTED_SOURCES["ols"], {}, [("2017-02", w), ("2017-03", w[1:] + w[:1])])
    assert job["loaded"] and set(job["replies"]) == {"2017-02", "2017-03"}
    assert all(rep["ok"] for rep in job["replies"].values())


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script as a stand-in docker binary")
def test_unavailable_reason_distinguishes_stopped_docker_from_missing_image(tmp_path):
    def fake_docker(stderr: str) -> str:
        p = tmp_path / f"docker-{abs(hash(stderr))}"
        p.write_text(f"#!/bin/sh\necho '{stderr}' >&2\nexit 1\n")
        p.chmod(0o755)
        return str(p)

    stopped = DockerSandbox(docker=fake_docker("Cannot connect to the Docker daemon. Is the docker daemon running?"))
    ok, detail = stopped.available()
    assert not ok and detail.startswith("Docker is not reachable (start Docker Desktop)")
    missing = DockerSandbox(docker=fake_docker("Error: No such image: hedgeproof-sandbox:1"))
    ok, detail = missing.available()
    assert not ok and "not built" in detail

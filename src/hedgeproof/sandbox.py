"""Host-side sandbox runner for generated estimator code. Owner: Kruthik.

Generated code never runs in the host process. It runs in a fresh Docker
container with no network, a read-only root filesystem, a non-root user, all
capabilities dropped, no new privileges, and CPU, memory and process limits.
No volumes, no Docker socket and no environment variables are passed, so the
container holds no secrets. Windows are streamed one per line.

Static checks below are a supplementary filter, not the isolation.
"""

from __future__ import annotations

import ast
import json
import queue
import re
import secrets
import subprocess
import threading
import time
from typing import Any

import numpy as np

from hedgeproof.records import VerificationReport, sha256_hex

IMAGE = "hedgeproof-sandbox:1"
FLAGS = [
    "--rm", "-i",
    "--network", "none",
    "--read-only",
    "--tmpfs", "/tmp:rw,size=16m",
    "--memory", "256m", "--memory-swap", "256m",
    "--cpus", "1",
    "--pids-limit", "64",
    "--user", "65534:65534",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
]
WINDOW_TIMEOUT_S = 5.0
JOB_TIMEOUT_S = 120.0
MAX_REPLY_CHARS = 10_000
ALLOWED_IMPORTS = {"math", "statistics", "numpy"}
FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "importlib", "open", "eval", "exec", "compile", "__import__", "globals",
    "locals", "vars", "getattr", "setattr", "delattr", "input", "breakpoint", "help", "memoryview", "builtins",
    "shutil", "pathlib", "urllib", "http", "requests", "ctypes", "pickle", "marshal",
}
FUTURE_YEAR = re.compile(r"(?<!\d)20(1[89]|[2-9]\d)(?!\d)")


class SandboxError(RuntimeError):
    pass


# --- Static checks (supplementary) -------------------------------------------


def static_checks(source: str, max_bytes: int = 8192) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    size = len(source.encode("utf-8"))
    add("size_limit", size <= max_bytes, f"{size} bytes (limit {max_bytes})")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        add("parses", False, f"syntax error: {e.msg} (line {e.lineno})")
        return checks
    add("parses", True, "valid Python syntax")
    bad_imports, bad_names, dunders, years = [], [], [], []
    has_estimate = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad_imports += [a.name for a in node.names if a.name.split(".")[0] not in ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                bad_imports.append(node.module or ".")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            bad_names.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            dunders.append(node.attr)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str) and FUTURE_YEAR.search(node.value):
                years.append(node.value[:30])
            elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and 2018 <= node.value < 2100 and float(node.value).is_integer():
                years.append(str(node.value))
        elif isinstance(node, ast.FunctionDef) and node.name == "estimate":
            has_estimate = len(node.args.args) == 2
    add("allowed_imports", not bad_imports, f"disallowed imports: {bad_imports}" if bad_imports else "only math, statistics, numpy")
    add("forbidden_names", not bad_names, f"forbidden names: {sorted(set(bad_names))}" if bad_names else "none")
    add("no_dunder_attributes", not dunders, f"dunder attributes: {sorted(set(dunders))}" if dunders else "none")
    add("no_future_dates", not years, f"date-like literals from 2018 on: {years[:5]}" if years else "none")
    add("estimate_signature", has_estimate, "defines estimate(window, config)" if has_estimate else "must define estimate(window, config)")
    return checks


# --- Synthetic verification windows (trusted, deterministic) -----------------


def known_answer_window(n: int = 36, beta: float = 0.9, seed: int = 11) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    df = rng.normal(0.0, 0.2, n)
    ds = beta * df + rng.normal(0.0, 0.01, n)
    return [{"hedge_month": f"T{i:03d}", "entry_date": "", "exit_date": "", "S_budget": 2.0, "S_exit": 2.0 + float(ds[i]),
             "F_entry": 2.0, "F_exit": 2.0 + float(df[i]), "dS": float(ds[i]), "dF": float(df[i])} for i in range(n)]


def zero_variance_window(n: int = 36) -> list[dict[str, Any]]:
    rng = np.random.default_rng(3)
    ds = rng.normal(0.0, 0.1, n)
    return [{"hedge_month": f"Z{i:03d}", "entry_date": "", "exit_date": "", "S_budget": 2.0, "S_exit": 2.0 + float(ds[i]),
             "F_entry": 2.0, "F_exit": 2.1, "dS": float(ds[i]), "dF": 0.1} for i in range(n)]


# --- Docker runner -----------------------------------------------------------


class DockerSandbox:
    def __init__(self, image: str = IMAGE, docker: str = "docker"):
        self.image, self.docker = image, docker
        self._avail: tuple[float, bool, str] | None = None

    def command(self, name: str, entrypoint: list[str] | None = None) -> list[str]:
        cmd = [self.docker, "run", "--name", name, *FLAGS]
        if entrypoint:
            cmd += ["--entrypoint", entrypoint[0], self.image, *entrypoint[1:]]
        else:
            cmd.append(self.image)
        return cmd

    def available(self) -> tuple[bool, str]:
        now = time.monotonic()
        if self._avail and now - self._avail[0] < 30:
            return self._avail[1], self._avail[2]
        try:
            r = subprocess.run([self.docker, "image", "inspect", self.image], capture_output=True, text=True, timeout=15)
            ok = r.returncode == 0
            detail = "Docker sandbox ready" if ok else f"image {self.image} not built (run: uv run hedgeproof sandbox-build)"
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, detail = False, f"Docker unavailable: {type(e).__name__}"
        self._avail = (now, ok, detail)
        return ok, detail

    def _kill(self, name: str) -> None:
        subprocess.run([self.docker, "kill", name], capture_output=True, timeout=20)

    def run_job(self, source: str, config: dict[str, Any], windows: list[tuple[str, list[dict[str, Any]]]]) -> dict[str, Any]:
        """Stream windows one at a time; return per-window results. Kills the container on timeout."""
        name = f"hp-sbx-{secrets.token_hex(6)}"
        t0 = time.monotonic()
        proc = subprocess.Popen(self.command(name), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", bufsize=1)
        lines: queue.Queue = queue.Queue()

        def reader() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line[: MAX_REPLY_CHARS + 1])
            lines.put(None)

        threading.Thread(target=reader, daemon=True).start()

        def ask(obj: dict[str, Any], timeout: float) -> dict[str, Any]:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(obj, allow_nan=False) + "\n")
            proc.stdin.flush()
            remaining = min(timeout, JOB_TIMEOUT_S - (time.monotonic() - t0))
            try:
                line = lines.get(timeout=max(remaining, 0.1))
            except queue.Empty:
                raise SandboxError("timeout") from None
            if line is None:
                raise SandboxError("container exited")
            if len(line) > MAX_REPLY_CHARS:
                raise SandboxError("reply too long")
            return json.loads(line)

        results: dict[str, Any] = {"loaded": False, "replies": {}, "error": None, "timed_out": False}
        try:
            first = ask({"source": source, "config": config}, 30.0)  # container start + numpy import
            results["loaded"] = bool(first.get("ok"))
            if not first.get("ok"):
                results["error"] = first.get("error", "load failed")
                return results
            for wid, win in windows:
                rep = ask({"id": wid, "window": win}, WINDOW_TIMEOUT_S)
                results["replies"][wid] = rep
        except SandboxError as e:
            results["error"] = str(e)
            results["timed_out"] = str(e) == "timeout"
            self._kill(name)
        except (BrokenPipeError, OSError, ValueError) as e:
            results["error"] = f"protocol error: {type(e).__name__}"
            self._kill(name)
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._kill(name)
                proc.kill()
            results["runtime_seconds"] = round(time.monotonic() - t0, 3)
            results["exit_code"] = proc.returncode
            if proc.stderr:
                results["stderr_tail"] = proc.stderr.read()[-500:]
        return results

    def probe(self, code: str, timeout: float = 60.0) -> dict[str, Any]:
        """Run a probe script with exactly the runner's flags (to verify isolation itself)."""
        name = f"hp-probe-{secrets.token_hex(6)}"
        try:
            r = subprocess.run(self.command(name, ["python", "-c", code]), capture_output=True, text=True, timeout=timeout)
            return {"exit_code": r.returncode, "stdout": r.stdout[-500:], "stderr": r.stderr[-300:]}
        except subprocess.TimeoutExpired:
            self._kill(name)
            return {"exit_code": None, "stdout": "", "stderr": "timeout (killed)"}

    # --- trusted-facing API used by the trusted core ---------------------------

    def verify(self, cand: dict[str, Any]) -> VerificationReport:
        source = cand["source"]
        checks = static_checks(source)
        tests: list[dict[str, Any]] = []
        runtime = 0.0
        if all(c["passed"] for c in checks):
            ka = known_answer_window()
            job = self.run_job(source, cand.get("params") or {}, [("known_answer", ka), ("zero_variance", zero_variance_window()), ("determinism", ka)])
            runtime = job.get("runtime_seconds", 0.0)
            rep = job["replies"]
            if not job["loaded"]:
                tests.append({"name": "loads", "passed": False, "detail": str(job["error"])[:300]})
            else:
                k = rep.get("known_answer", {})
                ok_k = k.get("ok") and abs(k["estimate"] - 0.9) <= 0.05
                tests.append({"name": "known_answer", "passed": bool(ok_k),
                              "detail": f"dS = 0.9 dF + noise gave {k.get('estimate', k.get('error'))}; required 0.9 ± 0.05"})
                z = rep.get("zero_variance", {})
                tests.append({"name": "zero_variance_errors", "passed": z.get("ok") is False,
                              "detail": "raised an error as required" if z.get("ok") is False else f"returned {z.get('estimate')} instead of an error"})
                d = rep.get("determinism", {})
                tests.append({"name": "deterministic", "passed": bool(k.get("ok") and d.get("ok") and d["estimate"] == k["estimate"]),
                              "detail": "same input gave the same output" if d.get("estimate") == k.get("estimate") else "outputs differ"})
                tests.append({"name": "finite_within_time", "passed": not job["timed_out"] and job["error"] is None,
                              "detail": f"runtime {runtime}s" + (f"; error {job['error']}" if job["error"] else "")})
        else:
            tests.append({"name": "static_checks", "passed": False, "detail": "not run in the sandbox because static checks failed"})
        passed = all(c["passed"] for c in checks) and bool(tests) and all(t["passed"] for t in tests)
        return VerificationReport(candidate_id=cand["id"], source_sha256=sha256_hex(source.encode("utf-8")), static_checks=checks,
                                  tests=tests, runner="docker", sandbox_image=self.image, sandbox_flags=FLAGS,
                                  runtime_seconds=runtime, passed=passed).seal()

    def estimates(self, cand: dict[str, Any], windows: dict[str, list[dict[str, Any]]]) -> dict[str, float]:
        from hedgeproof.trusted.core import TrustedError

        ok, detail = self.available()
        if not ok:
            raise TrustedError("SANDBOX_UNAVAILABLE", f"Reduced autonomy: generated code disabled ({detail}).", 503)
        ordered = sorted(windows.items())  # chronological: earlier decisions first
        job = self.run_job(cand["source"], cand.get("params") or {}, ordered)
        if job["error"] or not job["loaded"]:
            raise TrustedError("SANDBOX_JOB_FAILED", f"estimator job failed: {job['error']}", 409)
        out = {}
        for hm, rep in job["replies"].items():
            if not rep.get("ok"):
                raise TrustedError("ESTIMATOR_ERROR", f"estimator failed for {hm}: {rep.get('error')}", 409)
            out[hm] = float(rep["estimate"])
        return out


def self_check(sb: DockerSandbox) -> dict[str, Any]:
    """K1 acceptance: isolation verified through the runner's own command line."""
    ok, detail = sb.available()
    if not ok:
        return {"available": False, "detail": detail}
    probes = {
        "A_user_and_tmp": sb.probe("import os; open('/tmp/t','w').write('x'); print('uid', os.getuid(), 'tmp write ok')"),
        "B_network_blocked": sb.probe("import urllib.request as u; u.urlopen('https://pypi.org', timeout=3)"),
        "C_root_read_only": sb.probe("open('/opt/t','w')"),
        "D_no_env_secrets": sb.probe("import os; print(sorted(k for k in os.environ if k.startswith(('ANTHROPIC', 'HEDGEPROOF', 'AWS', 'GITHUB')) or 'TOKEN' in k or 'SECRET' in k))"),
        "E_no_capabilities": sb.probe("print(open('/proc/self/status').read().split('CapEff:')[1].split()[0])"),
    }
    loop = sb.run_job("def estimate(window, config):\n    while True:\n        pass\n", {}, [("w1", known_answer_window())])
    escape = sb.run_job("def estimate(window, config):\n    import socket\n    return 0.9\n", {}, [("w1", known_answer_window())])
    return {
        "available": True,
        "flags": FLAGS,
        "A_user_and_tmp": probes["A_user_and_tmp"]["stdout"].strip(),
        "B_network_blocked": probes["B_network_blocked"]["exit_code"] != 0 and "URLError" in probes["B_network_blocked"]["stderr"],
        "C_root_read_only": probes["C_root_read_only"]["exit_code"] != 0 and "Read-only file system" in probes["C_root_read_only"]["stderr"],
        "D_no_env_secrets": probes["D_no_env_secrets"]["stdout"].strip(),
        "E_effective_capabilities": probes["E_no_capabilities"]["stdout"].strip(),
        "F_infinite_loop_killed": loop["timed_out"],
        "F_runtime_seconds": loop.get("runtime_seconds"),
        "G_harness_blocks_socket_import": escape["replies"].get("w1", {}).get("ok") is False,
        "G_detail": escape["replies"].get("w1", {}).get("error"),
    }

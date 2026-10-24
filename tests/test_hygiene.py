"""Invariant 9: repository hygiene. No tracked file may look like an env or secret file."""

from __future__ import annotations

import re
import subprocess

from hedgeproof.config import REPO_ROOT

ENV_LIKE = re.compile(r"(^|/)(\.env(\..*)?|.*\.env|\.envrc|secrets\.toml)$", re.IGNORECASE)
KEY_LIKE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|sk-or-v1-[A-Za-z0-9]{20,}")


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def test_no_env_files_tracked():
    bad = [f for f in _tracked_files() if ENV_LIKE.search(f)]
    assert bad == [], f"env-like files are tracked: {bad}"


def test_no_api_keys_in_tracked_text_files():
    hits = []
    for f in _tracked_files():
        path = REPO_ROOT / f
        if path.suffix.lower() in {".xls", ".pdf", ".png", ".lock"} or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if KEY_LIKE.search(text):
            hits.append(f)
    assert hits == [], f"possible API keys in: {hits}"


def test_temporary_directory_cleanup_errors_are_not_suppressed():
    """Database handles must be closed, not hidden: no ignore_cleanup_errors anywhere."""
    hits = []
    for f in _tracked_files():
        if f.endswith(".py") and f != "tests/test_hygiene.py":
            if "ignore_cleanup_errors" in (REPO_ROOT / f).read_text(encoding="utf-8"):
                hits.append(f)
    assert hits == [], f"cleanup errors suppressed in: {hits}"


def test_public_deployment_does_not_publish_an_operator_code_or_open_chat():
    """The Vercel scaffold must not ship a known operator code, and chat must be opt-in."""
    import json

    vercel = json.loads((REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert "HEDGEPROOF_OPERATOR_CODE" not in json.dumps(vercel)
    api = (REPO_ROOT / "api" / "index.py").read_text(encoding="utf-8")
    assert "DEMO01" not in api
    assert 'os.environ.get("HEDGEPROOF_PUBLIC_CHAT") == "1"' in api
    assert '(body or {}).get("model")' not in api  # callers cannot choose the model

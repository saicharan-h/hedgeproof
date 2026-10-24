"""Invariant 9: repository hygiene. No tracked file may look like an env or secret file."""

from __future__ import annotations

import re
import subprocess

from hedgeproof.config import REPO_ROOT

ENV_LIKE = re.compile(r"(^|/)(\.env(\..*)?|.*\.env|\.envrc|secrets\.toml)$", re.IGNORECASE)
KEY_LIKE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")


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

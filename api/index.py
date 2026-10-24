"""Vercel serverless entrypoint for HedgeProof.

Vercel's Python runtime imports this module and exposes ``app`` (an ASGI
application). We build a trusted core on SYNTHETIC data so the deployment
works without raw data files or a database. State is ephemeral on Vercel
(serverless); for persistent state, wire an external Postgres (Phase 2).

Safe by default (this is a public URL):
  * The operator code is never published. Without a HEDGEPROOF_OPERATOR_CODE
    secret, each cold start uses a random code nobody knows, so the
    human-only routes (approvals, holdout opening, fault injection) are inert.
  * POST /chat is OFF unless HEDGEPROOF_PUBLIC_CHAT=1. A public chat endpoint
    spends the team's OpenRouter credit with no spend controller (serverless
    has no durable ledger), so when enabled the server fixes the model, caps
    the input and output size, and never echoes internal errors.

Endpoints:
  GET  /health, /policy, /splits, /artifacts, ...  (trusted service, SYNTHETIC data)
  POST /chat   - OpenRouter-backed explainer chat (disabled by default)

See docs/VERCEL_DEPLOYMENT.md.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import Request
from fastapi.responses import JSONResponse

from hedgeproof.cli import build_core
from hedgeproof.trusted.service import create_app

operator_code = os.environ.get("HEDGEPROOF_OPERATOR_CODE") or secrets.token_hex(8).upper()
scenario = os.environ.get("HEDGEPROOF_SCENARIO", "us")
CHAT_ENABLED = os.environ.get("HEDGEPROOF_PUBLIC_CHAT") == "1"
CHAT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-5.5")
MAX_MESSAGE_CHARS = 2000

core = build_core("test", synthetic=True, scenario=scenario, operator_code=operator_code)
app = create_app(core)


@app.post("/chat")
async def chat(request: Request):
    """OpenRouter-backed explainer chat. Body: {"message": str}. Disabled unless HEDGEPROOF_PUBLIC_CHAT=1.

    Keeps the API key server-side. The model is fixed by the server (any "model"
    field in the request is ignored). Returns {"reply": str}.
    """
    if not CHAT_ENABLED:
        return JSONResponse({"error": "chat is disabled on this deployment"}, status_code=403)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "chat is not configured"}, status_code=503)
    body = await request.json()
    message = str((body or {}).get("message", ""))[:MAX_MESSAGE_CHARS]
    if not message.strip():
        return JSONResponse({"error": "empty message"}, status_code=400)
    try:
        import openai

        client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", max_retries=0, timeout=30)
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are HedgeProof's research assistant. Help the user understand fuel-hedge research, the Mandate-Bound Evidence Gate, and the Indian/U.S. scenarios. Be concise and honest about limitations. You cannot approve orders or change policy."},
                {"role": "user", "content": message},
            ],
            max_tokens=300,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return {"reply": reply, "model": CHAT_MODEL}
    except Exception:  # noqa: BLE001 - never echo internal errors to a public caller
        return JSONResponse({"error": "chat request failed"}, status_code=502)


# (The five-role agent workflow is local-only; see CLI: `hedgeproof run`.)

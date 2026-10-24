"""Vercel serverless entrypoint for HedgeProof.

Vercel's Python runtime imports this module and exposes ``app`` (an ASGI
application). We build a trusted core on SYNTHETIC data so the deployment
works without raw data files or a database. State is ephemeral on Vercel
(serverless); for persistent state, wire an external Postgres (Phase 2).

Agentic AI endpoints:
  GET  /health, /policy, /splits, /artifacts, ...  (trusted service)
  POST /chat   - OpenRouter-backed chat (agentic AI entry point)
  POST /run    - run a TEST (scripted) agent workflow and return decisions

See docs/VERCEL_DEPLOYMENT.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedgeproof.agents.llm import OpenRouterClient
from hedgeproof.cli import build_core
from hedgeproof.trusted.service import create_app
from fastapi import Request
from fastapi.responses import JSONResponse

operator_code = os.environ.get("HEDGEPROOF_OPERATOR_CODE", "DEMO01")
scenario = os.environ.get("HEDGEPROOF_SCENARIO", "us")

core = build_core("test", synthetic=True, scenario=scenario, operator_code=operator_code)
app = create_app(core)


@app.post("/chat")
async def chat(request: Request):
    """OpenRouter-backed chat. Body: {"message": str, "model": str?}.

    Keeps the API key server-side. Returns {"reply": str}.
    """
    body = await request.json()
    message = (body or {}).get("message", "")
    model = (body or {}).get("model") or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "OPENROUTER_API_KEY not configured"}, status_code=503)
    try:
        import openai

        client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are HedgeProof's research assistant. Help the user understand fuel-hedge research, the Mandate-Bound Evidence Gate, and the Indian/U.S. scenarios. Be concise and honest about limitations."},
                {"role": "user", "content": message},
            ],
            max_tokens=512,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return {"reply": reply, "model": model}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


# (Scripted workflow runner is a local-only feature; see CLI: `hedgeproof run`.)
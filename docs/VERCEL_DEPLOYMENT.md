# Vercel deployment

This document explains how to deploy HedgeProof to Vercel and what works there.

## What runs on Vercel

* `api/index.py` — a FastAPI app (trusted service) running as a serverless
  function. Exposes `/health`, `/policy`, `/splits`, `/artifacts`, `/chat`, etc.
* `public/index.html` — the landing page (static). Calls `/api/*` and the chat
  endpoint.
* The core runs on SYNTHETIC data on Vercel (no raw data files needed), so the
  deployment works out of the box.

## What does NOT run on Vercel (and why)

* **Docker sandbox** — Vercel has no Docker. Generated-code execution is a
  local-only feature. The sandboxed verification path (F2, V6) is skipped on
  Vercel, as it is in environments without Docker.
* **Operator code TTY** — there is no console. A demo code is read from
  `HEDGEPROOF_OPERATOR_CODE` (default `DEMO01`).
* **Persistent state** — serverless functions are stateless; SQLite does not
  persist across invocations. State resets per cold start. Persistent state
  (Postgres/Neon) is Phase 2.
* **Streamlit dashboard** — Streamlit needs a long-lived process. The Vercel
  deployment uses the static landing page plus the API instead.

## Environment variables (set in the Vercel dashboard)

| Name | Required | Example |
|---|---|---|
| `OPENROUTER_API_KEY` | for chat | `sk-or-...` |
| `OPENROUTER_MODEL` | optional | `anthropic/claude-sonnet-4` |
| `HEDGEPROOF_SCENARIO` | optional | `us` or `india` |
| `HEDGEPROOF_OPERATOR_CODE` | optional | `DEMO01` |

## Deploy steps

1. Push the repository to GitHub.
2. Import the repository in Vercel (Framework Preset: Other).
3. Set the environment variables above.
4. Deploy. Vercel detects `api/index.py` and `public/`.

## Local preview

```powershell
uv run uvicorn api.index:app --reload --port 8000
```

Then open http://127.0.0.1:8000/.

## Agentic AI on Vercel

The chat endpoint (`POST /api/chat`) keeps the OpenRouter API key server-side
and returns a reply. The 5 agent roles (research, coder, critique, risk,
execution) remain a local feature via the CLI (`uv run hedgeproof run ...`); on
Vercel only the chat surface is exposed, to keep the deployment small.

## Phase 2 (not yet implemented)

* Persistent store on Postgres (Neon) — requires migrating the raw SQL in
  `trusted/core.py` from SQLite placeholders to Postgres.
* Operator-code flow replaced by a real auth (Vercel/NextAuth or a simple
  password).
* Optional: a Next.js frontend replacing `public/index.html`.
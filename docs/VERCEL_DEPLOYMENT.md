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
* **Operator code TTY** — there is no console. The code is never published:
  set `HEDGEPROOF_OPERATOR_CODE` as a Vercel secret only if you need human-only
  actions on the deployment; otherwise each cold start uses a random code that
  nobody knows, so approvals, the holdout opening and fault injection are inert
  on the public URL (the deployment is a read-only showcase).
* **Persistent state** — serverless functions are stateless; SQLite does not
  persist across invocations. State resets per cold start. Persistent state
  (Postgres/Neon) is Phase 2.
* **Streamlit dashboard** — Streamlit needs a long-lived process. The Vercel
  deployment uses the static landing page plus the API instead.

## Environment variables (set in the Vercel dashboard)

| Name | Required | Example (dummy) |
|---|---|---|
| `HEDGEPROOF_SCENARIO` | optional | `us` or `india` |
| `HEDGEPROOF_PUBLIC_CHAT` | optional; chat is OFF unless `1` | `1` |
| `OPENROUTER_API_KEY` | only if chat is enabled | `sk-or-...` (Vercel secret; never in the repo) |
| `OPENROUTER_MODEL` | optional; fixed by the server | `anthropic/claude-haiku-5.5` |
| `HEDGEPROOF_OPERATOR_CODE` | optional; keep unset for a public demo | random secret, never `DEMO01` |

## Security on a public URL

* A public chat endpoint spends the team's OpenRouter credit, and serverless
  functions have no durable spend ledger, so HedgeProof's spend controller
  cannot guard it. Chat is therefore off by default. If you enable it, use an
  OpenRouter key with its own small credit limit, keep the cheap fixed model,
  and turn it off after the demo.
* The server fixes the model (callers cannot pick an expensive one), caps the
  message at 2,000 characters and the reply at 300 tokens, and never echoes
  internal errors.
* The research agents, the sandbox and the spend controller run only locally
  (`uv run hedgeproof ...`); the Vercel deployment is a showcase on SYNTHETIC data.

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
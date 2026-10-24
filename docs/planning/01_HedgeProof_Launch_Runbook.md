# HedgeProof final round: launch runbook

Signal Syndicate: Saicharan Hariharan, Nikshep Doggalli, Kruthik M, Lohith Gollapelli. JSS Science & Technology University Mysuru. Agentic AI track.

Written Fri 23 Oct 2026, about 11:30 PM IST. **Phase: PREPARATION.** The organizer's opening talk is Sat 24 Oct 2026 at 10:00 AM IST and the hacking start has not been announced. This file holds checks and launch steps only. It contains no project code, and nothing in it should be built before the organizer announces the start.

Companion files in this folder:

- `02_HedgeProof_Interface_Contract.md`: what each workstream builds against (data, formulas, gate rules, records, endpoints, agent tools, the 16 evaluation cases).
- `03_HedgeProof_Plan_Board_Scripts.md`: wall-clock plan, owners, task board, risks, proposal checklist, decision log and checkpoint scripts.

---

## 1. Organizer requirements (quoted) and our assumptions

Quoted from the final-round brief. Later organizer instructions override these.

| Requirement | Source wording |
|---|---|
| Time zone | Asia/Kolkata (IST, UTC+05:30) for every schedule |
| Opening talk | Saturday, 24 October 2026, 10:00 AM IST, followed by the hacking round |
| Checkpoint 1 | 24 October, 4:00 PM IST |
| Checkpoint 2 | 24 October, 10:00 PM IST |
| Participation | Non-NITK team, so participation, checkpoints and judging are online |
| RSVP | "Every team must RSVP through the organizer's Google Form when shared" |
| Repository | "public GitHub repository ... regular, meaningful commits"; "detailed README"; "must not contain any env files" |
| Originality | "The project must be implemented from scratch. We cannot build on an existing project." |

Our assumptions (not organizer facts): hacking starts shortly after the opening talk; final judging around 25 Oct 10:00 AM IST; the submission cutoff is unknown until announced.

**Start rule:** implementation begins only when one of us posts "started" in the thread after the organizer announces the hacking start. The opening talk alone does not count.

---

## 2. Tonight, Fri 23 Oct (about 20 minutes each, then sleep)

Every teammate runs sections 2.1 to 2.3 on their own laptop. Only the API-key holder runs 2.4. Saicharan also does 2.6.

### 2.1 Tool versions

| OS | Command | Expected |
|---|---|---|
| Any | `git --version` | any recent version |
| Any | `docker version` | both Client and Server sections print. If Server is missing, start Docker Desktop (Windows: WSL 2 backend) and retry |
| Any | `uv --version` | `uv 0.x`. If missing, see below |

Install uv only if it is missing (from the uv documentation):

- macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Then run `uv python install 3.12`. Expected: it installs Python 3.12, or reports that it is already installed.

### 2.2 Docker sandbox checks (most important)

First pull the base image tonight: `docker pull python:3.12-slim`. Docker Hub rate-limited us once while testing, so pulling early matters.

Then run the three checks. Each one is a single line. PowerShell and bash accept the same text.

**Check A: the restricted container runs**

```
docker run --rm --network none --read-only --tmpfs "/tmp:rw,size=16m" --memory 256m --cpus 1 --pids-limit 64 --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges python:3.12-slim python -c "import os; print('uid', os.getuid()); open('/tmp/t','w').write('x'); print('tmp write ok')"
```

Expected output:

```
uid 65534
tmp write ok
```

**Check B: the network is blocked (this command should fail)**

```
docker run --rm --network none --read-only --tmpfs "/tmp:rw,size=16m" --memory 256m --cpus 1 --pids-limit 64 --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges python:3.12-slim python -c "import urllib.request as u; u.urlopen('https://pypi.org', timeout=3)"
```

Expected: the last line is `urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name resolution>`. If it prints nothing and exits normally, the network was not blocked. Report that.

**Check C: the root filesystem is read-only (this command should fail)**

```
docker run --rm --network none --read-only --tmpfs "/tmp:rw,size=16m" --memory 256m --cpus 1 --pids-limit 64 --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges python:3.12-slim python -c "open('/opt/t','w')"
```

Expected: the last line is `OSError: [Errno 30] Read-only file system: '/opt/t'`.

Status: all three checks are **VERIFIED in Claude's cloud workspace** (Linux, Docker 29.8.2) on Fri 23 Oct 2026 with exactly the outputs shown. On Sat 24 Oct about 9:10 AM IST, Saicharan reported that all three **PASSED on the Windows 11 demo laptop** (Docker Desktop 29.9.2, WSL 2.5.10.0). That result is reported, not run by Claude. Other teammates' laptops: not reported yet.

### 2.3 GitHub identity

1. Sign in to github.com in the browser and note your GitHub username.
2. Set the name and email that should appear on your commits (any OS):
   - `git config --global user.name "Your Name"`
   - `git config --global user.email "your-github-noreply-or-email"`
3. Optional: `gh auth login` if you use the GitHub CLI.

### 2.4 Claude API smoke test (API-key holder only)

Status on 24 Oct, 9:20 AM IST: **pending**. The Console API balance is $0, so this test cannot pass until credits are added. A $20 purchase is under consideration and not confirmed. If credits are bought, leave auto-reload off.

Never paste the key into chat, a file in the repo, or a command line that your shell will save to history.

Set the key for the current terminal session:

- macOS or Linux: `read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY`, then paste the key and press Enter. Nothing echoes, and the typed value is not saved to shell history.
- Windows: Start menu, then "Edit environment variables for your account", then New. Name: `ANTHROPIC_API_KEY`. Paste the value and click OK. Open a new PowerShell window afterwards. Do not use `setx` with the key in the command, because PowerShell saves commands to a history file.

Then run this one-call check from a scratch folder that is not inside any repository. It costs a fraction of a cent.

```
uv run --no-project --python 3.12 --with "anthropic==2.2.0" python -c "import anthropic; c=anthropic.Anthropic(); r=c.messages.create(model='claude-haiku-5-5', max_tokens=200, messages=[{'role':'user','content':'Reply with one word: ready'}]); print(r.model, r.stop_reason, r.usage.input_tokens, r.usage.output_tokens); print(sorted(m.id for m in c.models.list()))"
```

Expected: one line starting with `claude-haiku-5-5`, then a list of model ids that includes the models your key can use. Report the first word of any error (for example `AuthenticationError`, `PermissionDeniedError`, `RateLimitError`), not the full text if it contains account details.

Notes, VERIFIED tonight against the installed package (anthropic 2.2.0 in a scratch environment, no API call):

- `messages.create` accepts `output_config`, `thinking`, `cache_control`, `tools` and `tool_choice`, and no longer accepts `temperature`.
- The SDK raises typed errors, including `RateLimitError`, `APIStatusError`, `APIConnectionError`, `APITimeoutError`, `AuthenticationError` and `BadRequestError`.
- Per Anthropic's migration guide, SDK 2.x sends API version 2026-10-21, which rejects `temperature`, `top_p` and `top_k`.

### 2.5 Check that the EIA download links open (browser only, no processing)

These pages were checked tonight through a web fetch. EIA is blocked from Claude's workspace, so a teammate's laptop must download the files at hour 0.

| Data | Page |
|---|---|
| Futures, all contracts (XLS) | https://www.eia.gov/dnav/pet/xls/PET_PRI_FUT_S1_D.xls |
| Spot prices, all series (XLS) | https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_D.xls |
| Futures table (shows the 5 Apr 2024 end) | https://www.eia.gov/dnav/pet/pet_pri_fut_s1_d.htm |
| Spot table | https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm |

Tonight, only confirm that each XLS link starts a download. Do not keep or process the file. We download again at hour 0, so the retrieval time is honest.

### 2.6 Logistics (Saicharan)

- RSVP Google Form: fill it as soon as the organizer shares it, then post "RSVP done" in the thread.
- Find where the organizer will announce the hacking start, and where the checkpoint links and the submission form will appear.
- Confirm the presenter for checkpoints and judging (proposed: Saicharan, with handoffs to the module owners).

### 2.7 Send these results to the thread (no secrets)

1. Your OS, and the result of checks A, B and C (copy the last line of each).
2. API holder: "smoke test OK" or the error class name.
3. Your GitHub username.
4. RSVP status.

Then sleep. Target lights out by 12:30 AM and wake at 8:30 AM. The plan depends on four rested people, not on heroics at 4 AM.

### 2.8 Cloud environment for the build (setup only; tonight or before the start)

On claude.ai/code, open the environment selector (the first control under the message box) and choose "New environment".

| Setting | Value |
|---|---|
| Name | `HedgeProof` |
| Network access | Custom |
| "Also include default list of common package managers" | ticked |
| Allowed domains | `www.eia.gov` |
| Environment variables | leave empty |

Then click "Add environment". This lets the build session install packages, use Docker Hub and download EIA data itself. If any of this fails, the Default environment still works, and a teammate uploads the EIA files instead.

---

## 3. Saturday morning, before the start

| Time (IST) | Who | What |
|---|---|---|
| 09:15 to 09:50 | All | Short call. Re-run check A on the demo laptop. Skim sections 1 to 4 of the interface contract (owners, files, formulas, gate rules) |
| 10:00 | All, one note-taker | Opening talk. Record the official start time, submission deadline, judging format and time, checkpoint links and format, and the submission requirements. Post them in the thread immediately |

---

## 4. Hour-0 launch (only after the organizer announces the start)

Times are minutes after the announced start (T0). **Updated 24 Oct, 12:00 AM IST:** the build moves to an ordinary Claude Code cloud session, and the repo starts with a README, as Saicharan asked. The new session guides each click one step at a time.

| When | Owner | Step | Done when |
|---|---|---|---|
| T0+0 to 10 | Saicharan | On github.com, create a new repository: owner `saicharan-h`, name `hedgeproof` (or the confirmed name), **Public**, with "Add a README file" ticked and the ".gitignore" template set to **Python**. Then invite Nikshep, Kruthik and Lohith as collaborators | The repo page shows README.md and .gitignore |
| T0+10 to 15 | Saicharan | On the repo page, upload the `docs` folder from the handoff package (it holds `docs/planning/` with HANDOFF.md, files 01 to 04 and Submission.pdf) | `docs/planning/` is visible on GitHub |
| T0+15 to 20 | Saicharan | Open claude.ai/code. Click the repository selector below the message box and choose `hedgeproof`. In the first control under the message box, pick the HedgeProof environment (section 2.8). Paste the start message from HANDOFF.md and press Enter | The new session replies and starts work |
| T0+20 to 40 | New session | First commit: the extra ignore rules below, then `docs/BUILD_STATE.md`, the dependency specification and lock, and the frozen configuration (policy, experiment, agency fixture) with SHA-256 hashes recorded | First push visible on GitHub |
| T0+5 to 30 | Nikshep | Download the two XLS files in 2.5 in the browser, unmodified, and upload them to the repo. The new session moves them to `data/raw/`, then records their hashes and the retrieval time | The files are in `data/raw/` with hashes in the manifest |
| T0+30 | Everyone | `git clone` the repo, then `uv sync`, then `uv run pytest` (the session gives exact steps) | The first smoke test passes on each laptop |
| T0+30 to 45 | New session, Saicharan reviews | Publish the shared records (the contracts package). After this, only Saicharan approves changes to it | Contracts merged; every slice imports them |
| T0+45 onward | All | Parallel slices per the interface contract, section 2 | Slice acceptance tests in the plan file |

### Extra ignore rules for the first code commit

GitHub's Python template covers most of these. The first commit adds whatever is missing:

- Env and secret files: `.env`, `.env.*`, `*.env`, `.envrc`, `.streamlit/secrets.toml`
- Environments and caches: `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`
- Local state: `var/` (SQLite databases, logs, sandbox scratch), `*.db`, `*.sqlite`, `*.sqlite3`, `*.db-journal`, `*.db-wal`, `*.db-shm`, `*.log`
- OS and editor files: `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`

Committed on purpose: the raw EIA files (public domain, with attribution), small fixtures, measured result files and the evidence-packet export.

### Repository rules (from the brief)

- No env files of any kind, including `.env.example` and `.env.sample`. The README lists variable names with dummy values instead: `ANTHROPIC_API_KEY` (required only for live agent runs) and `HEDGEPROOF_MODEL` (optional model override).
- A test fails if any tracked filename looks like an env file. Before each checkpoint, also run `git ls-files` and look for `.env` or secret-like names by eye.
- If a key is ever committed, revoke it in the Claude Console first, then remove it from history. Deleting the file in a new commit is not enough.
- Commits must be real increments: no empty commits, no backdating, no history rewriting. Each person commits their own work under their own name. Claude's commits carry the author `Claude <noreply@anthropic.com>`, so the history shows plainly which work was AI-assisted.

---

## 5. Who runs what where

- **The ordinary Claude Code cloud session** (paid from the Claude Code credits) writes the code, runs the tests and pushes to GitHub.
- **The Windows 11 demo laptop** runs the trusted service, the dashboard and the live agent runs.
- **The app's own Claude API calls** use a separate API key and balance, set only in the laptop's environment. Balance checked on 24 Oct: $0. HANDOFF.md section 2 has the bounded budget plan.

---

## 6. Online checkpoint setup

- One presenter (proposed: Saicharan) with spoken handoffs to Nikshep (data and quant), Kruthik (agents and sandbox) and Lohith (gate, simulator and dashboard).
- Zoom the browser and terminal to 125 to 150 percent. Close chat apps and notifications. Use a browser profile with no personal tabs. Never show environment variables.
- Test screen sharing and audio 15 minutes before each checkpoint, on the laptop that will present.

# Manual demo — run each piece yourself

This is the interview walkthrough. **Do not use Docker for this.** Docker is only packaging (see the bottom). Start four host terminals so you can point at each process.

Prerequisite (once):

```bash
# from the capability-forge repo root
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cd frontend && npm install && cd ..
cp -n .env.example .env
# put OPENAI_API_KEY or ANTHROPIC_API_KEY in .env
```

Stop anything leftover: `make stop`

---

## What each process is

| Terminal | Command | Port | Role |
| --- | --- | --- | --- |
| 1 | `temporal server start-dev` | 7233 (UI 8233) | Run state machine + `human_resume` signal |
| 2 | `capability-forge api` | 8787 | Corebank UI + REST + Playwright sessions + Temporal worker |
| 3 | `cd frontend && npm run dev` | 5173 | Admin console |
| 4 | CLI commands | — | Discover / replay / approve / MCP (you type these) |

CLI `discover` / `replay` talk to Corebank on 8787. They do **not** need Temporal. Admin **Start discovery / Replay** and MCP `call_tool` **do**.

---

## Start (in this order)

**Terminal 1 — Temporal**

```bash
source .venv/bin/activate
temporal server start-dev
```

Wait until it prints that the frontend is on `http://localhost:8233`. Leave it running.

**Terminal 2 — API + Corebank + worker**

```bash
source .venv/bin/activate
capability-forge api
```

Wait for `Uvicorn running on http://127.0.0.1:8787`.

**Terminal 3 — Admin UI**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`.

**Sanity (browser or curl)**

- Corebank: `http://127.0.0.1:8787/corebank/`
- Health: `curl -s http://127.0.0.1:8787/api/health` → `"temporal": true` if T1 is up
- Temporal UI: `http://localhost:8233`

---

## Walk the product (Terminal 4)

```bash
source .venv/bin/activate
```

### A. See the target app (no agent)

Browser: search member `12345` → Open file → Record balance inquiry.  
Then search `99999` → “No records found.” That is a business outcome, not a crash.

### B. Replay without an LLM (proves the executor)

Seeded artifact `lookup-member-balance-v1` is already **approved**.

```bash
capability-forge replay --artifact-id lookup-member-balance-v1 --member-id 12345
# expect kind=success, savings_balance, confirmation_id

capability-forge replay --artifact-id lookup-member-balance-v1 --member-id 99999
# expect kind=business_outcome, MEMBER_NOT_FOUND
```

Chromium will open (headed). Evidence lands under `evidence/replay-<id>/`.

### C. Live LLM discovery (the non-negotiable)

Needs an API key in `.env`.

```bash
capability-forge discover --goal "look up member 12345 and read their current savings balance"
```

On success you get a **new draft** `lookup-member-balance-v2`. MCP still serves v1.

Or in the UI: **Runs → Start discovery** (this path uses Temporal).

### D. Approve so MCP flips

UI **Artifacts**: versions under one card, Approve v2.  
Or:

```bash
capability-forge approve lookup-member-balance-v2
```

If the admin tab is open, `/ws/admin` updates the list. If not, set `APPROVAL_WEBHOOK_URL` for Slack/email.

### E. Human handoff

Start a discovery from the UI. When status is `waiting_human`:

1. **Operator** page — live screenshot of the same Chromium.
2. Drive the headed window yourself.
3. **Resume automation** (Temporal `human_resume` signal).

### F. MCP (agent-facing tool)

```bash
capability-forge mcp
```

`list_tools` → one tool named `lookup-member-balance` = **latest approved** version.  
`call_tool` starts a Temporal `ReplayWorkflow` (needs T1 + T2).

### G. Stability (DuckDB)

UI **Stability**. DuckDB only *reads* `evidence/replay-*/result.json`. It does not store logs or traces. Traces are Playwright `trace.zip` on failure.

---

## Stop

```bash
make stop
```

Or Ctrl+C each terminal, then:

```bash
lsof -nP -iTCP:8787,5173,7233,8233 -sTCP:LISTEN
```

---

## Docker (optional — not the live demo)

Same three services as containers. Replay is **headless**; do not use this for operator handoff.

```bash
docker compose up --build
# http://localhost:5173  API 8787  Temporal 7233
# later: docker compose up --scale api=2
docker compose down
```

Scaling here means “copy the API/Playwright unit,” not a bank-grade cluster. The brief does not reward building that cluster.

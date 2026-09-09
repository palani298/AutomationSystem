# Capability Forge

A computer-use system for the long tail of bank/credit-union apps that have **no API**.

An LLM does a **discovery run** against a live UI once. The successful run is compiled into a **typed, versioned artifact** (steps, locator strategies, input/output contract, checkpoint, known business outcomes). After that, **replay is deterministic** — no model in the loop. When replay or discovery cannot safely continue, a human takes the **same live Playwright session** and hands it back. Approved artifacts are exposed as **MCP tools** through one generic reflection layer.

This is a capability-creation system, not a QA tool.

## Demo (the required path)

**Interview walkthrough (run each process yourself):** see [`DEMO.md`](DEMO.md). That file is the step list: start order, what to type, what to click, how to stop.

You need three terminals after install. Temporal is the orchestrator for UI-triggered runs; the CLI can also run discovery/replay in-process.

```bash
# 0. once
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cd frontend && npm install && cd ..
cp .env.example .env   # add OPENAI_API_KEY (or ANTHROPIC_API_KEY)

# 1. Temporal
temporal server start-dev

# 2. API (serves Corebank + control plane + in-process worker)
capability-forge api

# 3. Admin UI
cd frontend && npm run dev
```

Open `http://127.0.0.1:5173`. Corebank (the hostile proxy app) is at `http://127.0.0.1:8787/corebank/`.

### Discovery, then replay

```bash
# Live LLM discovery — this is the non-negotiable run
capability-forge discover --goal "look up member 12345 and read their current savings balance"

# Deterministic replay of the latest artifact (no LLM)
capability-forge replay --latest --member-id 12345

# Expected business outcome, not a crash
capability-forge replay --latest --member-id 99999
```

Or from the React admin: **Runs → Start discovery**, then **Artifacts → Replay**. Use **Operator** when a run is `waiting_human`: drive the headed Chromium window, then **Resume automation**.

The seeded reference artifact `lookup-member-balance-v1` is already `approved`, so replay and MCP work before the first discovery. A later discovery of the same flow is saved as `lookup-member-balance-v2` in **draft**; approve it in the Artifacts page (or `capability-forge approve lookup-member-balance-v2`) and MCP flips to v2.

### MCP

```bash
capability-forge approve lookup-member-balance-v1   # already approved
capability-forge mcp
```

`list_tools` returns one tool per **slug**, bound to the latest approved version. `call_tool("lookup-member-balance", {member_id})` starts a Temporal `ReplayWorkflow` of that live version. Drafts never appear.

Set `APPROVAL_WEBHOOK_URL` to ping Slack/email when a draft needs review and when a version becomes MCP-live. If the admin console is already open, `/ws/admin` pushes the same event into the page (connects on load, closes with the tab).

## Layout

| Path | Role |
| --- | --- |
| `src/capability_forge/schemas/artifact.py` | Artifact / locator / checkpoint contract |
| `src/capability_forge/discovery/` | LLM observe → decide → act |
| `src/capability_forge/replay/` | Deterministic executor + outcome taxonomy |
| `src/capability_forge/target_app/` | Legacy-style Corebank (iframe, no test IDs) |
| `src/capability_forge/temporal/` | Discovery/Replay workflows, human-resume signal |
| `src/capability_forge/mcp/` | Dynamic tools over the registry |
| `src/capability_forge/analytics/` | DuckDB over evidence JSON |
| `frontend/` | Runs, artifacts, operator console, stability |
| `evidence/` | Discovery + replay logs (gitignored payloads) |
| `REPORT.md` | Design write-up (required headings) |

## Config

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Required for a live discovery run |
| `LLM_PROVIDER` | `openai` (default) or `anthropic` |
| `PLAYWRIGHT_HEADLESS` | `false` so a human can take the live window |
| `ALLOWLIST_HOSTS` | Default `127.0.0.1,localhost` |
| `TEMPORAL_ADDRESS` | Default `localhost:7233` |

Without Temporal, CLI `discover` / `replay` still work (they use the engine directly). The admin **Start discovery / Replay** buttons require Temporal.

## Tests

```bash
pytest -q tests/test_safety.py tests/test_artifact.py
pytest -q tests/test_replay_live.py   # needs Chromium; starts Corebank on :8799
```

## Docker (optional)

`Dockerfile` + `docker-compose.yml` package Temporal, the API/Playwright unit, and the admin UI. Use this to show “these processes can be copied,” not for the headed handoff demo.

```bash
docker compose up --build
docker compose down
```

Manual host processes remain the real demo (`DEMO.md`).

# TODO — future improvements

Things we talked through and deliberately left out of the take-home. The core (discover once → versioned draft → approve → MCP latest-approved → deterministic replay → live handoff) stays as-is.

## Local / on-prem model (DGX Spark, OpenClaw)

- Point `LLMClient` at a Spark-hosted computer-use model instead of OpenAI/Anthropic when screenshots and ARIA cannot leave the institution.
- Use OpenClaw (or any local agent) as the **MCP caller** — it decides *what* to invoke; this system still replays without a model.
- Do **not** have a local agent poll until an admin approves. Approval is a human gate on a saved artifact, not a model watching a queue.

## Replay robustness

- One-step, allowlisted LLM fallback when a replay step fails (never open-ended). Record it as evidence.
- Multi-run stability: replay N times, report flakiness. DuckDB already reads `evidence/replay-*/result.json`; wire a real N-run job.
- Canonicalize routes (`/member/12345` → `/member/:id`) so locators stay parameterized.

## Heterogeneity & multi-tenant

- Desktop accessibility adapter (`surface.kind = desktop` is already on the schema).
- Tenant registry + canary replay: run the approved artifact on a second “tenant” variant, treat checkpoint miss as drift.
- Editor for `tenant_overrides` (label/path patches) instead of re-recording per institution.

## Operator & safety

- Bounded cobrowse on the operator console (highlight, lock, who-is-in-control chrome). Handoff mechanism is real; the toolbar is not.
- Field-level redaction / DLP, not only host allowlist + evidence redaction.
- Separate session-host process so a Temporal wait survives API/Playwright restart.

## Packaging

- Headed Playwright in Docker for operator handoff. Compose is headless today; the interview demo stays on the host.
- Optional `docker compose up --scale api=2` as replay workers only — not a multi-tenant cluster.

## Stretch we skipped

- Emit a page-object / test file from an artifact (the artifact *is* the program).
- Compose search-by-name → pick row → fetch details in *this* system. That stays the calling agent’s job.

---

## Already in place (do not rebuild)

- Versioned artifacts (`slug` + `vN`); MCP binds **latest approved**.
- Draft → approve; webhook if admin is offline; `/ws/admin` only while the console tab is open.
- `/ws/runs/{id}` only for live Playwright handoff.
- CLI replay without Temporal; UI/MCP replay through Temporal + `human_resume`.
- Seeded `lookup-member-balance-v1` so replay works without a model API key.
- `DEMO.md` for the manual walkthrough; Docker/Compose as optional packaging.

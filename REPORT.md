# REPORT

## Architecture

Capability Forge is a single Python control plane plus one in-process resource that cannot be serialized: the Playwright browser session.

- **Target surface.** A local Corebank workbench (search → results → member file → inquiry confirmation) stands in for a legacy servicing app. It uses nested tables, an iframe search form, and no test IDs. The same FastAPI process serves this app and the control API so the allowlist can stay on `localhost`.
- **Engine.** Discovery and replay are plain async Python (`DiscoveryAgent`, `ReplayExecutor`) that share `SessionManager`. That is the load-bearing core. CLI runs it directly.
- **Temporal.** UI-triggered runs are `DiscoveryWorkflow` / `ReplayWorkflow`. Activities are the retryable edges (open session, run until pause, persist registry rows). The workflow is the durable state machine: `running → waiting_human → running → succeeded|failed`. `human_resume` is a Temporal signal. We did **not** put queues, clusters, or multi-tenant routing in front of this. Temporal is here because pause/resume and “who is in control” are workflow problems, not because we needed a fleet.
- **Registry vs analytics.** SQLite holds artifacts and run rows (point lookup, status flips). DuckDB is used only to scan evidence JSON for a stability table. Mixing those jobs would be the wrong storage shape.
- **MCP.** One generic `list_tools` / `call_tool` layer. Tool **name is the capability slug** (`lookup-member-balance`), not a versioned row id. `call_tool` resolves the **latest approved version** of that slug. Drafts are invisible to agents. No per-capability hand-written tool.
- **React.** Admin only: start runs, review version history, approve a draft, watch the live session, read DuckDB stability. No automation logic lives in the browser.
- **Notifications.** Two seams. `APPROVAL_WEBHOOK_URL` POSTs when a draft is created or approved so Slack/email can reach an admin who is not in the UI. `/ws/admin` is **session-scoped**: the browser connects when the admin console loads and the socket dies when the tab closes. There is no always-on admin socket. `/ws/runs/{id}` is even tighter — only while the operator page is watching that run.

Trade-off: the Temporal worker runs in the API process so activities and the operator share the same `SessionManager`. If that process dies, the live page dies with it. At institution scale a session host would be a separate pool; we did not build that pool.

## Artifact schema

An artifact is the agent-facing contract, not a transcript.

- **Identity:** `slug` (stable capability name / MCP tool name), `id` (`{slug}-v{n}`), `name`, `description`, `schema_version`, monotonic `version` per slug, `status` (`draft` \| `approved`). A new discovery inserts `vN+1` as `draft`. Approving it makes that version the MCP live tool; older approved versions remain in history but are not what `list_tools` returns.
- **Surface:** `kind` (`web` \| `desktop`), `entry_url`, `vendor_app`, `vendor_version`. Perception/action adapters key off `kind`; the step list does not.
- **Typed I/O:** `inputs` / `outputs` as named params. Replay binds `params.member_id` at invocation. The artifact never stores the live member number, name, or balance.
- **Steps:** ordered actions with an **ordered locator list**. Strategies are `role_name`, `label`, `placeholder`, `text`, `title`, then `css`. `frame_selector` is how we address framesets without baking a DOM path into the flow.
- **Checkpoint:** assertions that must all hold (`url_matches`, `visible_text`, `locator_visible`, `extract_present`). Success is not “the last click did not throw.”
- **Business outcomes:** first-class detectors (`MEMBER_NOT_FOUND`, `ACCOUNT_RESTRICTED`, `PERMISSION_DENIED`). These are results, not exceptions.
- **Tenant overrides:** an empty map reserved for per-institution locator/url patches (see Heterogeneity). Not a second artifact.

We compile this from a successful discovery by recording each acted step and replacing goal-literal values (the member number) with parameter references.

## Determinism & error handling

Replay never asks the model what to do. It loads the artifact + fresh params and walks steps.

**Targeting.** Try locators in order until one is visible. Role+name and label win on Corebank; CSS is last. Iframe steps keep `frame_selector`. Playwright auto-wait plus an explicit timeout is the wait policy.

**Recoverable.** Known interstitials (the “Acknowledge” system notice) are dismissed and the step is retried. This is the only recovery that does not require a human or a model.

**Business outcomes.** After each step, and on action failure, we scan for configured outcome predicates. `member_id=99999` yields `MEMBER_NOT_FOUND` with a structured result. Restricted member `22222` yields `ACCOUNT_RESTRICTED` if that text is on screen.

**Hard failure.** Allowlist miss, missing required params, locator exhaustion, or checkpoint miss. The result names the step, the expected condition, and the observation. Playwright tracing + a screenshot are kept on failure under `/evidence/`.

**UI drift** is secondary (these apps change slowly). Ordered locator fallbacks and vendor/version on the surface are the designed answer; we do not silently LLM-patch a failed step in production replay.

## Heterogeneity & multi-tenant

**Surface seam.** The artifact’s step graph is “do this to a control, then assert.” `Surface.kind` selects an adapter that can resolve a `Locator` and fire `click/fill/extract`. Today the adapter is Playwright for `web`. A desktop adapter would resolve the same `role_name` / `label` locators against the OS accessibility tree (the reason we biased off raw CSS). Screenshots/coordinates would be a third adapter, not a different artifact type.

**Multi-tenant reuse.** Hundreds of institutions run the same vendor product. We model one artifact per **vendor_app + version**, not per tenant. `tenant_overrides` is where a credit union’s branded label (“Member #” vs “CIF”) or a path prefix would live — a patch, not a fork. Drift detection is a replay-budget problem: run the approved artifact on a canary tenant, treat checkpoint/locator failure as “version or config drifted,” and either apply an override or send the flow back to discovery as `draft`. We did not implement a tenant table; the fields are on the schema so the design is not painted into a per-tenant recording corner.

Composition (search-by-name → pick a row → fetch details) is the calling agent’s job. Artifacts stay atomic.

## Escalation & handoff

**Stuck** is explicit: identical page fingerprint four times, model `escalate`, action exception during discovery, max steps, or an irreversible allowlist hit.

**Route.** The run row flips to `waiting_human`. Evidence already has the last screenshot, step, and reason. The operator console subscribes to `/ws/runs/{id}` and shows the live frame plus why it stopped.

**Same session.** `SessionManager` holds the Playwright `Page`. The headed Chromium window *is* the live session; the React panel is the control-transfer UI, not a second browser. The human acts in that window (scope-accurate: we did not build a full cobrowse toolbar).

**Hand back.** Resume sends a Temporal `human_resume` signal and sets `controller=agent`. Discovery continues from the current DOM. Replay, whose first step is usually `navigate`, restarts the artifact on the same browser after resume — acceptable because the artifact is the source of truth, not the operator’s intermediate URL.

**Who is in control.** `LiveSession.controller` is `agent` or `human`. The workflow query `snapshot` exposes the same status. Automation will not click while the flag is `human`.

## Safety

- **Allowlist.** Only configured hosts and an explicit action enum. Navigate off-box is a hard failure.
- **Risk classes.** `safe` / `reversible` / `irreversible`. Paths like `close-account` are irreversible and **require a human** even if the model or artifact asks. We do not auto-confirm them.
- **Redaction.** Applied only when writing evidence/logs. Artifacts store placeholders. Replay never reads redacted files, so redaction cannot break production execution.
- **Limits.** A determined operator can type PII into Corebank; we do not pretend the headed window is a DLP product. The allowlist is host-level, not field-level. Credentials are env-only and never logged.

## Cuts

- No assisted LLM fallback on a failed replay step (stretch). Would be a single bounded, allowlisted retry, recorded as evidence.
- No real cobrowse tools (draw, multi-operator lock). The handoff *mechanism* is real; the chrome is minimal.
- No desktop adapter implementation — schema + REPORT only, per §3.7.
- No tenant registry, canary scheduler, or override editor. `tenant_overrides` is the stub.
- No Temporal Cloud / k8s / queues. A `Dockerfile` + Compose file only packages the same three host processes (Temporal, API, UI) so an API/Playwright unit could be replicated. That is not a multi-tenant cluster.
- Local-model computer-use on DGX Spark was not used. One frontier-API discovery run is the intended evidence.
- Code generation of page objects was skipped; the artifact *is* the reusable program.

Next: see `TODO.md` (local Spark/OpenClaw as discovery client or MCP caller, one-step replay fallback, desktop adapter, tenant canaries, headed Docker handoff).

# TODO

- Headed Playwright in Docker (operator handoff). Compose runs headless; demo stays on the host.
- Cross-tenant canary replays and per-tenant locator overrides.
- Desktop accessibility adapter (schema already has `surface.kind`).
- One-step, allowlisted LLM fallback on a failed replay step.
- Bounded cobrowse tools on the operator console.

Done, kept as the rule: `/ws/admin` is **on while the admin tab is open**, not a daemon. Webhook covers admins who are offline. `/ws/runs/{id}` stays a separate, run-scoped handoff socket.

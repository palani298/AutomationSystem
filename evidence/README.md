Evidence is written here at runtime (`discovery-<run>` / `replay-<run>`). Those folders are gitignored.

`demo/` is the checked-in slice the brief asks for:

- `artifact.json` — the typed capability (locators + params, no live PII)
- `replay-success/` — deterministic replay for member `12345` (outputs redacted on disk)
- `replay-not-found/` — same artifact, member `99999`, classified as `MEMBER_NOT_FOUND`

Replay never reads these files. A live LLM discovery run is produced with:

```bash
capability-forge discover --goal "look up member 12345 and read their current savings balance"
```

after `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is set. That folder will appear next to `demo/`.

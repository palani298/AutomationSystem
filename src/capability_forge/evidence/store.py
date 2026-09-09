from __future__ import annotations

import json
from pathlib import Path

from capability_forge.config import settings
from capability_forge.safety.redact import redact_mapping, redact_text
from capability_forge.schemas.run import RunEvent


class EvidenceWriter:
    def __init__(self, run_id: str, kind: str) -> None:
        self.run_id = run_id
        self.dir = settings.evidence_dir / f"{kind}-{run_id}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "screenshots").mkdir(exist_ok=True)
        self._events = self.dir / "events.jsonl"

    def log(self, event: RunEvent) -> None:
        payload = redact_mapping(event.model_dump())
        with self._events.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def write_json(self, name: str, data: dict) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(redact_mapping(data), indent=2), encoding="utf-8")
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(redact_text(text), encoding="utf-8")
        return path

    async def screenshot(self, page, label: str) -> Path | None:
        try:
            path = self.dir / "screenshots" / f"{label}.png"
            await page.screenshot(path=str(path), full_page=True)
            return path
        except Exception:
            return None

    async def start_tracing(self, context) -> None:
        try:
            await context.tracing.start(screenshots=True, snapshots=True, sources=False)
        except Exception:
            pass

    async def stop_tracing(self, context, *, keep: bool) -> Path | None:
        path = self.dir / "trace.zip"
        try:
            await context.tracing.stop(path=str(path) if keep else None)
            return path if keep and path.exists() else None
        except Exception:
            return None

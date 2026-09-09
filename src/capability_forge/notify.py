"""Approval notifications.

Webhook: POST to APPROVAL_WEBHOOK_URL so Slack/email/ticketing can reach an
admin who does not have this UI open.

WebSocket /ws/admin: push the same event into a console that *is* open.
The browser connects when the admin page loads and drops the socket when
the tab closes. There is no always-on socket with no client — that is not
how WebSockets work, and it would not notify anyone who is offline.

Do not reuse /ws/runs/{id} for this. That socket is the live Playwright
handoff and should only exist while an operator is on that run.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import WebSocket

from capability_forge.config import settings
from capability_forge.registry.db import registry
from capability_forge.schemas.artifact import Artifact

log = logging.getLogger(__name__)


class AdminHub:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._sockets.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = AdminHub()


async def catalog_payload() -> dict[str, Any]:
    return {
        "catalog": await registry.catalog(),
        "pending": [a.model_dump() for a in await registry.pending_drafts()],
    }


async def publish(kind: str, artifact: Artifact) -> None:
    live = await registry.latest_approved(artifact.slug)
    event = {
        "type": kind,
        "artifact": {
            "id": artifact.id,
            "slug": artifact.slug,
            "name": artifact.name,
            "version": artifact.version,
            "status": artifact.status,
        },
        "mcp_tool": artifact.slug,
        "mcp_live_version": live.version if live else None,
        **(await catalog_payload()),
    }
    await hub.broadcast(event)
    await _webhook(event)


async def approval_needed(artifact: Artifact) -> None:
    await publish("approval_needed", artifact)


async def approved(artifact: Artifact) -> None:
    await publish("approved", artifact)


async def _webhook(event: dict[str, Any]) -> None:
    url = settings.approval_webhook_url.strip()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=event)
    except Exception as exc:
        log.warning("approval webhook failed: %s", exc)

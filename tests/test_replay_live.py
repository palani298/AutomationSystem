import asyncio

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from capability_forge.config import settings
from capability_forge.engine import open_session, run_replay
from capability_forge.recording.compile import seed_reference_artifact
from capability_forge.registry.db import registry
from capability_forge.schemas.run import OutcomeKind
from capability_forge.target_app import STATIC as COREBANK_STATIC
from capability_forge.target_app.app import router as corebank_router


def _corebank_only() -> FastAPI:
    app = FastAPI()
    app.include_router(corebank_router)
    app.mount("/corebank/static", StaticFiles(directory=str(COREBANK_STATIC)), name="corebank-static")
    return app


@pytest.fixture
async def corebank(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_dir", tmp_path / "evidence")
    monkeypatch.setattr(settings, "database_path", tmp_path / "registry.sqlite")
    monkeypatch.setattr(settings, "public_base_url", "http://127.0.0.1:8799")
    monkeypatch.setattr(settings, "playwright_headless", True)
    monkeypatch.setattr(settings, "playwright_slow_mo_ms", 0)
    settings.evidence_dir.mkdir(parents=True)
    registry.path = settings.database_path
    await registry.init()

    config = uvicorn.Config(_corebank_only(), host="127.0.0.1", port=8799, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(80):
        if server.started:
            break
        await asyncio.sleep(0.05)
    yield "http://127.0.0.1:8799"
    server.should_exit = True
    await task


@pytest.mark.asyncio
async def test_replay_success_and_member_not_found(corebank):
    artifact = seed_reference_artifact()
    artifact.surface.entry_url = f"{corebank}/corebank/"
    await registry.upsert_artifact(artifact)

    session = await open_session("replay-ok", artifact.surface.entry_url)
    try:
        ok = await run_replay("replay-ok", session.id, artifact.id, {"member_id": "12345"})
    finally:
        from capability_forge.browser.session import sessions

        await sessions.close(session.id)
    assert ok.kind is OutcomeKind.SUCCESS
    assert ok.outputs.get("savings_balance")
    assert ok.outputs.get("confirmation_id", "").startswith("INQ-12345")

    session = await open_session("replay-miss", artifact.surface.entry_url)
    try:
        miss = await run_replay("replay-miss", session.id, artifact.id, {"member_id": "99999"})
    finally:
        from capability_forge.browser.session import sessions

        await sessions.close(session.id)
        await sessions.stop()
    assert miss.kind is OutcomeKind.BUSINESS_OUTCOME
    assert miss.business_code == "MEMBER_NOT_FOUND"

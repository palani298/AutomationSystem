from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from capability_forge.analytics.duck import replay_outcomes, stability_report
from capability_forge.browser.session import sessions
from capability_forge.config import settings
from capability_forge.engine import ensure_ready, new_run
from capability_forge.notify import approved as notify_approved, catalog_payload, hub
from capability_forge.registry.db import registry
from capability_forge.schemas.artifact import Step, StepAction
from capability_forge.schemas.run import RunKind
from capability_forge.target_app import STATIC as COREBANK_STATIC
from capability_forge.target_app.app import router as corebank_router
from capability_forge.temporal.models import DiscoveryInput, ReplayInput
from capability_forge.temporal.runtime import connect_client, start_background_worker
from capability_forge.temporal.workflows import DiscoveryWorkflow, ReplayWorkflow


class DiscoverRequest(BaseModel):
    goal: str
    entry_url: str | None = None


class ReplayRequest(BaseModel):
    artifact_id: str
    params: dict[str, str]
    entry_url: str | None = None


class ApproveRequest(BaseModel):
    status: str = "approved"


class ResumeRequest(BaseModel):
    note: str = ""
    workflow_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_ready()
    app.state.temporal = None
    app.state.worker_task = await start_background_worker()
    if app.state.worker_task:
        try:
            app.state.temporal = await connect_client()
        except Exception:
            app.state.temporal = None
    yield
    if app.state.worker_task:
        app.state.worker_task.cancel()
    await sessions.stop()


app = FastAPI(title="Capability Forge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(corebank_router)
app.mount("/corebank/static", StaticFiles(directory=str(COREBANK_STATIC)), name="corebank-static")


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "temporal": bool(getattr(app.state, "temporal", None)),
        "corebank": settings.corebank_url,
    }


@app.get("/api/artifacts")
async def list_artifacts() -> list[dict]:
    return [a.model_dump() for a in await registry.list_artifacts()]


@app.get("/api/catalog")
async def catalog() -> dict:
    return await catalog_payload()


@app.get("/api/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str) -> dict:
    artifact = await registry.resolve(artifact_id)
    if not artifact:
        raise HTTPException(404, "artifact not found")
    return artifact.model_dump()


@app.post("/api/artifacts/{artifact_id}/status")
async def set_artifact_status(artifact_id: str, body: ApproveRequest) -> dict:
    artifact = await registry.set_status(artifact_id, body.status)
    if not artifact:
        raise HTTPException(404, "artifact not found")
    if body.status == "approved":
        await notify_approved(artifact)
    return artifact.model_dump()


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    return [r.model_dump() for r in await registry.list_runs()]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await registry.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run.model_dump()


@app.get("/api/analytics/stability")
async def stability() -> dict:
    return {"events": stability_report(), "outcomes": replay_outcomes()}


@app.post("/api/discover")
async def start_discover(body: DiscoverRequest) -> dict:
    client = getattr(app.state, "temporal", None)
    if not client:
        raise HTTPException(503, "Temporal is not running. Start it with `temporal server start-dev`.")
    run = new_run(RunKind.DISCOVERY, goal=body.goal)
    await registry.upsert_run(run)
    handle = await client.start_workflow(
        DiscoveryWorkflow.run,
        DiscoveryInput(run_id=run.id, goal=body.goal, entry_url=body.entry_url or settings.corebank_url),
        id=f"discover-{run.id}",
        task_queue=settings.temporal_task_queue,
    )
    run.workflow_id = handle.id
    await registry.upsert_run(run)
    return {"run_id": run.id, "workflow_id": handle.id}


@app.post("/api/replay")
async def start_replay(body: ReplayRequest) -> dict:
    client = getattr(app.state, "temporal", None)
    if not client:
        raise HTTPException(503, "Temporal is not running. Start it with `temporal server start-dev`.")
    artifact = await registry.resolve(body.artifact_id)
    if not artifact:
        raise HTTPException(404, "artifact not found")
    run = new_run(RunKind.REPLAY, artifact_id=artifact.id, params=body.params)
    await registry.upsert_run(run)
    handle = await client.start_workflow(
        ReplayWorkflow.run,
        ReplayInput(
            run_id=run.id,
            artifact_id=artifact.id,
            params=body.params,
            entry_url=body.entry_url or artifact.surface.entry_url,
        ),
        id=f"replay-{run.id}",
        task_queue=settings.temporal_task_queue,
    )
    run.workflow_id = handle.id
    await registry.upsert_run(run)
    return {"run_id": run.id, "workflow_id": handle.id}


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, body: ResumeRequest) -> dict:
    client = getattr(app.state, "temporal", None)
    if not client:
        raise HTTPException(503, "Temporal is not running")
    run = await registry.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    workflow_id = body.workflow_id or run.workflow_id
    if not workflow_id:
        raise HTTPException(400, "no workflow id")
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal("human_resume", body.note)
    session = sessions.get_by_run(run_id)
    if session:
        sessions.set_controller(session.id, "agent")
    return {"ok": True}


@app.get("/api/runs/{run_id}/live")
async def live_state(run_id: str) -> dict:
    session = sessions.get_by_run(run_id)
    if not session:
        raise HTTPException(404, "no live session")
    snap = await sessions.snapshot(session.id)
    png = snap.pop("screenshot_png", b"")
    return {
        **{k: v for k, v in snap.items() if k != "aria"},
        "aria": snap.get("aria", "")[:4000],
        "screenshot": base64.b64encode(png).decode("ascii") if png else "",
        "session_id": session.id,
        "controller": session.controller,
    }


@app.websocket("/ws/admin")
async def admin_socket(websocket: WebSocket) -> None:
    """Lives only while an admin browser tab is open. See notify.AdminHub."""
    await hub.connect(websocket)
    try:
        await websocket.send_json({"type": "catalog", **(await catalog_payload())})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)


@app.websocket("/ws/runs/{run_id}")
async def operator_socket(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            session = sessions.get_by_run(run_id)
            if session:
                snap = await sessions.snapshot(session.id)
                png = snap.pop("screenshot_png", b"")
                await websocket.send_json(
                    {
                        "url": snap.get("url"),
                        "title": snap.get("title"),
                        "controller": session.controller,
                        "stuck_reason": session.stuck_reason,
                        "screenshot": base64.b64encode(png).decode("ascii") if png else "",
                    }
                )
            else:
                await websocket.send_json({"controller": "none", "stuck_reason": "no live session"})
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=1.2)
            except asyncio.TimeoutError:
                continue
            await _handle_operator_message(run_id, message)
    except WebSocketDisconnect:
        return


async def _handle_operator_message(run_id: str, message: dict[str, Any]) -> None:
    action = message.get("action")
    session = sessions.get_by_run(run_id)
    if action == "resume":
        client = getattr(app.state, "temporal", None)
        run = await registry.get_run(run_id)
        if client and run and run.workflow_id:
            handle = client.get_workflow_handle(run.workflow_id)
            await handle.signal("human_resume", message.get("note") or "")
        if session:
            sessions.set_controller(session.id, "agent")
        return
    if not session:
        return
    if action == "click" and message.get("locator"):
        step = Step(id="human", action=StepAction.CLICK, locators=[])
        # Operator clicks the headed Chromium window directly; this path is for named buttons.
        from capability_forge.schemas.artifact import Locator

        step.locators = [Locator.model_validate(message["locator"])]
        await sessions.act(session.id, step, {})
    if action == "fill" and message.get("locator"):
        from capability_forge.schemas.artifact import Locator

        step = Step(
            id="human",
            action=StepAction.FILL,
            locators=[Locator.model_validate(message["locator"])],
            literal=message.get("value"),
        )
        await sessions.act(session.id, step, {})


# Admin UI is the Vite app on :5173 in development. Built files can be copied later.

from __future__ import annotations

from temporalio import activity

from capability_forge.browser.session import sessions
from capability_forge.engine import open_session, persist_run, run_discovery, run_replay
from capability_forge.registry.db import registry
from capability_forge.schemas.run import RunKind, RunRecord, RunStatus
from capability_forge.temporal.models import DiscoveryInput, ReplayInput


@activity.defn
async def create_session(run_id: str, entry_url: str) -> str:
    session = await open_session(run_id, entry_url)
    return session.id


@activity.defn
async def close_session(session_id: str) -> None:
    await sessions.close(session_id)


@activity.defn
async def discover_until_done(payload: DiscoveryInput, session_id: str) -> dict:
    result = await run_discovery(payload.run_id, session_id, payload.goal)
    return {
        "status": result.status,
        "reason": result.reason,
        "needs_human": result.needs_human,
        "artifact_id": result.artifact.id if result.artifact else "",
        "outputs": result.outputs,
    }


@activity.defn
async def replay_until_done(payload: ReplayInput, session_id: str) -> dict:
    result = await run_replay(payload.run_id, session_id, payload.artifact_id, payload.params)
    return result.model_dump()


@activity.defn
async def mark_run(run_id: str, kind: str, status: str, extra: dict) -> None:
    existing = await registry.get_run(run_id)
    run = existing or RunRecord(id=run_id, kind=RunKind(kind), status=RunStatus(status))
    run.status = RunStatus(status)
    run.goal = extra.get("goal", run.goal)
    run.artifact_id = extra.get("artifact_id", run.artifact_id)
    run.outputs = extra.get("outputs", run.outputs)
    run.result = extra.get("result", run.result)
    run.workflow_id = extra.get("workflow_id", run.workflow_id)
    run.params = extra.get("params", run.params)
    await persist_run(run)


@activity.defn
async def set_human_control(session_id: str, reason: str) -> None:
    sessions.set_controller(session_id, "human", reason)


@activity.defn
async def set_agent_control(session_id: str) -> None:
    sessions.set_controller(session_id, "agent", "")

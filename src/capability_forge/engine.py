from __future__ import annotations

from uuid import uuid4

from capability_forge.browser.session import LiveSession, sessions
from capability_forge.config import settings
from capability_forge.discovery.agent import DiscoveryAgent, DiscoveryResult
from capability_forge.evidence.store import EvidenceWriter
from capability_forge.notify import approval_needed
from capability_forge.recording.compile import CAPABILITY_SLUG, seed_reference_artifact
from capability_forge.registry.db import registry
from capability_forge.replay.executor import ReplayExecutor
from capability_forge.schemas.run import OutcomeKind, ReplayResult, RunEvent, RunKind, RunRecord, RunStatus


async def ensure_ready() -> None:
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    await registry.init()
    if not await registry.versions_of(CAPABILITY_SLUG):
        await registry.upsert_artifact(seed_reference_artifact())


async def open_session(run_id: str, entry_url: str | None = None) -> LiveSession:
    await sessions.start()
    return await sessions.create(run_id, entry_url or settings.corebank_url)


async def run_discovery(run_id: str, session_id: str, goal: str) -> DiscoveryResult:
    session = sessions.get(session_id)
    evidence = EvidenceWriter(run_id, "discovery")
    await evidence.start_tracing(session.context)
    agent = DiscoveryAgent(session, evidence)
    result = await agent.run(goal)
    keep_trace = result.status != "succeeded"
    await evidence.stop_tracing(session.context, keep=keep_trace)
    if result.artifact:
        slug = result.artifact.slug or CAPABILITY_SLUG
        version = await registry.next_version(slug)
        result.artifact.slug = slug
        result.artifact.version = version
        result.artifact.id = f"{slug}-v{version}"
        result.artifact.status = "draft"
        evidence.write_json("artifact.json", result.artifact.model_dump())
        await registry.upsert_artifact(result.artifact)
        await approval_needed(result.artifact)
    evidence.write_json("result.json", {"status": result.status, "reason": result.reason, "outputs": result.outputs})
    return result


async def run_replay(run_id: str, session_id: str, artifact_id: str, params: dict[str, str]) -> ReplayResult:
    session = sessions.get(session_id)
    artifact = await registry.resolve(artifact_id)
    if not artifact:
        raise KeyError(f"unknown artifact {artifact_id}")
    evidence = EvidenceWriter(run_id, "replay")
    await evidence.start_tracing(session.context)
    executor = ReplayExecutor(session, evidence)
    result = await executor.run(artifact, params)
    await evidence.stop_tracing(session.context, keep=result.kind is not OutcomeKind.SUCCESS)
    evidence.write_json("result.json", result.model_dump())
    evidence.log(RunEvent(run_id=run_id, kind="result", message=result.kind.value, data=result.model_dump()))
    return result


async def persist_run(run: RunRecord) -> None:
    await registry.upsert_run(run)


def new_run(kind: RunKind, goal: str = "", artifact_id: str | None = None, params: dict[str, str] | None = None) -> RunRecord:
    return RunRecord(
        id=str(uuid4()),
        kind=kind,
        status=RunStatus.PENDING,
        goal=goal,
        artifact_id=artifact_id,
        params=params or {},
    )

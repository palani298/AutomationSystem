from __future__ import annotations

import argparse
import asyncio
import json
import sys

import uvicorn

from capability_forge.config import settings
from capability_forge.engine import ensure_ready, open_session, persist_run, run_discovery, run_replay
from capability_forge.recording.compile import seed_reference_artifact
from capability_forge.registry.db import registry
from capability_forge.schemas.run import RunKind, RunRecord, RunStatus


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="capability-forge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("api", help="Run the FastAPI control plane + in-process Temporal worker")
    sub.add_parser("worker", help="Run a standalone Temporal worker")
    sub.add_parser("mcp", help="Run the MCP stdio server")
    sub.add_parser("seed", help="Insert the reference artifact")

    d = sub.add_parser("discover", help="LLM discovery run against Corebank")
    d.add_argument("--goal", required=True)
    d.add_argument("--entry-url", default=None)

    r = sub.add_parser("replay", help="Deterministic replay of an artifact")
    r.add_argument("--artifact-id", default=None)
    r.add_argument("--latest", action="store_true")
    r.add_argument("--member-id", required=True)
    r.add_argument("--entry-url", default=None)

    a = sub.add_parser("approve", help="Flip an artifact to approved")
    a.add_argument("artifact_id")

    args = parser.parse_args(argv)
    if args.cmd == "api":
        uvicorn.run(
            "capability_forge.api.app:app",
            host=settings.app_host,
            port=settings.app_port,
            reload=False,
        )
        return
    if args.cmd == "worker":
        from capability_forge.temporal.runtime import run_worker_forever

        asyncio.run(run_worker_forever())
        return
    if args.cmd == "mcp":
        from capability_forge.mcp.server import main as mcp_main

        mcp_main()
        return
    if args.cmd == "seed":
        asyncio.run(_seed())
        return
    if args.cmd == "discover":
        asyncio.run(_discover(args.goal, args.entry_url))
        return
    if args.cmd == "replay":
        asyncio.run(_replay(args.artifact_id, args.latest, args.member_id, args.entry_url))
        return
    if args.cmd == "approve":
        asyncio.run(_approve(args.artifact_id))
        return


async def _seed() -> None:
    await ensure_ready()
    artifact = seed_reference_artifact()
    await registry.upsert_artifact(artifact)
    print(artifact.id)


async def _ensure_corebank() -> None:
    import httpx

    url = f"{settings.public_base_url}/corebank/"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=1.5)
            if response.status_code < 500:
                return
    except Exception:
        pass
    raise SystemExit(
        f"Corebank is not reachable at {url}. In another terminal run: capability-forge api"
    )


async def _discover(goal: str, entry_url: str | None) -> None:
    await ensure_ready()
    await _ensure_corebank()
    from uuid import uuid4

    run_id = str(uuid4())
    session = await open_session(run_id, entry_url or settings.corebank_url)
    run = RunRecord(id=run_id, kind=RunKind.DISCOVERY, status=RunStatus.RUNNING, goal=goal)
    await persist_run(run)
    try:
        result = await run_discovery(run_id, session.id, goal)
    finally:
        from capability_forge.browser.session import sessions

        await sessions.close(session.id)
    run.status = RunStatus.SUCCEEDED if result.status == "succeeded" else RunStatus.FAILED
    run.artifact_id = result.artifact.id if result.artifact else None
    run.outputs = result.outputs
    run.result = {"status": result.status, "reason": result.reason}
    await persist_run(run)
    print(json.dumps(run.result | {"artifact_id": run.artifact_id, "outputs": run.outputs}, indent=2))
    if result.status != "succeeded":
        sys.exit(1)


async def _replay(artifact_id: str | None, latest: bool, member_id: str, entry_url: str | None) -> None:
    await ensure_ready()
    await _ensure_corebank()
    artifact = None
    if latest:
        artifact = await registry.latest_artifact()
    elif artifact_id:
        artifact = await registry.resolve(artifact_id)
    if not artifact:
        raise SystemExit("no artifact found")
    from uuid import uuid4

    from capability_forge.browser.session import sessions

    run_id = str(uuid4())
    session = await open_session(run_id, entry_url or artifact.surface.entry_url)
    try:
        result = await run_replay(run_id, session.id, artifact.id, {"member_id": member_id})
    finally:
        await sessions.close(session.id)
    print(json.dumps(result.model_dump(), indent=2))
    if result.kind.value not in {"success", "business_outcome"}:
        sys.exit(1)


async def _approve(artifact_id: str) -> None:
    await ensure_ready()
    artifact = await registry.set_status(artifact_id, "approved")
    if not artifact:
        raise SystemExit("not found")
    from capability_forge.notify import approved as notify_approved

    await notify_approved(artifact)
    print(artifact.slug, f"v{artifact.version}", artifact.status)


if __name__ == "__main__":
    main()

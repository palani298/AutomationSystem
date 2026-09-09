from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from capability_forge.config import settings
from capability_forge.temporal.activities import (
    close_session,
    create_session,
    discover_until_done,
    mark_run,
    replay_until_done,
    set_agent_control,
    set_human_control,
)
from capability_forge.temporal.workflows import DiscoveryWorkflow, ReplayWorkflow


async def connect_client() -> Client:
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def build_worker(client: Client) -> Worker:
    return Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[DiscoveryWorkflow, ReplayWorkflow],
        activities=[
            create_session,
            close_session,
            discover_until_done,
            replay_until_done,
            mark_run,
            set_human_control,
            set_agent_control,
        ],
    )


async def run_worker_forever() -> None:
    client = await connect_client()
    worker = build_worker(client)
    await worker.run()


async def start_background_worker() -> asyncio.Task | None:
    try:
        client = await connect_client()
    except Exception:
        return None
    worker = build_worker(client)
    return asyncio.create_task(worker.run())

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import mcp.types as types
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server

from capability_forge.config import settings
from capability_forge.engine import ensure_ready
from capability_forge.registry.db import registry
from capability_forge.schemas.artifact import Artifact
from capability_forge.temporal.models import ReplayInput
from capability_forge.temporal.runtime import connect_client
from capability_forge.temporal.workflows import ReplayWorkflow


def _tool_from_artifact(artifact: Artifact) -> types.Tool:
    props = {
        name: {
            "type": "string",
            "description": next((p.description for p in artifact.inputs if p.name == name), ""),
        }
        for name in artifact.input_names()
    }
    required = [p.name for p in artifact.inputs if p.required]
    return types.Tool(
        name=artifact.slug,
        title=artifact.name,
        description=(
            f"{artifact.name} (v{artifact.version}, approved). {artifact.description}"
        ),
        input_schema={"type": "object", "properties": props, "required": required},
    )


async def _on_list_tools(_ctx, _params) -> types.ListToolsResult:
    artifacts = await registry.latest_approved_per_slug()
    return types.ListToolsResult(tools=[_tool_from_artifact(a) for a in artifacts])


async def _on_call_tool(_ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    artifact = await registry.latest_approved(params.name) or await registry.resolve(params.name)
    if not artifact or artifact.status != "approved":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"capability {params.name} is not approved or missing")],
            is_error=True,
        )
    arguments: dict[str, Any] = params.arguments or {}
    client = await connect_client()
    run_id = str(uuid4())
    result = await client.execute_workflow(
        ReplayWorkflow.run,
        ReplayInput(
            run_id=run_id,
            artifact_id=artifact.id,
            params={k: str(v) for k, v in arguments.items()},
            entry_url=artifact.surface.entry_url or settings.corebank_url,
        ),
        id=f"mcp-replay-{run_id}",
        task_queue=settings.temporal_task_queue,
    )
    text = json.dumps(result, default=str)
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content=result)


async def serve() -> None:
    await ensure_ready()
    server = Server(
        "capability-forge",
        instructions="Approved Corebank capabilities. Call with typed params (e.g. member_id).",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())

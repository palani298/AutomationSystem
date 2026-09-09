from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from capability_forge.temporal.activities import (
        close_session,
        create_session,
        discover_until_done,
        mark_run,
        replay_until_done,
        set_agent_control,
        set_human_control,
    )
    from capability_forge.temporal.models import DiscoveryInput, ReplayInput, WorkflowState


RETRY = RetryPolicy(maximum_attempts=2)
SLOW = timedelta(minutes=10)


@workflow.defn
class DiscoveryWorkflow:
    def __init__(self) -> None:
        self.state = WorkflowState()
        self._resume = False
        self._operator_note = ""

    @workflow.signal
    def human_resume(self, note: str = "") -> None:
        self._resume = True
        self._operator_note = note
        self.state.status = "resuming"

    @workflow.query
    def snapshot(self) -> dict:
        return {
            "status": self.state.status,
            "session_id": self.state.session_id,
            "reason": self.state.reason,
            "artifact_id": self.state.artifact_id,
            "outputs": self.state.outputs,
            "operator_note": self._operator_note,
        }

    @workflow.run
    async def run(self, payload: DiscoveryInput) -> dict:
        self.state.status = "running"
        await workflow.execute_activity(
            mark_run,
            args=[payload.run_id, "discovery", "running", {"goal": payload.goal, "workflow_id": workflow.info().workflow_id}],
            start_to_close_timeout=timedelta(seconds=30),
        )
        session_id = await workflow.execute_activity(
            create_session,
            args=[payload.run_id, payload.entry_url],
            start_to_close_timeout=timedelta(seconds=30),
        )
        self.state.session_id = session_id
        try:
            while True:
                self._resume = False
                result = await workflow.execute_activity(
                    discover_until_done,
                    args=[payload, session_id],
                    start_to_close_timeout=SLOW,
                    retry_policy=RETRY,
                )
                self.state.reason = result.get("reason", "")
                self.state.outputs = result.get("outputs") or {}
                self.state.artifact_id = result.get("artifact_id") or ""
                if result.get("needs_human"):
                    self.state.status = "waiting_human"
                    await workflow.execute_activity(
                        set_human_control,
                        args=[session_id, self.state.reason],
                        start_to_close_timeout=timedelta(seconds=15),
                    )
                    await workflow.execute_activity(
                        mark_run,
                        args=[payload.run_id, "discovery", "waiting_human", {"goal": payload.goal, "result": result}],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    await workflow.wait_condition(lambda: self._resume)
                    await workflow.execute_activity(
                        set_agent_control,
                        args=[session_id],
                        start_to_close_timeout=timedelta(seconds=15),
                    )
                    self.state.status = "running"
                    continue
                status = result.get("status") or "hard_failure"
                self.state.status = status
                extra = {
                    "goal": payload.goal,
                    "artifact_id": self.state.artifact_id,
                    "outputs": self.state.outputs,
                    "result": result,
                }
                mapped = {
                    "succeeded": "succeeded",
                    "escalated": "waiting_human",
                    "hard_failure": "hard_failure",
                }.get(status, status)
                await workflow.execute_activity(
                    mark_run,
                    args=[payload.run_id, "discovery", mapped, extra],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return result
        finally:
            await workflow.execute_activity(
                close_session,
                args=[session_id],
                start_to_close_timeout=timedelta(seconds=20),
            )


@workflow.defn
class ReplayWorkflow:
    def __init__(self) -> None:
        self.state = WorkflowState()
        self._resume = False

    @workflow.signal
    def human_resume(self, note: str = "") -> None:
        self._resume = True
        self.state.status = "resuming"

    @workflow.query
    def snapshot(self) -> dict:
        return {
            "status": self.state.status,
            "session_id": self.state.session_id,
            "reason": self.state.reason,
            "result": self.state.result,
        }

    @workflow.run
    async def run(self, payload: ReplayInput) -> dict:
        self.state.status = "running"
        await workflow.execute_activity(
            mark_run,
            args=[
                payload.run_id,
                "replay",
                "running",
                {
                    "artifact_id": payload.artifact_id,
                    "params": payload.params,
                    "workflow_id": workflow.info().workflow_id,
                },
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )
        session_id = await workflow.execute_activity(
            create_session,
            args=[payload.run_id, payload.entry_url],
            start_to_close_timeout=timedelta(seconds=30),
        )
        self.state.session_id = session_id
        try:
            result = await workflow.execute_activity(
                replay_until_done,
                args=[payload, session_id],
                start_to_close_timeout=SLOW,
                retry_policy=RETRY,
            )
            self.state.result = result
            kind = result.get("kind")
            status = {
                "success": "succeeded",
                "business_outcome": "business_outcome",
                "escalated": "waiting_human",
                "hard_failure": "hard_failure",
            }.get(kind, "hard_failure")
            if status == "waiting_human":
                self.state.status = status
                await workflow.execute_activity(
                    set_human_control,
                    args=[session_id, result.get("observed") or "replay stuck"],
                    start_to_close_timeout=timedelta(seconds=15),
                )
                await workflow.wait_condition(lambda: self._resume)
                result = await workflow.execute_activity(
                    replay_until_done,
                    args=[payload, session_id],
                    start_to_close_timeout=SLOW,
                    retry_policy=RETRY,
                )
                kind = result.get("kind")
                status = {
                    "success": "succeeded",
                    "business_outcome": "business_outcome",
                    "hard_failure": "hard_failure",
                }.get(kind, "hard_failure")
            self.state.status = status
            await workflow.execute_activity(
                mark_run,
                args=[
                    payload.run_id,
                    "replay",
                    status,
                    {
                        "artifact_id": payload.artifact_id,
                        "params": payload.params,
                        "outputs": result.get("outputs") or {},
                        "result": result,
                    },
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )
            return result
        finally:
            await workflow.execute_activity(
                close_session,
                args=[session_id],
                start_to_close_timeout=timedelta(seconds=20),
            )

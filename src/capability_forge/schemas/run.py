from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from capability_forge.schemas.artifact import Locator, StepAction


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunKind(str, Enum):
    DISCOVERY = "discovery"
    REPLAY = "replay"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    SUCCEEDED = "succeeded"
    BUSINESS_OUTCOME = "business_outcome"
    FAILED = "hard_failure"
    CANCELLED = "cancelled"


class OutcomeKind(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    HARD_FAILURE = "hard_failure"
    ESCALATED = "escalated"


class AgentDecision(BaseModel):
    thought: str = ""
    action: Literal[
        "click",
        "fill",
        "press",
        "extract",
        "dismiss",
        "wait",
        "done",
        "fail",
        "escalate",
    ]
    locator: Locator | None = None
    value: str | None = None
    extract_as: str | None = None
    outputs: dict[str, str] = Field(default_factory=dict)
    reason: str = ""


class ReplayResult(BaseModel):
    kind: OutcomeKind
    artifact_id: str
    run_id: str
    outputs: dict[str, str] = Field(default_factory=dict)
    business_code: str | None = None
    business_message: str | None = None
    failed_step_id: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence_dir: str = ""


class RunEvent(BaseModel):
    ts: str = Field(default_factory=utcnow)
    run_id: str
    kind: str
    step_id: str | None = None
    action: StepAction | str | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    id: str
    kind: RunKind
    status: RunStatus
    goal: str = ""
    artifact_id: str | None = None
    workflow_id: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    evidence_dir: str = ""
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)

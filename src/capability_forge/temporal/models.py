from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiscoveryInput:
    run_id: str
    goal: str
    entry_url: str


@dataclass
class ReplayInput:
    run_id: str
    artifact_id: str
    params: dict[str, str]
    entry_url: str


@dataclass
class WorkflowState:
    status: str = "pending"
    session_id: str = ""
    reason: str = ""
    artifact_id: str = ""
    outputs: dict[str, str] = field(default_factory=dict)
    result: dict = field(default_factory=dict)

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LocatorStrategy(str, Enum):
    ROLE_NAME = "role_name"
    LABEL = "label"
    PLACEHOLDER = "placeholder"
    TEXT = "text"
    TITLE = "title"
    CSS = "css"


class RiskClass(str, Enum):
    SAFE = "safe"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class StepAction(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    PRESS = "press"
    EXTRACT = "extract"
    WAIT = "wait"
    DISMISS = "dismiss"


class Locator(BaseModel):
    """How to find a control. Ordered fallbacks live on the Step, not here.

    Preference: accessibility role+name, then label/text, then CSS last.
    `frame_selector` is the seam that lets the same step work inside a frameset.
    """

    strategy: LocatorStrategy
    role: str | None = None
    name: str | None = None
    label: str | None = None
    text: str | None = None
    placeholder: str | None = None
    title: str | None = None
    css: str | None = None
    exact: bool = False
    frame_selector: str | None = None
    nth: int | None = None


class Param(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"] = "string"
    required: bool = True
    description: str = ""


class Step(BaseModel):
    id: str
    action: StepAction
    description: str = ""
    locators: list[Locator] = Field(default_factory=list)
    value_from: str | None = None
    literal: str | None = None
    extract_as: str | None = None
    url: str | None = None
    risk: RiskClass = RiskClass.SAFE
    wait_ms: int | None = None


class Assertion(BaseModel):
    kind: Literal["url_matches", "visible_text", "locator_visible", "extract_present"]
    pattern: str | None = None
    locator: Locator | None = None
    extract_name: str | None = None


class Checkpoint(BaseModel):
    description: str
    all_of: list[Assertion] = Field(default_factory=list)


class BusinessOutcome(BaseModel):
    code: str
    message: str
    detect: Assertion


class Surface(BaseModel):
    """Perception/action seam. Today: web. The schema is surface-kinded so a
    desktop adapter can be swapped without changing the flow graph.
    """

    kind: Literal["web", "desktop"] = "web"
    entry_url: str
    vendor_app: str = "corebank"
    vendor_version: str = "1.0"


class Artifact(BaseModel):
    """A typed, versioned, agent-invocable capability.

    The artifact never stores live secrets or PII — only locators, parameter
    *names*, and checkpoint predicates. Callers supply fresh values per invoke.
    """

    schema_version: str = "1.0.0"
    id: str
    slug: str = "lookup-member-balance"
    """Stable capability name. MCP tools are keyed by slug, not by row id.
    Versions of the same slug share this value; only the latest *approved*
    version is callable as that tool.
    """
    name: str
    description: str
    version: int = 1
    status: Literal["draft", "approved"] = "draft"
    surface: Surface
    inputs: list[Param] = Field(default_factory=list)
    outputs: list[Param] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    checkpoint: Checkpoint
    business_outcomes: list[BusinessOutcome] = Field(default_factory=list)
    tenant_overrides: dict[str, Any] = Field(default_factory=dict)
    created_from_run_id: str = ""
    created_at: str = ""

    def input_names(self) -> set[str]:
        return {p.name for p in self.inputs}

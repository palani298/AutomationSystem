from __future__ import annotations

import re
from datetime import datetime, timezone

from capability_forge.config import settings
from capability_forge.schemas.artifact import (
    Artifact,
    Assertion,
    BusinessOutcome,
    Checkpoint,
    Locator,
    LocatorStrategy,
    Param,
    Step,
    StepAction,
    Surface,
)
from capability_forge.schemas.run import AgentDecision


_MEMBER = re.compile(r"\b(\d{4,6})\b")
CAPABILITY_SLUG = "lookup-member-balance"
CAPABILITY_NAME = "Lookup member savings balance"


def artifact_id(slug: str, version: int) -> str:
    return f"{slug}-v{version}"


def infer_member_id(goal: str) -> str | None:
    match = _MEMBER.search(goal)
    return match.group(1) if match else None


def decision_to_step(index: int, decision: AgentDecision, goal: str) -> Step | None:
    if decision.action in {"done", "fail", "escalate", "wait"}:
        if decision.action == "wait":
            return Step(
                id=f"s{index:02d}",
                action=StepAction.WAIT,
                description=decision.thought,
                wait_ms=400,
            )
        return None
    locators = [decision.locator] if decision.locator else []
    action = StepAction(decision.action)
    value_from = None
    literal = decision.value
    member_id = infer_member_id(goal)
    if action is StepAction.FILL and decision.value and member_id and decision.value == member_id:
        value_from = "params.member_id"
        literal = None
    return Step(
        id=f"s{index:02d}",
        action=action,
        description=decision.thought,
        locators=locators,
        value_from=value_from,
        literal=literal,
        extract_as=decision.extract_as,
    )


def compile_artifact(
    *,
    run_id: str,
    goal: str,
    steps: list[Step],
    outputs: dict[str, str],
    version: int = 1,
) -> Artifact:
    member_id = infer_member_id(goal)
    inputs = [
        Param(name="member_id", type="string", description="Member number to look up"),
    ]
    output_params = [
        Param(name=name, type="string", required=False, description=f"Extracted {name}")
        for name in (outputs or {"savings_balance": ""})
    ]
    if not any(p.name == "savings_balance" for p in output_params):
        output_params.append(
            Param(name="savings_balance", type="string", required=False, description="Savings available balance")
        )

    # Always include a parameterized fill if the LLM typed a member id via CSS-less locator.
    if member_id and not any(s.value_from == "params.member_id" for s in steps):
        for step in steps:
            if step.action is StepAction.FILL and step.literal == member_id:
                step.value_from = "params.member_id"
                step.literal = None

    checkpoint = Checkpoint(
        description="Confirmation or member file showing a savings balance is visible",
        all_of=[
            Assertion(kind="url_matches", pattern=r"/(member|inquiry|confirm)"),
        ],
    )
    outcomes = [
        BusinessOutcome(
            code="MEMBER_NOT_FOUND",
            message="No member file exists for the supplied member number",
            detect=Assertion(kind="visible_text", pattern="No records found"),
        ),
        BusinessOutcome(
            code="ACCOUNT_RESTRICTED",
            message="Member file is on a servicing hold",
            detect=Assertion(kind="visible_text", pattern="Servicing hold"),
        ),
        BusinessOutcome(
            code="PERMISSION_DENIED",
            message="Operator is not allowed to perform that action",
            detect=Assertion(kind="visible_text", pattern="Permission denied"),
        ),
    ]
    slug = CAPABILITY_SLUG
    return Artifact(
        id=artifact_id(slug, version),
        slug=slug,
        name=CAPABILITY_NAME,
        description=goal,
        version=version,
        status="draft",
        surface=Surface(kind="web", entry_url=settings.corebank_url, vendor_app="corebank"),
        inputs=inputs,
        outputs=output_params,
        steps=steps,
        checkpoint=checkpoint,
        business_outcomes=outcomes,
        created_from_run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def seed_reference_artifact() -> Artifact:
    """A known-good artifact used by tests and as a fallback demo."""
    frame = 'iframe[title="Member search form"]'
    return Artifact(
        id=artifact_id(CAPABILITY_SLUG, 1),
        slug=CAPABILITY_SLUG,
        name=CAPABILITY_NAME,
        description="look up member {member_id} and read their current savings balance",
        version=1,
        status="approved",
        surface=Surface(kind="web", entry_url=settings.corebank_url, vendor_app="corebank"),
        inputs=[Param(name="member_id", description="Member number")],
        outputs=[
            Param(name="savings_balance", required=False),
            Param(name="confirmation_id", required=False),
        ],
        steps=[
            Step(
                id="s01",
                action=StepAction.NAVIGATE,
                description="Open servicing search",
                url=settings.corebank_url,
            ),
            Step(
                id="s02",
                action=StepAction.FILL,
                description="Enter member number",
                value_from="params.member_id",
                locators=[
                    Locator(
                        strategy=LocatorStrategy.LABEL,
                        label="Member number",
                        frame_selector=frame,
                    ),
                    Locator(
                        strategy=LocatorStrategy.ROLE_NAME,
                        role="textbox",
                        name="Member number",
                        frame_selector=frame,
                    ),
                ],
            ),
            Step(
                id="s03",
                action=StepAction.CLICK,
                description="Search",
                locators=[
                    Locator(
                        strategy=LocatorStrategy.ROLE_NAME,
                        role="button",
                        name="Search",
                        frame_selector=frame,
                    )
                ],
            ),
            Step(
                id="s04",
                action=StepAction.CLICK,
                description="Open member file",
                locators=[
                    Locator(strategy=LocatorStrategy.ROLE_NAME, role="link", name="Open file"),
                    Locator(strategy=LocatorStrategy.TEXT, text="Open file"),
                ],
            ),
            Step(
                id="s05",
                action=StepAction.EXTRACT,
                description="Read savings available",
                extract_as="savings_balance",
                locators=[
                    Locator(strategy=LocatorStrategy.ROLE_NAME, role="generic", name="Savings balance"),
                    Locator(strategy=LocatorStrategy.CSS, css='[aria-label="Savings balance"]'),
                ],
            ),
            Step(
                id="s06",
                action=StepAction.CLICK,
                description="Record inquiry",
                locators=[
                    Locator(
                        strategy=LocatorStrategy.ROLE_NAME,
                        role="button",
                        name="Record balance inquiry",
                    ),
                    Locator(strategy=LocatorStrategy.TEXT, text="Record balance inquiry"),
                ],
            ),
            Step(
                id="s07",
                action=StepAction.EXTRACT,
                description="Read confirmation",
                extract_as="confirmation_id",
                locators=[
                    Locator(strategy=LocatorStrategy.CSS, css='[aria-label="Inquiry confirmation"]'),
                ],
            ),
        ],
        checkpoint=Checkpoint(
            description="Inquiry confirmation page is showing",
            all_of=[
                Assertion(kind="visible_text", pattern="Balance inquiry has been written"),
                Assertion(kind="extract_present", extract_name="savings_balance"),
            ],
        ),
        business_outcomes=[
            BusinessOutcome(
                code="MEMBER_NOT_FOUND",
                message="No member file exists for the supplied member number",
                detect=Assertion(kind="visible_text", pattern="No records found"),
            ),
            BusinessOutcome(
                code="ACCOUNT_RESTRICTED",
                message="Member file is on a servicing hold",
                detect=Assertion(kind="visible_text", pattern="Servicing hold"),
            ),
        ],
        created_from_run_id="seed",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

from __future__ import annotations

from dataclasses import dataclass, field

from capability_forge.browser.actions import execute_step, observe
from capability_forge.browser.session import LiveSession
from capability_forge.config import settings
from capability_forge.discovery.llm import LLMClient
from capability_forge.evidence.store import EvidenceWriter
from capability_forge.recording.compile import compile_artifact, decision_to_step
from capability_forge.safety.allowlist import ActionGuard
from capability_forge.schemas.artifact import Artifact, Step, StepAction
from capability_forge.schemas.run import RunEvent


@dataclass
class DiscoveryResult:
    artifact: Artifact | None
    outputs: dict[str, str]
    status: str
    reason: str = ""
    steps: list[Step] = field(default_factory=list)
    needs_human: bool = False


class DiscoveryAgent:
    def __init__(self, session: LiveSession, evidence: EvidenceWriter, llm: LLMClient | None = None) -> None:
        self.session = session
        self.evidence = evidence
        self.llm = llm or LLMClient()
        self.guard = ActionGuard()
        self.history: list[str] = []
        self.recorded: list[Step] = []
        self.page_fingerprints: list[str] = []

    def _stuck(self, fingerprint: str) -> bool:
        self.page_fingerprints.append(fingerprint)
        if len(self.page_fingerprints) < 4:
            return False
        return len(set(self.page_fingerprints[-4:])) == 1

    async def run(self, goal: str) -> DiscoveryResult:
        page = self.session.page
        outputs: dict[str, str] = {}

        for i in range(1, settings.max_discovery_steps + 1):
            url_guard = self.guard.check_url(page.url)
            if not url_guard.allowed:
                self.evidence.log(RunEvent(run_id=self.session.run_id, kind="guard", message=url_guard.reason))
                return DiscoveryResult(None, outputs, "hard_failure", url_guard.reason, self.recorded)

            observation = await observe(page)
            fingerprint = f"{observation['url']}|{observation['aria'][:400]}"
            if self._stuck(fingerprint):
                self.session.stuck_reason = "same page observed four times"
                return DiscoveryResult(None, outputs, "escalated", self.session.stuck_reason, self.recorded, True)

            decision = await self.llm.decide(goal, observation, self.history)
            self.evidence.log(
                RunEvent(
                    run_id=self.session.run_id,
                    kind="decision",
                    step_id=f"s{i:02d}",
                    action=decision.action,
                    message=decision.thought,
                    data={"reason": decision.reason},
                )
            )
            self.history.append(f"{decision.action}: {decision.thought}")

            if decision.action == "escalate":
                self.session.stuck_reason = decision.reason or "model requested human"
                return DiscoveryResult(None, outputs, "escalated", self.session.stuck_reason, self.recorded, True)
            if decision.action == "fail":
                await self.evidence.screenshot(page, f"fail-{i:02d}")
                return DiscoveryResult(None, outputs, "hard_failure", decision.reason, self.recorded)
            if decision.action == "done":
                outputs.update(decision.outputs)
                artifact = compile_artifact(
                    run_id=self.session.run_id, goal=goal, steps=self.recorded, outputs=outputs
                )
                return DiscoveryResult(artifact, outputs, "succeeded", decision.reason, self.recorded)

            step = decision_to_step(i, decision, goal)
            if step is None:
                continue
            if step.action is not StepAction.WAIT:
                step_guard = self.guard.check_step(step, page.url, step.url)
                if not step_guard.allowed:
                    return DiscoveryResult(None, outputs, "hard_failure", step_guard.reason, self.recorded)
                if step_guard.requires_human:
                    self.session.stuck_reason = step_guard.reason
                    return DiscoveryResult(None, outputs, "escalated", step_guard.reason, self.recorded, True)
            try:
                extracted = await execute_step(page, step, _params_from_goal(goal))
            except Exception as exc:
                await self.evidence.screenshot(page, f"error-{i:02d}")
                self.evidence.log(
                    RunEvent(run_id=self.session.run_id, kind="act_error", step_id=step.id, message=str(exc))
                )
                self.session.stuck_reason = f"action failed: {exc}"
                return DiscoveryResult(None, outputs, "escalated", self.session.stuck_reason, self.recorded, True)
            if extracted and step.extract_as:
                outputs[step.extract_as] = extracted
            self.recorded.append(step)
            await self.evidence.screenshot(page, f"step-{step.id}")

        self.session.stuck_reason = "max discovery steps reached"
        return DiscoveryResult(None, outputs, "escalated", self.session.stuck_reason, self.recorded, True)


def _params_from_goal(goal: str) -> dict[str, str]:
    from capability_forge.recording.compile import infer_member_id

    member_id = infer_member_id(goal)
    return {"member_id": member_id} if member_id else {}

from __future__ import annotations

import re

from playwright.async_api import Page

from capability_forge.browser.actions import execute_step, observe
from capability_forge.browser.locators import resolve_first_visible
from capability_forge.browser.session import LiveSession
from capability_forge.evidence.store import EvidenceWriter
from capability_forge.safety.allowlist import ActionGuard
from capability_forge.schemas.artifact import Artifact, Assertion, Step
from capability_forge.schemas.run import OutcomeKind, ReplayResult, RunEvent


class ReplayExecutor:
    def __init__(self, session: LiveSession, evidence: EvidenceWriter) -> None:
        self.session = session
        self.evidence = evidence
        self.guard = ActionGuard()

    async def run(self, artifact: Artifact, params: dict[str, str]) -> ReplayResult:
        page = self.session.page
        outputs: dict[str, str] = {}
        missing = [p.name for p in artifact.inputs if p.required and p.name not in params]
        if missing:
            return self._fail(artifact, "precheck", f"missing params: {missing}", page.url)

        for step in artifact.steps:
            business = await self._detect_business(page, artifact)
            if business:
                return business

            recoverable = await self._recover(page)
            if recoverable:
                self.evidence.log(
                    RunEvent(run_id=self.session.run_id, kind="recovered", message=recoverable)
                )

            guard = self.guard.check_step(step, page.url, step.url)
            if not guard.allowed:
                await self.evidence.screenshot(page, f"blocked-{step.id}")
                return self._fail(artifact, step.id, guard.reason, page.url)
            if guard.requires_human:
                self.session.stuck_reason = guard.reason
                return ReplayResult(
                    kind=OutcomeKind.ESCALATED,
                    artifact_id=artifact.id,
                    run_id=self.session.run_id,
                    failed_step_id=step.id,
                    expected="human confirmation for irreversible action",
                    observed=guard.reason,
                    evidence_dir=str(self.evidence.dir),
                )

            try:
                extracted = await execute_step(page, step, params)
            except Exception as exc:
                business = await self._detect_business(page, artifact)
                if business:
                    return business
                await self.evidence.screenshot(page, f"error-{step.id}")
                self.evidence.log(
                    RunEvent(
                        run_id=self.session.run_id,
                        kind="step_error",
                        step_id=step.id,
                        message=str(exc),
                    )
                )
                return self._fail(artifact, step.id, f"expected to {step.action} {step.description}", str(exc))

            if extracted and step.extract_as:
                outputs[step.extract_as] = extracted
            self.evidence.log(
                RunEvent(
                    run_id=self.session.run_id,
                    kind="step",
                    step_id=step.id,
                    action=step.action,
                    message=step.description,
                )
            )

        business = await self._detect_business(page, artifact)
        if business:
            return business

        ok, observed = await self._checkpoint(page, artifact, outputs)
        if not ok:
            await self.evidence.screenshot(page, "checkpoint-failed")
            return self._fail(artifact, "checkpoint", artifact.checkpoint.description, observed)

        return ReplayResult(
            kind=OutcomeKind.SUCCESS,
            artifact_id=artifact.id,
            run_id=self.session.run_id,
            outputs=outputs,
            evidence_dir=str(self.evidence.dir),
        )

    async def _detect_business(self, page: Page, artifact: Artifact) -> ReplayResult | None:
        body = ""
        try:
            body = await page.inner_text("body")
        except Exception:
            return None
        for outcome in artifact.business_outcomes:
            if await self._assertion_holds(page, outcome.detect, {}, body):
                await self.evidence.screenshot(page, f"business-{outcome.code}")
                return ReplayResult(
                    kind=OutcomeKind.BUSINESS_OUTCOME,
                    artifact_id=artifact.id,
                    run_id=self.session.run_id,
                    business_code=outcome.code,
                    business_message=outcome.message,
                    observed=outcome.detect.pattern,
                    evidence_dir=str(self.evidence.dir),
                )
        return None

    async def _recover(self, page: Page) -> str | None:
        """Known recoverable interstitials — dismiss and continue."""
        try:
            notice = page.get_by_role("button", name="Acknowledge")
            if await notice.count():
                await notice.first.click(timeout=800)
                return "dismissed system notice"
        except Exception:
            return None
        return None

    async def _checkpoint(self, page: Page, artifact: Artifact, outputs: dict[str, str]) -> tuple[bool, str]:
        body = await page.inner_text("body")
        for assertion in artifact.checkpoint.all_of:
            if not await self._assertion_holds(page, assertion, outputs, body):
                return False, f"failed assertion {assertion.kind}: {assertion.pattern or assertion.extract_name}"
        return True, "ok"

    async def _assertion_holds(
        self, page: Page, assertion: Assertion, outputs: dict[str, str], body: str
    ) -> bool:
        if assertion.kind == "url_matches":
            return bool(re.search(assertion.pattern or "", page.url))
        if assertion.kind == "visible_text":
            return bool(assertion.pattern) and assertion.pattern in body
        if assertion.kind == "extract_present":
            return bool(outputs.get(assertion.extract_name or ""))
        if assertion.kind == "locator_visible" and assertion.locator:
            try:
                await resolve_first_visible(page, [assertion.locator], timeout_ms=1500)
                return True
            except Exception:
                return False
        return False

    def _fail(self, artifact: Artifact, step_id: str, expected: str, observed: str) -> ReplayResult:
        return ReplayResult(
            kind=OutcomeKind.HARD_FAILURE,
            artifact_id=artifact.id,
            run_id=self.session.run_id,
            failed_step_id=step_id,
            expected=expected,
            observed=observed,
            evidence_dir=str(self.evidence.dir),
        )

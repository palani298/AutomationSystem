from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from capability_forge.config import Settings, settings
from capability_forge.schemas.artifact import RiskClass, Step, StepAction


ALLOWED_ACTIONS = {
    StepAction.NAVIGATE,
    StepAction.CLICK,
    StepAction.FILL,
    StepAction.SELECT,
    StepAction.PRESS,
    StepAction.EXTRACT,
    StepAction.WAIT,
    StepAction.DISMISS,
}

IRREVERSIBLE_PATH_MARKERS = ("close-account", "post-transfer", "wire", "delete")


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str = ""
    risk: RiskClass = RiskClass.SAFE
    requires_human: bool = False


class ActionGuard:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or settings

    def check_url(self, url: str) -> GuardDecision:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            return GuardDecision(False, f"blocked scheme: {parsed.scheme}")
        if host not in self.cfg.allowlist_host_set:
            return GuardDecision(False, f"host not on allowlist: {host}")
        return GuardDecision(True, risk=self._risk_for_path(parsed.path))

    def check_step(self, step: Step, current_url: str, target_url: str | None = None) -> GuardDecision:
        if step.action not in ALLOWED_ACTIONS:
            return GuardDecision(False, f"action not allowed: {step.action}")
        url_decision = self.check_url(current_url)
        if not url_decision.allowed:
            return url_decision
        if target_url:
            dest = self.check_url(target_url)
            if not dest.allowed:
                return dest
        risk = step.risk
        if target_url:
            risk = _max_risk(risk, self._risk_for_path(urlparse(target_url).path))
        risk = _max_risk(risk, self._risk_for_path(urlparse(current_url).path))
        if risk is RiskClass.IRREVERSIBLE:
            return GuardDecision(
                True,
                "irreversible action requires a human before execution",
                risk=risk,
                requires_human=True,
            )
        return GuardDecision(True, risk=risk)

    def _risk_for_path(self, path: str) -> RiskClass:
        lowered = path.lower()
        if any(marker in lowered for marker in IRREVERSIBLE_PATH_MARKERS):
            return RiskClass.IRREVERSIBLE
        if "confirm" in lowered or "inquiry" in lowered:
            return RiskClass.REVERSIBLE
        return RiskClass.SAFE


def _max_risk(a: RiskClass, b: RiskClass) -> RiskClass:
    order = {RiskClass.SAFE: 0, RiskClass.REVERSIBLE: 1, RiskClass.IRREVERSIBLE: 2}
    return a if order[a] >= order[b] else b

from capability_forge.safety.allowlist import ActionGuard
from capability_forge.safety.redact import redact_mapping, redact_text
from capability_forge.schemas.artifact import RiskClass, Step, StepAction


def test_redacts_pii_and_amounts():
    text = "Jane paid $4,250.17 from 123-45-6789"
    out = redact_text(text)
    assert "$4,250.17" not in out
    assert "123-45-6789" not in out
    assert "[REDACTED_AMOUNT]" in out


def test_redacts_sensitive_keys():
    out = redact_mapping({"member_name": "Jane Alvarez", "step": "click"})
    assert out["member_name"] == "[REDACTED]"
    assert out["step"] == "click"


def test_allowlist_blocks_foreign_host():
    guard = ActionGuard()
    decision = guard.check_url("https://evil.example/login")
    assert decision.allowed is False


def test_irreversible_path_requires_human():
    guard = ActionGuard()
    step = Step(id="x", action=StepAction.CLICK, risk=RiskClass.SAFE)
    decision = guard.check_step(step, "http://127.0.0.1:8787/corebank/member/12345/close-account")
    assert decision.requires_human is True
    assert decision.risk is RiskClass.IRREVERSIBLE

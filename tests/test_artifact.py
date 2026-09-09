from capability_forge.recording.compile import compile_artifact, decision_to_step, infer_member_id, seed_reference_artifact
from capability_forge.schemas.artifact import Artifact, StepAction
from capability_forge.schemas.run import AgentDecision


def test_infers_member_id():
    assert infer_member_id("look up member 12345 and read balance") == "12345"


def test_fill_becomes_parameter():
    decision = AgentDecision(action="fill", value="12345", thought="type id")
    step = decision_to_step(1, decision, "look up member 12345")
    assert step is not None
    assert step.value_from == "params.member_id"
    assert step.literal is None


def test_seed_artifact_is_reviewable_contract():
    artifact = seed_reference_artifact()
    assert artifact.slug == "lookup-member-balance"
    assert artifact.id == "lookup-member-balance-v1"
    assert artifact.version == 1
    assert artifact.inputs[0].name == "member_id"
    assert any(s.action is StepAction.EXTRACT for s in artifact.steps)
    assert artifact.checkpoint.all_of
    assert {o.code for o in artifact.business_outcomes} >= {"MEMBER_NOT_FOUND"}
    Artifact.model_validate(artifact.model_dump())


def test_compile_never_embeds_live_member_id_as_literal_when_parameterized():
    from capability_forge.schemas.artifact import Locator, LocatorStrategy, Step

    steps = [
        Step(
            id="s01",
            action=StepAction.FILL,
            value_from="params.member_id",
            locators=[Locator(strategy=LocatorStrategy.LABEL, label="Member number")],
        )
    ]
    artifact = compile_artifact(run_id="r1", goal="look up member 12345", steps=steps, outputs={"savings_balance": "1"})
    dumped = artifact.model_dump_json()
    assert "params.member_id" in dumped
    assert artifact.status == "draft"
    assert artifact.version == 1

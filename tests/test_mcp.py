from capability_forge.mcp.server import _tool_from_artifact
from capability_forge.recording.compile import CAPABILITY_SLUG, seed_reference_artifact


def test_approved_artifact_becomes_generic_tool():
    tool = _tool_from_artifact(seed_reference_artifact())
    assert tool.name == CAPABILITY_SLUG
    assert "member_id" in tool.input_schema["required"]

import pytest

from capability_forge.mcp.server import _tool_from_artifact
from capability_forge.recording.compile import CAPABILITY_SLUG, compile_artifact, seed_reference_artifact
from capability_forge.registry.db import Registry
from capability_forge.schemas.artifact import Locator, LocatorStrategy, Step, StepAction


@pytest.fixture
async def reg(tmp_path):
    db = Registry(tmp_path / "registry.sqlite")
    await db.init()
    return db


def _draft(version: int):
    return compile_artifact(
        run_id="r",
        goal="look up member 12345",
        steps=[
            Step(
                id="s01",
                action=StepAction.FILL,
                value_from="params.member_id",
                locators=[Locator(strategy=LocatorStrategy.LABEL, label="Member number")],
            )
        ],
        outputs={"savings_balance": "1"},
        version=version,
    )


@pytest.mark.asyncio
async def test_versions_increment_and_mcp_tracks_latest_approved(reg: Registry):
    v1 = seed_reference_artifact()
    await reg.upsert_artifact(v1)
    assert await reg.next_version(CAPABILITY_SLUG) == 2

    v2 = _draft(2)
    await reg.upsert_artifact(v2)
    live = await reg.latest_approved(CAPABILITY_SLUG)
    assert live is not None
    assert live.version == 1
    tools = await reg.latest_approved_per_slug()
    assert [t.slug for t in tools] == [CAPABILITY_SLUG]
    assert _tool_from_artifact(tools[0]).name == CAPABILITY_SLUG
    assert _tool_from_artifact(tools[0]).description.startswith("Lookup member")

    await reg.set_status(v2.id, "approved")
    live = await reg.latest_approved(CAPABILITY_SLUG)
    assert live is not None and live.version == 2
    assert (await reg.resolve(CAPABILITY_SLUG)).id == v2.id


@pytest.mark.asyncio
async def test_catalog_lists_drafts_separately_from_live(reg: Registry):
    await reg.upsert_artifact(seed_reference_artifact())
    await reg.upsert_artifact(_draft(2))
    catalog = await reg.catalog()
    assert catalog[0]["live_version"] == 1
    assert catalog[0]["pending_count"] == 1
    drafts = await reg.pending_drafts()
    assert drafts[0].version == 2


@pytest.mark.asyncio
async def test_resolve_accepts_slug_version_and_legacy_ref(reg: Registry):
    v1 = seed_reference_artifact()
    v1.id = "lookup-member-balance-ref"
    await reg.upsert_artifact(v1)
    await reg.init()
    found = await reg.resolve("lookup-member-balance-v1")
    assert found is not None
    assert found.version == 1
    assert found.slug == CAPABILITY_SLUG

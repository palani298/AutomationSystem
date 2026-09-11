from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import aiosqlite

from capability_forge.config import settings
from capability_forge.recording.compile import CAPABILITY_SLUG
from capability_forge.schemas.artifact import Artifact
from capability_forge.schemas.run import RunRecord, utcnow


SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL DEFAULT 'lookup-member-balance',
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  goal TEXT,
  artifact_id TEXT,
  workflow_id TEXT,
  params TEXT,
  outputs TEXT,
  result TEXT,
  evidence_dir TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Registry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.database_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            cols = {row[1] for row in await (await db.execute("PRAGMA table_info(artifacts)")).fetchall()}
            if "slug" not in cols:
                await db.execute(
                    "ALTER TABLE artifacts ADD COLUMN slug TEXT NOT NULL DEFAULT 'lookup-member-balance'"
                )
            await db.commit()
        await self._backfill_slugs()
        await self._migrate_legacy_seed_id()

    async def _backfill_slugs(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT id, slug, body FROM artifacts")).fetchall()
        for row in rows:
            artifact = Artifact.model_validate_json(row["body"])
            slug = row["slug"] or artifact.slug or CAPABILITY_SLUG
            if artifact.slug != slug or row["slug"] != slug:
                artifact.slug = slug
                await self.upsert_artifact(artifact)

    async def _migrate_legacy_seed_id(self) -> None:
        """Older DBs used lookup-member-balance-ref; DEMO.md uses …-v1."""
        from capability_forge.recording.compile import artifact_id

        old = await self.get_artifact("lookup-member-balance-ref")
        new_id = artifact_id(CAPABILITY_SLUG, 1)
        if not old or await self.get_artifact(new_id):
            return
        old.id = new_id
        old.slug = CAPABILITY_SLUG
        old.version = 1
        await self.upsert_artifact(old)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM artifacts WHERE id=?", ("lookup-member-balance-ref",))
            await db.commit()

    async def upsert_artifact(self, artifact: Artifact) -> None:
        if not artifact.slug:
            artifact.slug = CAPABILITY_SLUG
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO artifacts (id, slug, name, status, version, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  slug=excluded.slug,
                  name=excluded.name,
                  status=excluded.status,
                  version=excluded.version,
                  body=excluded.body
                """,
                (
                    artifact.id,
                    artifact.slug,
                    artifact.name,
                    artifact.status,
                    artifact.version,
                    artifact.model_dump_json(),
                    artifact.created_at,
                ),
            )
            await db.commit()

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT body FROM artifacts WHERE id=?", (artifact_id,))
            row = await cur.fetchone()
            return Artifact.model_validate_json(row["body"]) if row else None

    async def resolve(self, ref: str) -> Artifact | None:
        """Exact row id, `{slug}-v{n}`, slug (latest approved), or latest any version."""
        found = await self.get_artifact(ref)
        if found:
            return found
        if "-v" in ref:
            slug, _, suffix = ref.rpartition("-v")
            if slug and suffix.isdigit():
                version = int(suffix)
                for artifact in await self.versions_of(slug):
                    if artifact.version == version:
                        return artifact
        return await self.latest_approved(ref) or await self.latest_for_slug(ref)

    async def latest_artifact(self) -> Artifact | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT body FROM artifacts ORDER BY created_at DESC LIMIT 1")
            row = await cur.fetchone()
            return Artifact.model_validate_json(row["body"]) if row else None

    async def list_artifacts(self) -> list[Artifact]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT body FROM artifacts ORDER BY slug ASC, version DESC")
            rows = await cur.fetchall()
            return [Artifact.model_validate_json(r["body"]) for r in rows]

    async def versions_of(self, slug: str) -> list[Artifact]:
        return [a for a in await self.list_artifacts() if a.slug == slug]

    async def next_version(self, slug: str) -> int:
        versions = await self.versions_of(slug)
        return (max(a.version for a in versions) + 1) if versions else 1

    async def latest_for_slug(self, slug: str) -> Artifact | None:
        versions = await self.versions_of(slug)
        return max(versions, key=lambda a: a.version) if versions else None

    async def latest_approved(self, slug: str) -> Artifact | None:
        approved = [a for a in await self.versions_of(slug) if a.status == "approved"]
        return max(approved, key=lambda a: a.version) if approved else None

    async def latest_approved_per_slug(self) -> list[Artifact]:
        grouped: dict[str, list[Artifact]] = defaultdict(list)
        for artifact in await self.list_artifacts():
            if artifact.status == "approved":
                grouped[artifact.slug].append(artifact)
        return [max(items, key=lambda a: a.version) for items in grouped.values()]

    async def pending_drafts(self) -> list[Artifact]:
        return [a for a in await self.list_artifacts() if a.status == "draft"]

    async def catalog(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[Artifact]] = defaultdict(list)
        for artifact in await self.list_artifacts():
            grouped[artifact.slug].append(artifact)
        out: list[dict[str, Any]] = []
        for slug, versions in grouped.items():
            versions = sorted(versions, key=lambda a: a.version, reverse=True)
            live = await self.latest_approved(slug)
            out.append(
                {
                    "slug": slug,
                    "name": versions[0].name,
                    "live_version": live.version if live else None,
                    "live_id": live.id if live else None,
                    "pending_count": sum(1 for a in versions if a.status == "draft"),
                    "versions": [a.model_dump() for a in versions],
                }
            )
        return out

    async def approved_artifacts(self) -> list[Artifact]:
        return await self.latest_approved_per_slug()

    async def set_status(self, artifact_id: str, status: str) -> Artifact | None:
        artifact = await self.get_artifact(artifact_id)
        if not artifact:
            return None
        artifact.status = status  # type: ignore[assignment]
        await self.upsert_artifact(artifact)
        return artifact

    async def upsert_run(self, run: RunRecord) -> None:
        run.updated_at = utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO runs (id, kind, status, goal, artifact_id, workflow_id, params, outputs, result, evidence_dir, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  status=excluded.status,
                  goal=excluded.goal,
                  artifact_id=excluded.artifact_id,
                  workflow_id=excluded.workflow_id,
                  params=excluded.params,
                  outputs=excluded.outputs,
                  result=excluded.result,
                  evidence_dir=excluded.evidence_dir,
                  updated_at=excluded.updated_at
                """,
                (
                    run.id,
                    run.kind.value,
                    run.status.value,
                    run.goal,
                    run.artifact_id,
                    run.workflow_id,
                    json.dumps(run.params),
                    json.dumps(run.outputs),
                    json.dumps(run.result),
                    run.evidence_dir,
                    run.created_at,
                    run.updated_at,
                ),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM runs WHERE id=?", (run_id,))
            row = await cur.fetchone()
            return _row_to_run(row) if row else None

    async def list_runs(self) -> list[RunRecord]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM runs ORDER BY created_at DESC")
            return [_row_to_run(r) for r in await cur.fetchall()]


def _row_to_run(row: aiosqlite.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        goal=row["goal"] or "",
        artifact_id=row["artifact_id"],
        workflow_id=row["workflow_id"],
        params=json.loads(row["params"] or "{}"),
        outputs=json.loads(row["outputs"] or "{}"),
        result=json.loads(row["result"] or "{}"),
        evidence_dir=row["evidence_dir"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


registry = Registry()

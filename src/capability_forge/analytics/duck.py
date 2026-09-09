from __future__ import annotations

from pathlib import Path

import duckdb

from capability_forge.config import settings


def stability_report(evidence_dir: Path | None = None) -> list[dict]:
    """Query JSONL evidence files in-process. Registry stays in SQLite."""
    root = evidence_dir or settings.evidence_dir
    pattern = str(root / "replay-*" / "events.jsonl")
    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(
            """
            SELECT
              json_extract_string(data, '$.artifact_id') AS artifact_id,
              kind,
              count(*) AS events
            FROM read_json_auto(?)
            GROUP BY 1, 2
            ORDER BY events DESC
            """,
            [pattern],
        ).fetchall()
        return [{"artifact_id": r[0], "kind": r[1], "events": r[2]} for r in rows]
    except Exception:
        # Empty directory / no files yet is a valid state.
        return []
    finally:
        con.close()


def replay_outcomes(evidence_dir: Path | None = None) -> list[dict]:
    root = evidence_dir or settings.evidence_dir
    pattern = str(root / "replay-*" / "result.json")
    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(
            """
            SELECT
              artifact_id,
              kind,
              count(*) AS n
            FROM read_json_auto(?)
            GROUP BY 1, 2
            """,
            [pattern],
        ).fetchall()
        return [{"artifact_id": r[0], "kind": r[1], "n": r[2]} for r in rows]
    except Exception:
        return []
    finally:
        con.close()

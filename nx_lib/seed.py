"""INT-only synthetic data seeding for tables nexora only *reads*.

Some tables are filled in production by collectors that live outside the repo
and run on Task Scheduler -- nexora only ever SELECTs from them. On INT those
collectors are usually unscheduled, so the table is empty or months stale and a
feature that consumes it cannot be verified: you cannot tell a broken query
from an empty table. The seeders here fill that gap with plausible data.

Two entry points share this module: ``scripts/seed-int-db.py`` (CLI) and the
admin overview's *Seed INT data* / *Clear seed* buttons
(``nx_lib/views/admin/seed.py``).

**Every seeded row is tracked.** A seed run records the exact keys of the rows
it wrote in ``dbo.SeedRuns`` (NexoraDB, migration 0141), and clearing deletes
those rows and nothing else. Seeding replaces the seeder's own earlier rows and
never touches rows the real collector wrote. Rows written by the pre-0141 CLI
(which deleted whole windows) are not tracked and must be cleaned once by hand.

Guards: ``seed_refusal()`` refuses unless ENVIRONMENT=INT and the resolved SQL
server does not look like production. The check is on the resolved VALUE, never
on the variable name -- ``DB_SERVER_PRD`` is called that in every env file but
holds the INT server on INT. Never add a bypass.
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text


class SeedRefusedError(RuntimeError):
    """Raised when a seed or clear must not run (wrong environment, no data to
    extrapolate from, unknown seeder)."""


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


def seed_refusal() -> str | None:
    """Why seeding must not run here, or None when it may.

    INT only, and the resolved server must not carry a prd/prod tag. The
    statistics DB name must be set because every seeder so far writes there.
    """
    env = os.environ.get("ENVIRONMENT")
    if env != "INT":
        return f"ENVIRONMENT is {env!r}, expected 'INT'"

    from nx_lib import config as cfg

    server = cfg.DB_SERVER_PRD or ""
    if not server:
        return "DB_SERVER_PRD is unset -- is env/INT.env present?"
    if any(tag in server.lower() for tag in ("prd", "prod")):
        return f"resolved server {server!r} looks like production"
    if not cfg.DB_STATISTICS:
        return "DB_STATISTICS is unset"
    return None


def _ensure_allowed() -> None:
    reason = seed_refusal()
    if reason:
        raise SeedRefusedError(f"refusing to seed: {reason}")


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


@dataclass
class SeedReport:
    seeder: str
    days: int
    applied: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    inserted: int = 0
    cleared_rows: int = 0
    cleared_runs: int = 0
    run_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeder": self.seeder,
            "days": self.days,
            "applied": self.applied,
            "planned": len(self.rows),
            "inserted": self.inserted,
            "cleared_rows": self.cleared_rows,
            "cleared_runs": self.cleared_runs,
            "run_id": self.run_id,
            "summary": self.summary,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# backlog-history seeder
# --------------------------------------------------------------------------- #

_BACKLOG_TABLE = "dbo.BacklogHistory"


def _known_pairs() -> list[tuple[str, ...]]:
    """(ClientName, ProcessName) pairs from dbo.ProcessSources -- the registry the
    dashboard resolves against. [] if NexoraDB is unreachable."""
    try:
        from nx_lib.db import engine_nexora_db

        with engine_nexora_db.connect() as c:
            return [
                tuple(str(r[0]).split(".", 1))
                for r in c.execute(text("SELECT DISTINCT ProcessName FROM dbo.ProcessSources"))
                if r[0] and "." in str(r[0])
            ]
    except Exception:
        return []


def _live_backlog_by_pair(notes: list[str]) -> dict[str, int]:
    """{"<client>.<process>".casefold(): count} from the live Octo runtime, via
    the same total_backlog_count() the dashboard KPI uses.

    Empty dict if the runtime is unreachable -- the caller then falls back to
    the stored snapshot, because a seeding tool must never be the thing that
    fails a dev box. total_backlog_count reads current_app, so an app context
    is pushed when the caller (the CLI) has none.
    """
    try:
        from flask import has_app_context

        from nx_lib.workitem_sources import total_backlog_count
    except Exception as e:
        notes.append(f"live backlog unavailable: {e}")
        return {}

    def _collect() -> dict[str, int]:
        out: dict[str, int] = {}
        for client, process in _known_pairs():
            try:
                out[f"{client}.{process}".casefold()] = total_backlog_count([(client, process)])
            except Exception:
                continue
        return out

    try:
        if has_app_context():
            return _collect()
        from nx_lib import create_app

        with create_app().app_context():
            return _collect()
    except Exception as e:
        notes.append(f"live backlog unavailable: {e}")
        return {}


def random_walk(today: int, days: int, rng: random.Random, pull: float = 0.15) -> list[int]:
    """``days`` daily counts, index 0 = today = ``today``, walking backwards.

    Mean-reverting, not a pure geometric walk: compounding uniform(0.90, 1.11)
    over a 90-day window drifts to 0 or to many times the base, which is as
    useless for verification as an empty table. The pull-back keeps the series
    in a plausible band while still wandering. Raise ``pull`` for a flatter line.
    """
    count = max(1, int(today or 1))
    base = count
    walk = [count]
    for _ in range(days - 1):
        drifted = count * rng.uniform(0.90, 1.11)
        count = max(0, int(round(drifted * (1 - pull) + base * pull)))
        walk.append(count)
    return walk


def plan_backlog_history(days: int, rng: random.Random, report: SeedReport) -> None:
    """Fill ``report.rows`` with one 20:00 snapshot per day per (client, process),
    random-walked backwards from today's real backlog so today's point equals
    the live value. Writes nothing.

    Owned in production by ops/backlog_history/backlog_history.py (every 30 min
    on Task Scheduler, never scheduled on INT). The dashboard backlog trend
    reads this table; without rows it draws nothing.

    ClientName/ProcessName are written EXACTLY as Octo spells them -- display
    cased ('Privera'), not the lower-cased dbo.ProcessSources spelling. The
    mismatch is real and the readers casefold to bridge it; seeding the
    lower-cased form would hide that.
    """
    from nx_lib.db import engine_statistics_db

    # The (client, process, source) rows come from the last stored snapshot,
    # but their MAGNITUDE comes from the live runtime -- the stored counts can
    # be months old, and seeding from them puts the synthetic history on a
    # different scale from today's real backlog (a cliff in the sparkline).
    with engine_statistics_db.connect() as conn:
        seeds = [
            (r[0], r[1], r[2], r[3])
            for r in conn.execute(
                text(
                    f"""
                    SELECT b.ClientName, b.ProcessName, b.SourceCode, b.BacklogCount
                    FROM {_BACKLOG_TABLE} b
                    JOIN (SELECT ClientName, ProcessName, MAX(SnapshotAt) AS MaxAt
                          FROM {_BACKLOG_TABLE} GROUP BY ClientName, ProcessName) m
                      ON m.ClientName = b.ClientName
                     AND m.ProcessName = b.ProcessName
                     AND m.MaxAt = b.SnapshotAt
                    """
                )
            )
        ]
    if not seeds:
        raise SeedRefusedError(
            f"{_BACKLOG_TABLE} is completely empty -- run the collector once "
            "(python ops/backlog_history/backlog_history.py --once) so there "
            "is a real shape to extrapolate from"
        )

    live = _live_backlog_by_pair(report.notes)
    report.notes.append(f"live runtime backlog resolved for {len(live)} pair(s)")
    evening = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
    for client, process, source, base in seeds:
        # Live count wins when the runtime knows this pair; the stored snapshot
        # is only the fallback. Casefolded because BacklogHistory carries
        # Octo's display casing and ProcessSources does not.
        today = live.get(f"{client}.{process}".casefold())
        origin = "live" if today is not None else "stored"
        if today is None:
            today = base
        walk = random_walk(today, days, rng)
        drift = "" if origin == "stored" or base == walk[0] else f"  (stored said {base})"
        report.summary.append(f"{client}.{process}  [{source}]  today={walk[0]} ({origin}){drift}")
        for offset, value in enumerate(walk):
            report.rows.append(
                {
                    "a": (evening - timedelta(days=offset)).isoformat(sep=" "),
                    "s": source,
                    "c": client,
                    "p": process,
                    "n": value,
                }
            )
    report.summary.insert(
        0, f"{len(seeds)} (client, process) pairs x {days} days = {len(report.rows)} rows"
    )


_BACKLOG_INSERT = text(
    f"INSERT INTO {_BACKLOG_TABLE} "
    "(SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount) "
    "VALUES (CAST(:a AS DATETIME2(0)), :s, :c, :p, :n)"
)

# Every column is part of the key: a seeded row is only ever deleted when it
# still looks exactly like what was written. SnapshotAt is bound as an ISO
# string and cast server-side -- the legacy ODBC driver cannot bind dates.
_BACKLOG_DELETE = text(
    f"DELETE FROM {_BACKLOG_TABLE} "
    "WHERE SnapshotAt = CAST(:a AS DATETIME2(0)) "
    "AND ((:s IS NULL AND SourceCode IS NULL) OR SourceCode = :s) "
    "AND ClientName = :c AND ProcessName = :p AND BacklogCount = :n"
)


def write_backlog_history(rows: list[dict[str, Any]]) -> int:
    from nx_lib.db import engine_statistics_db

    if not rows:
        return 0
    with engine_statistics_db.begin() as conn:
        conn.execute(_BACKLOG_INSERT, rows)
    return len(rows)


def delete_backlog_history(rows: list[dict[str, Any]]) -> int:
    from nx_lib.db import engine_statistics_db

    if not rows:
        return 0
    deleted = 0
    with engine_statistics_db.begin() as conn:
        # One statement per key so the count is exact; a few hundred rows.
        for row in rows:
            deleted += conn.execute(_BACKLOG_DELETE, row).rowcount or 0
    return deleted


@dataclass(frozen=True)
class Seeder:
    name: str
    table: str
    doc: str
    plan: Callable[[int, random.Random, SeedReport], None]
    write: Callable[[list[dict[str, Any]]], int]
    delete: Callable[[list[dict[str, Any]]], int]


SEEDERS: dict[str, Seeder] = {
    "backlog-history": Seeder(
        name="backlog-history",
        table=_BACKLOG_TABLE,
        doc="dbo.BacklogHistory: one 20:00 snapshot per day per (client, process)",
        plan=plan_backlog_history,
        write=write_backlog_history,
        delete=delete_backlog_history,
    ),
}


# --------------------------------------------------------------------------- #
# Run ledger (dbo.SeedRuns, NexoraDB)
# --------------------------------------------------------------------------- #


def list_runs() -> list[dict[str, Any]]:
    """Tracked seed runs, newest first, without their key blobs."""
    from nx_lib.db import engine_nexora_db

    with engine_nexora_db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT RunID, Seeder, TargetTable, Days, RowsWritten, SeededAt, SeededBy "
                "FROM dbo.SeedRuns ORDER BY SeededAt DESC, RunID DESC"
            )
        ).fetchall()
    return [
        {
            "run_id": r[0],
            "seeder": r[1],
            "table": r[2],
            "days": r[3],
            "rows": r[4],
            "seeded_at": r[5].isoformat(sep=" ", timespec="seconds")
            if isinstance(r[5], datetime)
            else str(r[5]),
            "seeded_by": r[6],
        }
        for r in rows
    ]


def _record_run(report: SeedReport, seeder: Seeder, seeded_by: str | None) -> int:
    from nx_lib.db import engine_nexora_db

    with engine_nexora_db.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO dbo.SeedRuns (Seeder, TargetTable, Days, RowsWritten, RowKeys, SeededBy) "
                "OUTPUT INSERTED.RunID "
                "VALUES (:seeder, :tbl, :days, :n, :keys, :by)"
            ),
            {
                "seeder": seeder.name,
                "tbl": seeder.table,
                "days": report.days,
                "n": len(report.rows),
                "keys": json.dumps(report.rows, separators=(",", ":")),
                "by": seeded_by,
            },
        ).fetchone()
    return int(row[0]) if row else 0


def clear_seeds(*, seeder: str | None = None) -> dict[str, int]:
    """Delete every row a tracked seed run wrote (all seeders, or one), then
    the run records. Real collector rows are untouched by construction: only
    keys recorded at seed time are deleted, and only when the row still matches
    them exactly.

    Returns {"runs": n, "rows": n}.
    """
    _ensure_allowed()
    if seeder is not None and seeder not in SEEDERS:
        raise SeedRefusedError(f"unknown seeder {seeder!r}")

    from nx_lib.db import engine_nexora_db

    where = "WHERE Seeder = :seeder" if seeder else ""
    params = {"seeder": seeder} if seeder else {}
    with engine_nexora_db.connect() as conn:
        runs = conn.execute(
            text(f"SELECT RunID, Seeder, RowKeys FROM dbo.SeedRuns {where}"), params
        ).fetchall()

    rows_deleted = 0
    runs_deleted = 0
    for run_id, name, keys in runs:
        spec = SEEDERS.get(name)
        if spec is not None:
            rows_deleted += spec.delete(json.loads(keys or "[]"))
        # A run for a seeder that no longer exists cannot be undone here; drop
        # the record anyway so the ledger does not carry it forever.
        with engine_nexora_db.begin() as conn:
            conn.execute(text("DELETE FROM dbo.SeedRuns WHERE RunID = :id"), {"id": run_id})
        runs_deleted += 1
    return {"runs": runs_deleted, "rows": rows_deleted}


def run_seed(
    what: str,
    days: int,
    *,
    apply_it: bool,
    rng: random.Random | None = None,
    seeded_by: str | None = None,
) -> SeedReport:
    """Plan (and with ``apply_it`` write) one seeder's rows.

    Applying first clears this seeder's earlier tracked runs, so re-seeding
    replaces rather than stacks, then records the new run BEFORE inserting --
    a crash mid-insert still leaves a run whose clear removes whatever landed.
    """
    _ensure_allowed()
    spec = SEEDERS.get(what)
    if spec is None:
        raise SeedRefusedError(f"unknown seeder {what!r}")
    if days < 2:
        raise SeedRefusedError("days must be at least 2")

    report = SeedReport(seeder=what, days=days, applied=apply_it)
    spec.plan(days, rng or random.Random(), report)
    if not apply_it:
        return report

    cleared = clear_seeds(seeder=what)
    report.cleared_rows = cleared["rows"]
    report.cleared_runs = cleared["runs"]
    report.run_id = _record_run(report, spec, seeded_by)
    report.inserted = spec.write(report.rows)
    return report

"""Seed the INT databases with plausible synthetic data for local development.

For tables nexora only ever *reads* — filled in production by an out-of-repo
collector on Task Scheduler — INT is often empty or months stale, which makes a
feature impossible to verify: you cannot tell a broken query from an empty
table. This script fills those gaps.

It is a DEV TOOL. It refuses to run unless ENVIRONMENT=INT and the resolved SQL
server does not look like production. Never point it at PROD: the real
collectors own these tables there.

Usage:
    python scripts/seed-int-db.py                       # dry run, shows the plan
    python scripts/seed-int-db.py --yes                 # actually write
    python scripts/seed-int-db.py --what backlog-history --days 30 --yes
    python scripts/seed-int-db.py --list

Each seeder is idempotent: it deletes the window it is about to write, so
re-running replaces rather than stacks.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --------------------------------------------------------------------------- #
# Guards. Not optional: this writes to a shared database.
# --------------------------------------------------------------------------- #


def _refuse(msg):
    sys.exit(f"refusing to seed: {msg}")


def check_environment():
    """Returns (server, statistics_db). Exits unless we are clearly on INT.

    Note the trap this guards against: the env var is named DB_SERVER_PRD in
    every environment file, but on INT it holds the INT server (INTSQL01). So
    the check is on the resolved VALUE, never on the variable's name.
    """
    env = os.environ.get("ENVIRONMENT")
    if env != "INT":
        _refuse(f"ENVIRONMENT is {env!r}, expected 'INT'")

    from nx_lib import config as cfg

    server = cfg.DB_SERVER_PRD or ""
    if not server:
        _refuse("DB_SERVER_PRD is unset — is env/INT.env present?")
    if any(tag in server.lower() for tag in ("prd", "prod")):
        _refuse(f"resolved server {server!r} looks like production")
    if not cfg.DB_STATISTICS:
        _refuse("DB_STATISTICS is unset")
    return server, cfg.DB_STATISTICS


# --------------------------------------------------------------------------- #
# Seeders
# --------------------------------------------------------------------------- #


def seed_backlog_history(days, apply_it):
    """dbo.BacklogHistory: one 20:00 snapshot per day per (client, process).

    Random-walked backwards from today's real backlog, so today's point equals
    the live value.

    Owned in production by ops/backlog_history/backlog_history.py, which runs
    every 30 min on Task Scheduler and was never scheduled on INT. The dashboard
    backlog trend reads this table; without rows it draws nothing.

    ClientName/ProcessName are written EXACTLY as Octo spells them — display
    cased ('Privera'), not the lower-cased dbo.ProcessSources spelling
    ('privera.02_Posteingang'). The mismatch is real and the readers casefold
    to bridge it; seeding the lower-cased form would hide that.
    """
    from sqlalchemy import text

    from nx_lib.db import engine_statistics_db

    conn = engine_statistics_db.connect()
    try:
        # Start from whatever the last real snapshot said, so the synthetic
        # history lands in the right order of magnitude per process. Falls back
        # to the live process list if the table is completely empty.
        seeds = [
            (r[0], r[1], r[2], r[3])
            for r in conn.execute(
                text(
                    """
                    SELECT b.ClientName, b.ProcessName, b.SourceCode, b.BacklogCount
                    FROM dbo.BacklogHistory b
                    JOIN (SELECT ClientName, ProcessName, MAX(SnapshotAt) AS MaxAt
                          FROM dbo.BacklogHistory GROUP BY ClientName, ProcessName) m
                      ON m.ClientName = b.ClientName
                     AND m.ProcessName = b.ProcessName
                     AND m.MaxAt = b.SnapshotAt
                    """
                )
            )
        ]
        if not seeds:
            _refuse(
                "dbo.BacklogHistory is completely empty — run the collector once "
                "(python ops/backlog_history/backlog_history.py --once) so there "
                "is a real shape to extrapolate from"
            )

        midnight = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
        rows = []
        for client, process, source, base in seeds:
            count = max(1, int(base or 1))
            # Walk backwards from today so today's point equals the real value.
            walk = [count]
            for _ in range(days - 1):
                count = max(0, int(count * random.uniform(0.90, 1.11)))
                walk.append(count)
            for offset, value in enumerate(walk):
                rows.append(
                    {
                        "a": midnight - timedelta(days=offset),
                        "s": source,
                        "c": client,
                        "p": process,
                        "n": value,
                    }
                )

        print(f"  {len(seeds)} (client, process) pairs x {days} days = {len(rows)} rows")
        for client, process, source, base in seeds:
            print(f"    {client}.{process}  [{source}]  today={base}")

        if not apply_it:
            return len(rows)

        # Idempotent: clear the window first, so re-running replaces.
        deleted = conn.execute(
            text(
                "DELETE FROM dbo.BacklogHistory "
                "WHERE SnapshotAt >= DATEADD(day, :d, CAST(GETDATE() AS DATE))"
            ),
            {"d": -(days - 1)},
        ).rowcount
        conn.execute(
            text(
                "INSERT INTO dbo.BacklogHistory "
                "(SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount) "
                "VALUES (:a, :s, :c, :p, :n)"
            ),
            rows,
        )
        conn.commit()
        print(f"  deleted {deleted} existing rows in the window, inserted {len(rows)}")
        return len(rows)
    finally:
        conn.close()


SEEDERS = {
    "backlog-history": seed_backlog_history,
}


# --------------------------------------------------------------------------- #


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--what",
        default="backlog-history",
        choices=sorted(SEEDERS),
        help="which seeder to run (default: backlog-history)",
    )
    ap.add_argument("--days", type=int, default=14, help="days of history (default: 14)")
    ap.add_argument("--yes", action="store_true", help="actually write; without it, dry run")
    ap.add_argument("--list", action="store_true", help="list seeders and exit")
    ap.add_argument("--seed", type=int, help="RNG seed, for a reproducible walk")
    args = ap.parse_args()

    if args.list:
        for name, fn in sorted(SEEDERS.items()):
            print(f"{name:20s} {(fn.__doc__ or '').strip().splitlines()[0]}")
        return 0

    if args.days < 2:
        _refuse("--days must be at least 2")
    if args.seed is not None:
        random.seed(args.seed)

    server, stats_db = check_environment()
    mode = "WRITING" if args.yes else "dry run"
    print(f"{mode}: {args.what} -> {server} / {stats_db}  ({args.days} days)")

    SEEDERS[args.what](args.days, args.yes)

    if not args.yes:
        print("\ndry run - nothing written. Re-run with --yes to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Seed the INT databases with plausible synthetic data for local development.

Thin CLI over ``nx_lib/seed.py`` -- the same seeders the admin overview's
*Seed INT data* / *Clear seed* buttons run. See that module for what is
seeded, how every seeded row is tracked in dbo.SeedRuns, and the guards.

It is a DEV TOOL. It refuses to run unless ENVIRONMENT=INT and the resolved SQL
server does not look like production. Never point it at PROD: the real
collectors own these tables there.

Usage:
    python scripts/seed-int-db.py                       # dry run, shows the plan
    python scripts/seed-int-db.py --yes                 # actually write
    python scripts/seed-int-db.py --what backlog-history --days 30 --yes
    python scripts/seed-int-db.py --clear --yes         # delete every tracked seeded row
    python scripts/seed-int-db.py --list                # seeders and tracked runs

Seeding replaces the seeder's own earlier tracked rows, never the real
collector's; --clear deletes exactly the rows the tracked runs wrote.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--what", default="backlog-history", help="which seeder (default: backlog-history)"
    )
    ap.add_argument("--days", type=int, default=14, help="days of history (default: 14)")
    ap.add_argument("--yes", action="store_true", help="actually write; without it, dry run")
    ap.add_argument(
        "--clear", action="store_true", help="delete tracked seeded rows instead of seeding"
    )
    ap.add_argument("--list", action="store_true", help="list seeders and tracked runs, then exit")
    ap.add_argument("--seed", type=int, help="RNG seed, for a reproducible walk")
    args = ap.parse_args()

    from nx_lib import seed as seedlib

    if args.list:
        for name, spec in sorted(seedlib.SEEDERS.items()):
            print(f"{name:20s} {spec.doc}")
        try:
            runs = seedlib.list_runs()
        except Exception as e:  # ledger missing (migration 0141 not applied) or DB down
            print(f"\n(tracked runs unavailable: {e})")
            return 0
        print(f"\n{len(runs)} tracked run(s):")
        for r in runs:
            print(
                f"  #{r['run_id']:<5} {r['seeder']:18s} {r['rows']:>6} rows  {r['seeded_at']}  {r['seeded_by'] or ''}"
            )
        return 0

    if args.what not in seedlib.SEEDERS:
        sys.exit(f"unknown seeder {args.what!r}; --list shows the available ones")

    reason = seedlib.seed_refusal()
    if reason:
        sys.exit(f"refusing to seed: {reason}")

    from nx_lib import config as cfg

    mode = "WRITING" if args.yes else "dry run"

    if args.clear:
        print(f"{mode}: clear tracked seed runs on {cfg.DB_SERVER_PRD} / {cfg.DB_STATISTICS}")
        runs = seedlib.list_runs()
        for r in runs:
            print(f"  #{r['run_id']} {r['seeder']}  {r['rows']} rows  seeded {r['seeded_at']}")
        if not runs:
            print("  nothing tracked -- nothing to clear")
            return 0
        if not args.yes:
            print("\ndry run - nothing deleted. Re-run with --yes to apply.")
            return 0
        result = seedlib.clear_seeds()
        print(f"  deleted {result['rows']} rows from {result['runs']} run(s)")
        return 0

    if args.days < 2:
        sys.exit("refusing to seed: --days must be at least 2")

    print(f"{mode}: {args.what} -> {cfg.DB_SERVER_PRD} / {cfg.DB_STATISTICS}  ({args.days} days)")
    try:
        report = seedlib.run_seed(
            args.what,
            args.days,
            apply_it=args.yes,
            rng=random.Random(args.seed) if args.seed is not None else None,
            seeded_by="cli",
        )
    except seedlib.SeedRefusedError as e:
        sys.exit(str(e))

    for line in report.notes:
        print(f"  ({line})")
    for line in report.summary:
        print(f"  {line}")
    if args.yes:
        print(
            f"  cleared {report.cleared_rows} earlier seeded rows ({report.cleared_runs} run(s)), "
            f"inserted {report.inserted}, run #{report.run_id}"
        )
    else:
        print("\ndry run - nothing written. Re-run with --yes to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Freeze the Sydoc Controlling figures of the months Finance has already closed (#433).

Since 0147, closing a month in Sydoc Finance also freezes its Controlling
figures in dbo.ControllingMonthClose. Months Finance closed before that have
no Controlling snapshot and are served live; this script freezes them, the
way the close does. Months already frozen are skipped, so it can be re-run.

    .venv/Scripts/python.exe scripts/controlling-freeze-months.py --env PROD --dry-run
    .venv/Scripts/python.exe scripts/controlling-freeze-months.py --env PROD

A month whose BPS hours or Bexio invoices cannot be read is reported and
left live; the rest still freeze. Months before January 2025 (no BPS
history) are not on the Controlling page and are skipped.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--env", required=True, choices=("INT", "STAGING", "PROD"))
    ap.add_argument("--by", default="controlling-freeze-months.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.environ["ENVIRONMENT"] = args.env
    sys.path.insert(0, str(REPO_ROOT))
    # Imported only now: nx_lib.config reads ENVIRONMENT when it loads.
    from nx_lib.controlling import EARLIEST, month_key
    from nx_lib.views import controlling as cv
    from nx_lib.views import finance as fv
    from nx_main import app

    with app.test_request_context():
        closed = sorted(fv._closed_months())
        wanted = [k for k in closed if k >= month_key(*EARLIEST)]
        frozen = set(cv._frozen(wanted))
        todo = [k for k in wanted if k not in frozen]
        print(f"{args.env}: {len(closed)} closed in Finance, {len(todo)} to freeze")
        failures = 0
        for key in todo:
            if args.dry_run:
                print(f"  {key} would freeze")
                continue
            y, m = (int(x) for x in key.split("-"))
            if cv.close_month(y, m, args.by):
                print(f"  {key} frozen")
            else:
                failures += 1
                print(f"  {key} NOT frozen (see the log: a source was down)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

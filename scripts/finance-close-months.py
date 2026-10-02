"""Close the Sydoc Finance months that were invoiced before the page existed (#408).

Every month the page's picker offers is snapshotted into dbo.FinanceMonthClose,
exactly as the "Close month" button does, except the newest ended month
(accounting is still invoicing it) and the running one. Months already closed
are skipped, so the script can be re-run.

    .venv/Scripts/python.exe scripts/finance-close-months.py --env PROD --dry-run
    .venv/Scripts/python.exe scripts/finance-close-months.py --env PROD

--keep N leaves the newest N ended months open (default 1). --until YYYY-MM
closes up to and including that month instead. A month whose section cannot
be read is reported and left open; the rest still close. The snapshot labels
are rendered in --lang (default de), the language accounting reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--env", required=True, choices=("INT", "STAGING", "PROD"))
    ap.add_argument("--keep", type=int, default=1, help="newest ended months to leave open")
    ap.add_argument("--until", help="close up to and including this month (YYYY-MM)")
    ap.add_argument("--lang", default="de")
    ap.add_argument("--by", default="finance-close-months.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.environ["ENVIRONMENT"] = args.env
    sys.path.insert(0, str(REPO_ROOT))
    # Imported only now: nx_lib.config reads ENVIRONMENT when it loads.
    from nx_lib.finance import month_key, month_options
    from nx_lib.views import finance as fv
    from nx_main import app

    today = dt.date.today()
    ended = [
        (key, y, m) for key, y, m in month_options(today) if (y, m) < (today.year, today.month)
    ]
    months = [o for o in ended if o[0] <= args.until] if args.until else ended[args.keep :]
    months.sort()
    with app.test_request_context(headers={"Accept-Language": args.lang}):
        closed = fv._closed_months()
        print(f"{args.env}: {len(months)} month(s) to close, {months[0][0]} .. {months[-1][0]}")
        failures = 0
        for key, y, m in months:
            if key in closed:
                print(f"  {key} already closed")
                continue
            if args.dry_run:
                print(f"  {key} would close")
                continue
            error = fv.close_month(y, m, args.by)
            if error:
                failures += 1
                print(f"  {key} NOT closed: {error[0]}")
            else:
                print(f"  {key} closed")
        assert month_key(today.year, today.month) not in {k for k, _, _ in months}
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

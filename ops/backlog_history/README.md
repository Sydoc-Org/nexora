# Backlog-history collector

Standalone — no nexora code needed. Snapshots the current C+A backlog per
(source, client, process) from the Octo runtime DB (and MS02 Postgres when
configured) into `dbo.BacklogHistory` on the Statistics DB. `SnapshotAt` is
server-local time. Excluded (client, process) pairs live in the `EXCLUDED`
set at the top of `backlog_history.py`.

## Install (once, on the target server)

1. Copy this folder anywhere (e.g. `D:\sydoc\tools\backlog_history\`).
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in the credentials (names match the
   main nexora env files 1:1).
4. Smoke test: `python backlog_history.py --dry-run`

## Task Scheduler (every 30 minutes)

Program: `D:\sydoc\tools\py\python.exe`
Arguments: `D:\sydoc\tools\backlog_history\backlog_history.py --once`

The `dbo.BacklogHistory` table is created automatically on first run.

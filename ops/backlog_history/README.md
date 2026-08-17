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

## Logging & failure tickets

- Every run logs to `backlog_history.log` next to the script (rotating,
  1 MB × 3 backups).
- On failure (a source query or the Statistics-DB write) the run exits
  non-zero and opens ONE consolidated helpdesk ticket by mailing
  `TICKET_TO` (default `support.helpdesk@sydoc.ch`) via Microsoft Graph,
  using the same `GRAPH_*` ROPC creds as nexora. `TICKET_COOLDOWN_HOURS`
  (default 6, tracked in `last_ticket.txt`) stops a dead DB from raising a
  new ticket every 30 minutes. Leave `TICKET_TO` empty to disable
  ticketing — failures still log and still exit non-zero.

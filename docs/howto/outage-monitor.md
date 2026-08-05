# Outage monitor

`ops/outage_monitor.py` probes PROD from outside the Flask process and mails a
support ticket when something breaks. It exists because of the 2026-08-05
incident (issue #166): migration `0042` reached PROD ahead of its code, the
workitems list served a degraded-source banner and zero rows for roughly half a
day, and the only evidence anywhere was an `Invalid object name` error storm in
`var/logs/system/app.log` that nobody was watching. A user noticing the banner
was the detection mechanism.

## Quick start

```powershell
# probe everything and print what would be mailed — sends nothing, writes nothing
$env:ENVIRONMENT = "PROD"; python ops\outage_monitor.py --dry-run

# show the currently tracked components and any open incidents
python ops\outage_monitor.py --check
```

```
    ok  db:NexoraDB: 462 ms
    ok  db:OctoDB: 462 ms
    ok  http:site: https://nexora.sydoc.ch/nexora/: HTTP 200
    ok  octo:prd-dps.sydoc.ch: https://prd-dps.sydoc.ch/auth/connect/token: HTTP 200
  FAIL  log storm @ process_helpers:97: 30x in 15 min: nx_lib process_helpers:<n> Failed to load activity instances to ignore: ('<s>', "<s>")
[dry-run] would mail support.helpdesk@sydoc.ch: [nexora PROD] OUTAGE: log storm @ process_helpers:97
outage monitor: 11 probes, 1 event(s), 0 mail(s), 1 incident(s) open
```

## Why it runs outside the app

An in-app scheduler cannot report that the app is dead — which is the main case
this exists to catch. The monitor is a standalone script under `ops/` (a
directory that ships to the server; `scripts/` does not) driven by Windows Task
Scheduler on SYAPP01.

## What it probes

| Component | Probe | Catches |
|---|---|---|
| `db:<engine>` | `SELECT 1` via `ping_dbs_parallel`, 5s timeout | DB server down, credentials expired, network partition |
| `http:site` | `GET` on `OUTAGE_SITE_URL` | IIS down, app pool crashed, WSGI import error |
| `octo:<domain>` | `POST /auth/connect/token` | Octo vendor-side outage |
| `log storm @ <site>` | repeated `ERROR` signature in `app.log` | logic-level breakage while every connectivity probe stays green |

The log-storm probe is the one that would have caught the `0042` incident. It
reads the tail of `var/logs/system/app.log`, normalizes each `ERROR` message
into a signature (ids, GUIDs, quoted literals and numbers collapse, so the same
fault does not fragment into hundreds of distinct storms), and opens an incident
when one signature appears **10+ times in 15 minutes**.

On a **dev box** expect the log-storm probe to fire constantly: the unit suite
deliberately logs errors ("boom", "DB down", …) into the same `app.log`, so a
run right after `pytest` opens dozens of incidents. That is why `SUPPORT_MAIL`
defaults to unset — a dev box probes and prints but never mails.

The Octo probe deliberately does **not** call `nx_lib.octo.get_access_token` —
that memoizes the token in the Flask cache, so a monitor using it would report a
cached success while the vendor was down. A probe must always touch the network.

## Alert hygiene

A monitor that mails on every failed probe floods the support inbox the moment
anything flaps — the `ping_prdsrv` monitor once sent ~200 mails from a single
flapping link. Three guards, all in `nx_lib.outage.update_component`:

- **Fail threshold** — 2 consecutive bad probes (3 for the HTTP probe, since an
  IIS app-pool recycle can drop one request) before an incident opens. Log
  storms open on the first sighting: their 10-in-15-minutes window *is* the
  hysteresis, and waiting another poll only delays the mail.
- **Dedupe** — while an incident is open, further failures update the evidence
  and send nothing.
- **Min-hold** — an open incident cannot close until it has been open 30
  minutes. A component toggling every poll therefore produces exactly one
  outage mail and one recovery mail.

State lives in `var/outage-state.json` (written atomically) so a restart does not
re-alert on an incident that is already open. Closed components untouched for 7
days are pruned — only the dynamic log-storm keys ever go stale.

All components breaching in the same run batch into **one** mail: a single root
cause (a DB going down) trips every call site that touches it, and support wants
one ticket for that, not twenty. The subject names the first three components
and appends `(+N more)`; the body lists every one with its evidence.

## Configuration

Both keys go in `env/{ENVIRONMENT}.env` (see `env/*.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `SUPPORT_MAIL` | unset | Ticket recipient. **Unset means probe + log, never mail** — the correct setting for a dev box. |
| `OUTAGE_SITE_URL` | `https://nexora.sydoc.ch/nexora/` | URL the HTTP probe GETs. |

Mail goes out through the existing Microsoft Graph sender (`nx_lib/mail.py`), so
it needs the same `GRAPH_*` credentials the scheduled reports already use.

## Wiring on SYAPP01

A Task Scheduler task every 5 minutes (matching the hysteresis defaults):

```
Program:   D:\sydoc\tools\py\python.exe
Arguments: D:\sydoc\nexora\ops\outage_monitor.py
Start in:  D:\sydoc\nexora
Environment: ENVIRONMENT=PROD
```

The script always exits 0, even with incidents open — the alert is the mail, and
a non-zero exit would leave Task Scheduler showing a permanently failing task.

## Layout

- `nx_lib/outage.py` — pure logic: signature normalization, storm detection,
  hysteresis state machine, state persistence, mail rendering. Fully unit
  tested in `tests/unit/test_outage.py`.
- `ops/outage_monitor.py` — the probes and the orchestration.

Same split as `nx_lib/reporting/schedule.py` + `ops/run_scheduled_reports.py`:
the decisions are testable without a live PROD, the I/O is not.

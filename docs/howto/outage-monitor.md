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
| `api:v1` | unauthenticated `GET /api/v1/stats/today`, **401 is the pass** | the external API entry point being broken (bad rewrite rule, import error in `api_auth`) while every page still renders |
| `api:key` | `GET /api/test/v1/stats/today` with `OUTAGE_API_KEY` as Bearer | the key lookup / process scoping being broken -- the half `api:v1` cannot see |
| `octo:<domain>` | `POST /auth/connect/token` | Octo vendor-side outage |
| `graph:mail` | Graph ROPC token request | expired Graph credentials — which silently kill alert mail itself |
| `log storm @ <site>` | repeated `ERROR`/`CRITICAL` signature in `app.log` | logic-level breakage while every connectivity probe stays green |
| `warn storm @ <site>` | repeated `WARNING` signature in `app.log` | a fault that only warns -- the reporting catalog warned on every request for months, unwatched |

The two API probes are deliberately split. `api:v1` needs no credentials at all
(a 401 already proves routing reached `require_api_key` and it answered), so it
runs everywhere with zero setup. `api:key` covers what a 401 cannot -- the
`dbo.ApiKeys` lookup and the key's process scope -- and hits the `/api/test/v1`
twin so a poll every 5 minutes never touches the Statistics or Octo backends.
It skips itself when `OUTAGE_API_KEY` is unset, so no server is required to hold
a key before the code lands. To enable it: create a monitor-only key row in
`dbo.ApiKeys` and paste `OUTAGE_API_KEY=<raw key>` into that server's
`env/<ENV>.env` (`scripts/env-sync.py` will otherwise report it missing).

The Graph probe asks for a **token only**. Actually sending a message would be a
truer end-to-end check but would also drop mail in the mailbox every 5 minutes,
and a failing token is what kills alert mail anyway. The Graph probe skips
itself when its credentials are not configured for the environment, the same
way the MS02 engines do.

There used to be a `bexio:api` probe. It went with the archived invoices page
(#177): nothing in the app calls Bexio any more, so an alert on it would have
woken someone for a vendor no page depends on. Migration `0057` deletes its
`dbo.StatusComponents` row so it also stops rendering on the admin status page.

The log-storm probe is the one that would have caught the `0042` incident. It
reads the tail of `var/logs/system/app.log`, normalizes each message into a
signature (ids, GUIDs, quoted literals and numbers collapse, so the same fault
does not fragment into hundreds of distinct storms), and opens an incident when
one signature appears **10+ times in 15 minutes**.

`WARNING` is scanned as well, at its own much higher bar: **60+ in 15 minutes**
(4/minute sustained). Warnings are routine and errors are not, so one threshold
for both would either drown the mailbox or keep missing faults that never raise.
A warning storm is labelled `warn storm @ <site>` rather than `log storm`, and a
signature seen at both levels is judged at the *error* bar -- one stray WARNING
must not raise an error storm's threshold.

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

## The status page (`/admin/status`)

Every run is also mirrored into two NexoraDB tables (migration `0055`), which is
all the admin status page reads:

| Table | Holds |
|---|---|
| `dbo.StatusComponents` | one row per fixed component — current state, detail, `FirstSeenAt`, `LastCheckedAt`, `LastOkAt`; overwritten each run |
| `dbo.StatusIncidents` | append-only outage log; `EndedAt IS NULL` means still open |
| `dbo.StatusSamples` | one latency sample per fixed component per run (migration `0071`), behind the status page's response-time sparklines; pruned to 14 days by the monitor itself |

Log-storm components appear **only** in `StatusIncidents`. Their keys are content
hashes of an error signature, so a permanent row per signature ever seen would
turn the component grid into a junk drawer.

The mirror write is best-effort and wrapped in `try/except`: NexoraDB being down
is one of the things this monitor exists to report, so a failed write prints a
warning and the alert mail still goes out. `var/outage-state.json` — not the DB —
remains the working state for hysteresis, for the same reason.

The page (`nx_lib/views/admin.py` → `admin_status_view`, permission
`admin.status.view`) never probes on page load. The question it answers is "what
has been true since yesterday evening", which a request-scoped ping cannot. The
flip side is that it is only as fresh as the scheduled task: when nothing has
been recorded for **15 minutes** the page reports the data as stale instead of
rendering a reassuring all-green grid.

Component states are `operational`, `degraded` (probes failing but not yet past
the fail threshold — the window where the monitor is deliberately silent) and
`outage`. An active `MaintenanceBanner` window takes over the headline only;
component states stay factual, so real breakage during a maintenance window is
still visible.

On INT there is no scheduled task, so the page stays empty until you run the
monitor by hand:

```powershell
$env:ENVIRONMENT = "INT"; python ops\outage_monitor.py
```

A future public status page for clients has to live outside the app to survive a
full app outage. It should read these same two tables rather than growing a
second data model.

## Configuration

Both keys go in `env/{ENVIRONMENT}.env` (see `env/*.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `SUPPORT_MAIL` | unset | Ticket recipient. **Unset means probe + log, never mail** — the correct setting for a dev box. |
| `OUTAGE_SITE_URL` | `https://nexora.sydoc.ch/nexora/` | URL the HTTP probe GETs. |

Mail goes out through the existing Microsoft Graph sender (`nx_lib/mail.py`), so
it needs the same `GRAPH_*` credentials the scheduled reports already use.

## Wiring on SYAPP01

`ops/outage-monitor-task.xml` is a ready-to-import Task Scheduler definition
(every 5 minutes, matching the hysteresis defaults). Import it in an elevated
shell on SYAPP01:

```powershell
schtasks /create /xml "D:\sydoc\nexora\ops\outage-monitor-task.xml" /tn "\sydoc\nexora\Outage Monitor"

# run it once immediately and read the result
schtasks /run /tn "\sydoc\nexora\Outage Monitor"
Get-Content D:\sydoc\nexora\var\logs\system\outage_monitor.log
```

Or: Task Scheduler → **Import Task…** → pick the XML.

Three things in that XML are deliberate:

- **Runs as `SYSTEM`** (`S-1-5-18`), not a named account, so there is no stored
  password to expire. Nothing in the monitor uses Windows auth — the DB
  connections use the SQL logins from `env/PROD.env` and Graph uses its own
  credentials. To run it as a domain account instead, change `<UserId>` and add
  `<LogonType>Password</LogonType>`.
- **Launches via `cmd.exe`**, because Task Scheduler XML has no way to set an
  environment variable and the app needs `ENVIRONMENT=PROD`. Note the missing
  space in `set ENVIRONMENT=PROD&&` — `PROD &&` would set the value to `"PROD "`
  with a trailing space, and `IS_PROD` would silently be false.
- **Redirects to `var/logs/system/outage_monitor.log` with `>`, not `>>`**, so
  the file only ever holds the last run and cannot grow unbounded. The durable
  record of an incident is the mail plus `var/outage-state.json`, not this file.

The script always exits 0, even with incidents open — the alert is the mail, and
a non-zero exit would leave Task Scheduler showing a permanently failing task.

## Layout

- `nx_lib/outage.py` — pure logic: signature normalization, storm detection,
  hysteresis state machine, state persistence, mail rendering. Fully unit
  tested in `tests/unit/test_outage.py`.
- `ops/outage_monitor.py` — the probes and the orchestration.
- `ops/outage-monitor-task.xml` — importable Task Scheduler definition.

Same split as `nx_lib/reporting/schedule.py` + `ops/run_scheduled_reports.py`:
the decisions are testable without a live PROD, the I/O is not.

## Response-time sparklines

Every probe already measures how long it took -- the DB pings always carried it
in the detail line, and the HTTP/Graph/Octo probes now append ` (204 ms)` from
`requests`' own timing. `persist_run` parses that number back out and writes one
`dbo.StatusSamples` row per component per run, so `/admin/status` can draw 24
hourly buckets beside each component.

Three choices worth knowing before changing them:

* **Zero-based axis, scaled per component.** A DB ping at 158 ms and a Graph
  token at 310 ms are both normal, so one shared axis would flatten every line
  but the slowest; fitting each line to its own min..max instead would turn
  ordinary ±20% jitter into cliffs. Each component gets its own `0..max`.
* **Each bucket keeps its slowest sample, not the mean.** A five-minute stall is
  exactly what the graph exists to show; averaging twelve samples per hour
  erases it.
* **Gaps stay gaps.** A bucket with no sample renders as a break in the line.
  Interpolating would draw a healthy flat line straight through the window where
  the monitor itself was dead.

The pure helpers (`spark_series`, `spark_geometry` in `nx_lib/status.py`) do the
bucketing and the SVG coordinates, so the template does no arithmetic and both
are unit-tested. Retention is enforced by the monitor's own `DELETE` on every
run -- there is no separate cleanup job to schedule.

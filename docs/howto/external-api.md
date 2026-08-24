# External API v1 (machine-to-machine)

An in-app rendition of this reference lives at `/api-docs` (sidebar "API
Docs", permission `api.docs.view`) for internal staff and API clients'
portal accounts — this file stays the source of truth; keep both in sync.

Read-only JSON API for external clients, authenticated with per-client API
keys. Seven documented endpoints in v1. Code: routes in
`nx_lib/views/api_external.py`, auth in `nx_lib/api_auth.py`, KPI
computation shared with the dashboard (`compute_today_stats` /
`compute_avg_processing_time` / `compute_undelivered_count` /
`resolve_import_datetimes` in `nx_lib/views/dashboard.py`,
`total_backlog_count` in `nx_lib/workitem_sources.py`), the workitem
query/detail data shared with the Workitems overview page
(`_get_workitems_data` with a session-less `scope` + `_load_media_info` in
`nx_lib/views/workitems.py`), table created by
`sql/_migrations/NexoraDB/0038_create_api_keys.sql`.

## Base URLs

| Environment | Base URL |
|---|---|
| PROD | `https://nexora.sydoc.ch/nexora/api/v1` |
| Test sandbox | `https://nexora.sydoc.ch/nexora/api/test/v1` |
| INT (dev) | `http://127.0.0.1:8000/api/v1` |

The in-app `/api-docs` page shows only the PROD and test-sandbox rows —
external clients have no use for a `127.0.0.1` dev URL; it stays documented
here for staff.

PROD serves the app under the `/nexora` prefix via `PrefixMiddleware`; the
Flask routes themselves are registered unprefixed, so no code is
prefix-aware. The dev server binds port 8000 (`FLASK_RUN_PORT`).

Keys are **not** shared across environments: INT and PROD each run their own
NexoraDB (`NexoraDB_INT` vs `NexoraDB`), so `dbo.ApiKeys` is a separate table
per environment. A key issued on INT gets a uniform 401 against PROD, and
vice versa — same as an unknown key (no existence oracle). Issue a key
against each environment separately (see "Issuing a key" below).

## Quick start

One header, one GET — with a key in hand (see "Issuing a key" below) this
is the whole integration:

    curl -H "Authorization: Bearer TfNbeGaVwZUwSITZq0eDo5wRbXHnPTGyBg95Y5C8AAc" \
        https://nexora.sydoc.ch/nexora/api/v1/backlog

    {
      "datetime": "2026-08-04 09:15",
      "current_backlog": 154
    }

Same against a local dev server: `curl -H "Authorization: Bearer <key>"
http://127.0.0.1:8000/api/v1/backlog`. In PowerShell use `curl.exe` —
bare `curl` is an alias for `Invoke-WebRequest`, which spells the header
differently. No key or a wrong key returns
`401 {"error": "Invalid API key"}`.

## Authentication

Send the key as a Bearer token on every request:

    GET /api/v1/backlog
    Authorization: Bearer <api key>

Keys are per-client rows in `dbo.ApiKeys` (NexoraDB): only the SHA-256 hash
of the key is stored, plus a client code, an audit `Label`, a
comma-separated `ProcessList` scope (full `dbo.Statconfig.ProcessName`
values, e.g. `sydoc.05_PDBS`), an `Enabled` flag and `CreatedAt` /
`LastUsedAt` stamps.

### Issuing a key (v1: manual, dev-side)

`scripts/` is not deployed to prod, so run this from a dev clone:

    python scripts/new-api-key.py --client-code <code> --label "<who holds it>" --processes "<ProcessName>,<ProcessName>"

The script prints the raw token ONCE (hand it to the client over a secure
channel; it is not recoverable) and a ready-to-run `INSERT` for
`dbo.ApiKeys`. Execute the INSERT against the target NexoraDB (INT and/or
PROD) in SSMS.

### Revoking / rotating

    UPDATE dbo.ApiKeys SET Enabled = 0 WHERE Label = '<who holds it>';

Effective on the next request (the auth path has no cache). A disabled key
answers exactly like an unknown key (401 `Invalid API key`) — deliberately
indistinguishable, so a leaked/revoked key confirms nothing. Rotation =
issue a new key, then disable the old row.

## GET /api/v1/backlog

The dashboard's "Current Backlog" KPI number, scoped to the key's
`ProcessList`:

    {
      "datetime": "2026-08-04 09:15",
      "current_backlog": 154
    }

- `datetime` — **server-local** timestamp (`YYYY-MM-DD HH:MM`) the count was
  computed at.
- `current_backlog` — the summed C+A backlog count across all active
  workitem sources for the key's `ProcessList`. The response deliberately
  does **not** echo the process list — scoping happens once, at key
  issuance, not per response. An empty scope returns `0`. Not cached: every
  call computes fresh numbers.

## GET /api/v1/avg_processing_time

The dashboard's "Avg Processing Time" KPI number, scoped to the key's
`ProcessList`:

    {
      "avg_minutes": 4.2,
      "avg_display": "4min"
    }

- `avg_minutes` — average minutes between import and export among rows
  exported **today** (server-local), rounded to 1 decimal; `null` if no
  matching rows exist yet today.
- `avg_display` — the same figure pre-formatted for display: `"<n>s"` under a
  minute, `"<n>min"` under an hour, `"<n>h"` above (one decimal), or `"—"`
  when `avg_minutes` is `null`.

Like `/backlog`, the response does not echo the process list — scoping
happens at key issuance. An empty scope returns `null`/`"—"`.

**Calculation**, verified against `compute_avg_processing_time` (the same
function backing the dashboard card, so this is deliberately "the same
number as on the Dashboard"): for each `Statconfig` row (each represents one
process/table), take `AVG(export_column - import_column)` in seconds among
rows whose export date is today and whose export is after its import; then
average those per-row-source averages together as a **plain mean, not
weighted by row count** — a source with 2000 rows counts the same as one
with 2. The MS02 client contributes one more such average from its own
table, folded into the same mean. Not cached: every call computes fresh
numbers.

## GET /api/v1/workitems

The **query** endpoint (issue #197): find workitems with the same filters
the Workitems overview page offers, scoped to the key's `ProcessList`. The
typical flow is query → take an `id` → fetch its document details from
`/api/v1/workitems/<id>` below. Example — look up an invoice number:

    curl -H "Authorization: Bearer <key>" \
        "https://nexora.sydoc.ch/nexora/api/v1/workitems?field=invoicenr&value=INV-2026-00123&op=eq"

    {
      "count": 1,
      "page": 1,
      "per_page": 40,
      "total_pages": 1,
      "workitems": [
        {
          "id": 78214,
          "status": "Done",
          "stage": "Delivery",
          "modified_at": "2026-08-04 10:02:11",
          "import_datetime": "2026-08-04 09:12:31"
        }
      ]
    }

Query parameters (all optional; invalid values return a `400` with a plain
English `error` string — nothing is silently coerced or ignored):

| Param | Meaning |
|---|---|
| `workitem_id` | workitem-id **prefix** match (`11` matches `11`, `110`, `1199`, ... but not `911`) |
| `status` | one of `Ready`, `In Progress`, `Done` |
| `stage` | one of `Import`, `Extraction`, `Validation`, `Delivery` |
| `start_date` / `end_date` | ISO datetime bounds on the last-modified timestamp; `start_date` is **inclusive**, `end_date` is **exclusive** |
| `process` | comma-joined subset of the key's `ProcessList` (default: all of it) |
| `field` / `value` / `op` / `comb` | repeated doc-field filter pairs, see below |
| `page` / `per_page` | paging; `per_page` accepts only `40`, `100`, `200`, `500`, `1000` (default `40`) |

Doc-field filters repeat in parallel: each `field`+`value` pair may carry an
`op` (`contains` default, `ncontains`, `eq`, `neq`, `startswith`,
`endswith`) and a `comb` (`and` default, `or`) joining it to the pairs
before it — at most **10 pairs** per request (`400` beyond). Field keys are
written **lowercase with no separators** (`invoicenr`, `esrreference`,
`grossamount`, …) — fetch your key's live list from
`GET /api/v1/workitems/fields` below; an unknown — or
sensitive — field key returns `400 {"error": "Unknown field '...'"}`
(sensitive doc-fields are never queryable with an API key), and a real
field mapped for none of your key's processes returns
`400 {"error": "Field '...' is not available for your process scope"}`
instead of silently matching nothing. The `LIKE`-family ops treat `%` and `_` in the
value as SQL wildcards (historical overview behaviour). Matches honour the
same per-process time window (`SearchConfig.TimeFilter`) as the overview
page's search — very old documents fall outside it.

Response rows: `id` feeds the detail call below, `modified_at` is the
runtime's last-touch timestamp, and `import_datetime` is looked up from the
Statistics DB where a process is mapped there (`null` otherwise). All
timestamps are **server-local**
`YYYY-MM-DD HH:MM:SS`. An empty `ProcessList` returns an empty page. If any
backing source fails, the whole call returns
`500 {"error": "Workitems backend unavailable"}` rather than a silently
partial page; a failing doc-field resolution instead fails **closed** to
zero matching rows (same guard as the overview), and a failed load of the
sensitive-field list also answers `500` on both workitem endpoints — this
surface never degrades to serving unfiltered data. Not cached.

## GET /api/v1/workitems/fields

The **discovery** endpoint for the query above: the field keys `?field=`
accepts **for your key's process scope**, as the server resolves them right
now. No parameters:

    curl -H "Authorization: Bearer <key>" \
        "https://nexora.sydoc.ch/nexora/api/v1/workitems/fields"

    {
      "fields": ["archiveboxno", "bankpk", "branch", "…", "invoicenr", "…"]
    }

Keys are lowercase with no separators. The list is config-driven and
**scoped**: only fields mapped for at least one process in the key's
`ProcessList` appear, **minus sensitive fields** — so prefer fetching it
over hard-coding. On `/workitems`, a key absent from the global config
answers `400 Unknown field`; a real field outside your scope answers
`400 Field '...' is not available for your process scope`. A failed config
lookup returns `500` (fail closed), never a partial list. An empty
`ProcessList` returns an empty list. Not cached.

## GET /api/v1/stages

The count of workitems currently in each stage, scoped to the key's
`ProcessList`. No parameters:

    curl -H "Authorization: Bearer <key>" \
        "https://nexora.sydoc.ch/nexora/api/v1/stages"

    {
      "datetime": "2026-08-18 09:15",
      "stages": {
        "Import": 12,
        "Extraction": 4,
        "Validation": 9,
        "Delivery": 131
      }
    }

- `datetime` — **server-local** timestamp (`YYYY-MM-DD HH:MM`) the counts
  were computed at.
- `stages` — one integer per stage (`Import`, `Extraction`, `Validation`,
  `Delivery`): how many workitems are currently in that stage across all
  active workitem sources for the key's `ProcessList`. Computed via the
  same path as a stage-filtered `/workitems` query, so the numbers always
  match it. A degraded source answers `500` instead of silently partial
  counts. An empty scope returns all zeros. Not cached: every call computes
  fresh numbers.

## GET /api/v1/workitems/&lt;id&gt;

The **detail** endpoint (issue #197): the document details the overview
row-expand shows — extracted field values and table values, no page images,
confidence or source locations:

    curl -H "Authorization: Bearer <key>" \
        "https://nexora.sydoc.ch/nexora/api/v1/workitems/78214"

    {
      "workitem_id": 78214,
      "detail": {
        "fields": {
          "InvoiceNumber": "INV-2026-00123",
          "InvoiceDate": "2026-08-01",
          "TotalAmount": "1234.50"
        },
        "tables": [
          {
            "title": "LineItems",
            "columns": ["Description", "Quantity", "Amount"],
            "rows": [
              [
                {"column": "Description", "value": "Widget"},
                {"column": "Quantity", "value": "2"},
                {"column": "Amount", "value": "617.25"}
              ]
            ]
          }
        ]
      }
    }

No query parameters — the workitem is located within the key's process
scope automatically.

- `fields` — extracted field name → value, mapped through the same
  field-name mapping the overview uses; sensitive fields are stripped.
- `tables` — extracted table values; columns matching a sensitive field are
  stripped too.
- `404 {"workitem_id": ..., "detail": null}` — returned **uniformly** for an
  unknown id, an id outside the key's process scope, and a document the
  runtime backend can't load right now (no existence oracle; a transient
  runtime outage is indistinguishable from a bad id on this surface).

The workitem's entitlement is checked against the key's `ProcessList`
before any document fetch. Detail payloads are served from the same
short-lived cache the overview panel uses; the first hit on a cold workitem
fetches live from the runtime service and can take a few seconds.

## GET /api/v1/undelivered

The number of workitems **not delivered yet**: imported within the last
`days` days but with no export date so far, scoped to the key's
`ProcessList` (issue #196):

    curl -H "Authorization: Bearer <api key>" \
        "https://nexora.sydoc.ch/nexora/api/v1/undelivered?days=7"

    {
      "date": "2026-08-10",
      "days": 7,
      "undelivered": 42
    }

- `days` (**required** query param) — the import window in calendar days,
  counted back from today inclusive. Accepts **only `7` or `10`**; anything
  else (including a missing param) returns
  `400 {"error": "days must be 7 or 10"}`.
- `date` — the **server-local** calendar date the count refers to.
- `undelivered` — workitems whose import-date column falls within the window
  and whose export-date column is still `NULL`. Statconfig rows without an
  `ImportColumn` can't answer this metric and are skipped.

Like `/backlog`, the response does **not** echo the process list — scoping
happens once, at key issuance. An empty scope returns `0`. Not cached:
every call computes fresh numbers.

## Test sandbox (/api/test/v1)

Every `/api/v1/...` route has a `/api/test/v1/...` twin: same path suffix,
same Bearer-key auth, same response shape -- but the numbers are random, not
real KPI values. No backend DB queries happen at all, so it's safe to hit
repeatedly while building an integration. Use a real (enabled) API key, just
point at `/api/test/v1` instead of `/api/v1`:

    curl -H "Authorization: Bearer <key>" \
        https://nexora.sydoc.ch/nexora/api/test/v1/backlog

    {
      "datetime": "2026-08-04 09:15",
      "current_backlog": 289
    }

Same auth errors (401/429) apply. This convention holds for future v1
routes too -- a new `/api/v1/...` endpoint ships with its `/api/test/v1/...`
counterpart in the same change.

## Errors (JSON unless noted)

| Status | Body | Meaning |
|---|---|---|
| 400 | `{"error": "days must be 7 or 10"}` | `/undelivered` called with a missing or invalid `days` param |
| 400 | `{"error": "<plain-English validation message>"}` | `/workitems` called with an invalid filter param (unknown status/stage/op/comb/field, malformed date, bad paging, process outside the key's scope) |
| 401 | `{"error": "Missing or malformed Authorization header"}` | no/bad `Authorization: Bearer` header (`WWW-Authenticate: Bearer` set) |
| 401 | `{"error": "Invalid API key"}` | unknown **or disabled** key (uniform on purpose) |
| 404 | `{"error": "Not found"}` | wrong path under `/api/v1` (including a non-numeric `/workitems/<id>`) |
| 404 | `{"workitem_id": ..., "detail": null}` | `/workitems/<id>`: unknown id, id outside the key's scope, or the runtime backend can't load the document (uniform on purpose) |
| 405 | HTML (Flask default) | non-GET verb — the API is GET-only |
| 429 | HTML (flask-limiter default) | over 60 requests/minute |
| 500 | `{"error": "Stats backend unavailable"}` (`/avg_processing_time`, `/undelivered`) or `{"error": "Backlog backend unavailable"}` (`/backlog`) or `{"error": "Workitems backend unavailable"}` (`/workitems`, `/workitems/<id>`, `/stages`) or `{"error": "Internal server error"}` | backend query or server failure |
| 503 | `{"error": "Auth backend unavailable"}` | NexoraDB unreachable during auth (fail closed) |
| 503 | `{"error": "Maintenance", "maintenance": {...}}` | blocking maintenance window (global lockout) |

## Operational notes

- Rate limit: 60/min per source IP, checked BEFORE authentication (so
  brute-force key guessing is throttled too), enforced in-memory per worker
  process (see the TODO in `nx_lib/extensions.py`);
  `NEXORA_DISABLE_RATELIMIT=1` disables it (tests/e2e only).
- Every hit lands in the standard CSV request log
  (`var/logs/user/YYYYMMDDHH/nexora_logs.csv`) with empty user fields —
  a free audit trail; `dbo.ApiKeys.LastUsedAt` shows last successful auth.
- No session, no cookies, no CSRF (GET-only), no i18n — error strings are
  English by design (`_()` in these modules would drag in the pybabel
  cycle for machine-facing text).
- Monitored: `ops/outage_monitor.py` probes this API every 5 minutes and the
  result shows on `/admin/status` under **Application** — `api:v1`
  (unauthenticated, 401 is the pass) and, when `OUTAGE_API_KEY` holds a
  monitor-only key, `api:key` against `/api/test/v1/stats/today`. See
  `docs/howto/outage-monitor.md`.

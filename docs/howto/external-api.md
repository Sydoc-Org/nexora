# External API v1 (machine-to-machine)

Read-only JSON API for external clients, authenticated with per-client API
keys. One endpoint in v1. Code: routes in `nx_lib/views/api_external.py`,
auth in `nx_lib/api_auth.py`, KPI computation shared with the dashboard
(`compute_today_stats` in `nx_lib/views/dashboard.py`), table created by
`sql/_migrations/NexoraDB/0038_create_api_keys.sql`.

## Base URLs

| Environment | Base URL |
|---|---|
| PROD | `https://nexora.sydoc.ch/nexora/api/v1` |
| INT (dev server) | `http://127.0.0.1:8000/api/v1` |

PROD serves the app under the `/nexora` prefix via `PrefixMiddleware`; the
Flask routes themselves are registered unprefixed, so no code is
prefix-aware. The dev server binds port 8000 (`FLASK_RUN_PORT`).

## Quick start

One header, one GET — with a key in hand (see "Issuing a key" below) this
is the whole integration:

    curl -H "Authorization: Bearer TfNbeGaVwZUwSITZq0eDo5wRbXHnPTGyBg95Y5C8AAc" \
        https://nexora.sydoc.ch/nexora/api/v1/stats/today

    {
      "date": "2026-07-22",
      "imported_today": 123,
      "exported_today": 117,
      "processes": ["sydoc.05_PDBS"]
    }

Same against a local dev server: `curl -H "Authorization: Bearer <key>"
http://127.0.0.1:8000/api/v1/stats/today`. In PowerShell use `curl.exe` —
bare `curl` is an alias for `Invoke-WebRequest`, which spells the header
differently. No key or a wrong key returns
`401 {"error": "Invalid API key"}`.

## Authentication

Send the key as a Bearer token on every request:

    GET /api/v1/stats/today
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

## GET /api/v1/stats/today

The dashboard's "imported today" / "processed today" KPI numbers, scoped to
the key's `ProcessList`:

    {
      "date": "2026-07-14",
      "imported_today": 123,
      "exported_today": 117,
      "processes": ["sydoc.05_PDBS"]
    }

- `date` — the **server-local** calendar date the counts refer to (the
  underlying SQL uses `GETDATE()` / `CURRENT_DATE`).
- `imported_today` — documents whose import-date column is today.
- `exported_today` — documents whose export-date column is today (the
  dashboard's `processed_today` semantics, inherited verbatim — on the
  default T-SQL leg this counts export-today among rows also imported
  today).
- `processes` — the key's scope, echoed for debugging. An empty scope
  returns zeros with `"processes": []`. Not cached: every call computes
  fresh numbers.

## Errors (JSON unless noted)

| Status | Body | Meaning |
|---|---|---|
| 401 | `{"error": "Missing or malformed Authorization header"}` | no/bad `Authorization: Bearer` header (`WWW-Authenticate: Bearer` set) |
| 401 | `{"error": "Invalid API key"}` | unknown **or disabled** key (uniform on purpose) |
| 404 | `{"error": "Not found"}` | wrong path under `/api/v1` |
| 405 | HTML (Flask default) | non-GET verb — the API is GET-only |
| 429 | HTML (flask-limiter default) | over 60 requests/minute |
| 500 | `{"error": "Stats backend unavailable"}` or `{"error": "Internal server error"}` | stats query / server failure |
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

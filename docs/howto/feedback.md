# Feedback page

The `/feedback` page (profile dropdown → "Feedback", or Ctrl+K) is the
in-app way for a user to report a bug, ask a question, or suggest an idea —
before this existed, problems only got noticed when someone happened to
mention them (the incident that prompted this). It mails `SUPPORT_MAIL`
directly; there is **no ticket tracking in-app** — the mailbox is the queue,
deliberately.

## Mechanics

- Route + logic: `nx_lib/views/profile.py` (`feedback()` /
  `submit_feedback()`), same "all authenticated users, no dedicated
  permission code" family as `/appearance` and `/whats_new` — it's guarded
  by a bare session check, not `@require_permission`, and is absent from
  `page_visibility()` for the same reason those two are.
- The form posts to `POST /feedback/submit` via `fetch`
  (`templates/js/_feedback_js.html`), not a redirect+flash page — success
  swaps the form for a confirmation panel in place.
- **Mail:** `nx_lib/mail.py`'s existing `send_mail()` (the Graph sender
  built for outage-monitor alerts, issue #166), sent to `SUPPORT_MAIL`
  (`nx_lib/config.py`) — the same env var and mailbox
  `ops/outage_monitor.py` already alerts on breach. If `SUPPORT_MAIL` is
  unset, the form returns a clear 503 rather than silently doing nothing —
  unlike the background monitor, where "unset = probe + log, never mail"
  is the documented, correct dev-box behaviour (see
  `docs/howto/outage-monitor.md`), a live interactive form has to tell the
  user it didn't go anywhere.
- **Enrichment** (server-side, not typed by the user): `session['username']`
  / `fullname`, the referring page (`?from=<path>` on the header link and
  command-palette entry, round-tripped through a hidden form field —
  chosen over `document.referrer` since some browsers/privacy settings
  strip it), `nexora_version`/`nx_lib/version.py`'s `BUILD_STAMP`, and
  `ENVIRONMENT` (same `os.environ.get("ENVIRONMENT", "?")` idiom
  `nx_lib/views/admin/overview.py` uses for its `current_env`).
- **Screenshot:** optional, image-only. Validated with the same
  `nx_lib/files.py` `is_file_allowed()` MIME sniff every other upload in
  the app uses (narrowed here to PNG/JPEG — its table also allows
  pdf/xlsx, not wanted for a screenshot), capped at 5 MB. Read into memory
  and attached to the mail as base64 (`send_mail`'s existing attachment
  support) — **never saved to disk**, so there's nothing to clean up
  later.
- **Rate limit:** `@limiter.limit("10 per hour")` on the POST, keyed by
  remote address like every other `@limiter.limit(...)` route
  (`nx_lib/extensions.py`).

## Testing locally

`SUPPORT_MAIL` is unset by default on `TEST`/most dev boxes (per the
outage-monitor convention above) — submitting will 503 with "Feedback is
not configured on this environment" unless you set it in your `env/*.env`.
For automated tests, `nx_lib.views.profile.send_mail` is what to
`unittest.mock.patch` (it's imported directly into that module's
namespace, same idiom `tests/integration/test_reporting_routes.py` uses
for `ops.run_scheduled_reports.send_mail`) — see
`tests/integration/test_feedback_routes.py`.

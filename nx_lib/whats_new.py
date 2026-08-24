"""What's New — curated, user-facing release notes plus the per-user seen-marker.

Content is authored here at release time (see ``docs/howto/whats-new.md``):
one dict per release, newest first, each entry optionally gated by a
permission code and optionally linking to its feature page. Strings are
lazy-gettext so they render in the session locale; pybabel extracts them
because the alias is named ``_``.

The badge ("unseen" dot in the header) lights when a curated release newer
than ``dbo.Users.whats_new_seen_version`` has at least one entry the user's
permissions can see. Opening ``/whats_new`` stamps the current app version.
"""

from flask import current_app
from flask_babel import lazy_gettext as _

from .db import engine_nexora_db
from .version import __version__

# Newest first. Entry keys: title, body, perm (None = everyone),
# endpoint (url_for name, None = no link), icon (fontawesome, no "fa-" prefix).
RELEASES = [
    {
        "version": "3.1.1",
        "date": "2026-08-18",
        "entries": [
            {
                "title": _("Filters apply instantly"),
                "body": _(
                    "The Apply button is gone from the Generali filter bars — "
                    "changing any filter or date reloads the list right away."
                ),
                "perm": "generali.baseservices.view",
                "endpoint": "generali_baseServices",
                "icon": "bolt",
            },
            {
                "title": _("Type to find a user in the filters"),
                "body": _(
                    "The user filter on the Generali pages is now a search box: "
                    "type a few letters, pick the name, and the list filters "
                    "instantly."
                ),
                "perm": "generali.baseservices.view",
                "endpoint": "generali_baseServices",
                "icon": "magnifying-glass",
            },
        ],
    },
    {
        "version": "3.1",
        "date": "2026-08-06",
        "entries": [
            {
                "title": _("Forecast your report trends"),
                "body": _(
                    "Reports charted over a single date breakdown (per week, "
                    "month, …) gain a Forecast toggle: the chart extends with a "
                    "dashed prediction line and a confidence band, and exports "
                    "and scheduled mails include the forecast too."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "chart-line",
            },
            {
                "title": _("Compare with the prior period"),
                "body": _(
                    "Simple-tab reports with a relative date range now show ↑/↓ "
                    "change chips and a small trend sparkline against the "
                    "equivalent prior period — see at a glance whether numbers "
                    "went up or down."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "arrow-trend-up",
            },
            {
                "title": _("Backlog over time"),
                "body": _(
                    "Reporting has a new Backlog measure — track how the open "
                    "backlog develops per client or process, week by week."
                ),
                # 0069 retired the standalone backlog source; the Backlog
                # measure now lives on the docprocessing source.
                "perm": "reporting.source.docprocessing",
                "endpoint": "reporting",
                "icon": "layer-group",
            },
            {
                "title": _("Chat with the reporting AI"),
                "body": _(
                    "The one-shot Ask AI is now a full chat panel on both "
                    "Reporting tabs — ask follow-up questions in context, watch "
                    "live progress while the agent works, and continue or retry "
                    "a run that stopped early."
                ),
                "perm": "reporting.ai.use",
                "endpoint": "reporting",
                "icon": "comments",
            },
            {
                "title": _("Filter several processes at once"),
                "body": _(
                    "The process filter on Dashboard and Workitems is now a "
                    "multi-select — combine two or three processes in one view."
                ),
                "perm": "workitems.view",
                "endpoint": "workitems_overview",
                "icon": "filter",
            },
            {
                "title": _("Smarter document value search"),
                "body": _(
                    "Search workitems by document value without picking a field "
                    "first — matches are found across every field you may see. "
                    "Each search row now has an operator (contains, =, ≠, starts "
                    "with, ends with) and rows combine with AND/OR."
                ),
                "perm": "workitems.filter.documentfields",
                "endpoint": "workitems_overview",
                "icon": "magnifying-glass",
            },
            {
                "title": _("Date-range presets"),
                "body": _(
                    "Today, Yesterday, This week, Last 7 days, This month — one "
                    "click in the Workitems advanced filter instead of typing dates."
                ),
                "perm": "workitems.view",
                "endpoint": "workitems_overview",
                "icon": "calendar-days",
            },
            {
                "title": _("Filter workitems by stage"),
                "body": _(
                    "A new Stage filter (Import, Extraction, Validation, Delivery) "
                    "narrows the list to workitems currently in that step."
                ),
                "perm": "workitems.filter.stage",
                "endpoint": "workitems_overview",
                "icon": "list-check",
            },
            {
                "title": _("See deleted workitems"),
                "body": _(
                    "The status filter gains a Deleted option — workitems that "
                    "were deleted, previously hidden entirely, can now be shown "
                    "on demand, badged red."
                ),
                "perm": "workitems.filter.status.deleted",
                "endpoint": "workitems_overview",
                "icon": "trash-can",
            },
            {
                "title": _("Make nexora look your way"),
                "body": _(
                    "The new Appearance page has a live preview and more choices: "
                    "light, dark or system theme, custom accent color, font size, "
                    "corner style, high contrast, table stripes, page backgrounds "
                    "and animation speed. Your settings follow your account on "
                    "every device."
                ),
                "perm": None,
                "endpoint": "appearance",
                "icon": "palette",
            },
            {
                "title": _("API documentation in the app"),
                "body": _(
                    "The external API is now documented on the new API Documentation page — "
                    "authentication, endpoints and copyable examples included. "
                    "Every endpoint also has a test twin — same address and shape, "
                    "fake data — so you can integrate without touching production."
                ),
                "perm": "api.docs.view",
                "endpoint": "api_docs",
                "icon": "code",
            },
            {
                "title": _("System status at a glance for admins"),
                "body": _(
                    "The new Status page shows each component's health, a 30-day "
                    "uptime strip and the incident history — checked every few "
                    "minutes by the outage monitor, with a clear warning if the "
                    "data ever goes stale."
                ),
                "perm": "admin.status.view",
                "endpoint": "admin_status_view",
                "icon": "heart-pulse",
            },
            {
                "title": _("Chat, notifications and workitem tags retired"),
                "body": _(
                    "The chat page, the notification bell, and workitem tags, "
                    "priority, assignment and comments have been removed to keep "
                    "nexora focused on document processing. Existing data is "
                    "preserved."
                ),
                "perm": None,
                "endpoint": None,
                "icon": "box-archive",
            },
        ],
    },
    {
        "version": "2.5.64",
        "date": "2026-07-22",
        "entries": [
            {
                "title": _("Build multi-card dashboards"),
                "body": _(
                    "Save several reports as one dashboard: combine KPI, chart "
                    "and table cards, drag to rearrange, set global filters with "
                    "per-card overrides, and export or drill through from any card."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "table-columns",
            },
            {
                "title": _("Drill through to the documents"),
                "body": _(
                    "Click a chart element or result row in Reporting to open the "
                    "underlying document rows, with workitem links and export."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "magnifying-glass-chart",
            },
            {
                "title": _("Combine measures in one report"),
                "body": _(
                    "The guided report builder now takes several measures at once "
                    "(from the same source) and has its own process step, with "
                    "coverage badges showing which processes provide each field."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "wand-magic-sparkles",
            },
            {
                "title": _("Machine-to-machine API"),
                "body": _(
                    "External clients can fetch KPI numbers — like today's "
                    "imported and processed counts — over the new authenticated "
                    "/api/v1 interface."
                ),
                "perm": "api.docs.view",
                "endpoint": "api_docs",
                "icon": "plug",
            },
        ],
    },
]


def _ver(v):
    """'2.5.64' -> (2, 5, 64); malformed/empty -> (0,) so it sorts oldest."""
    try:
        return tuple(int(p) for p in str(v).strip().split("."))
    except ValueError:
        return (0,)


def visible_releases(has_perm):
    """Releases with only the entries ``has_perm`` allows; empty releases drop."""
    out = []
    for rel in RELEASES:
        entries = [e for e in rel["entries"] if not e.get("perm") or has_perm(e["perm"])]
        if entries:
            out.append({**rel, "entries": entries})
    return out


def has_unseen(last_seen, has_perm):
    """True when a curated release newer than ``last_seen`` is visible to the user."""
    seen = _ver(last_seen) if last_seen else (0,)
    return any(_ver(rel["version"]) > seen for rel in visible_releases(has_perm))


def load_seen_version(userid):
    """The user's stored seen-marker; None when never stamped or on DB error."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT whats_new_seen_version FROM Users WHERE userid = ?", [userid])
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None
    except Exception as e:
        current_app.logger.error(f"whats_new load_seen_version error: {e}")
        return __version__  # fail quiet: no badge rather than a stuck one
    finally:
        if conn:
            conn.close()


def mark_seen(userid):
    """Stamp the current app version as seen (clears the badge)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET whats_new_seen_version = ? WHERE userid = ?",
            [__version__, userid],
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        current_app.logger.error(f"whats_new mark_seen error: {e}")
    finally:
        if conn:
            conn.close()

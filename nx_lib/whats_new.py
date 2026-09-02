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

from . import user_cache
from .db import engine_nexora_db
from .version import __version__

# Newest first. Entry keys: title, body, perm (None = everyone),
# endpoint (url_for name, None = no link), icon (fontawesome, no "fa-" prefix).
RELEASES: list[dict] = [
    {
        "version": "3.2.3",
        "date": "2026-08-27",
        "entries": [
            {
                "title": _("Reporting has a new home screen"),
                "body": _(
                    "The reporting page is now a workbench: a Library of every "
                    "report you can see, a Results screen that brings back your "
                    "last result without re-running it, Dashboards, Scheduled "
                    "deliveries, and a rail down the left showing each data "
                    "source with its live response time."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "table-columns",
            },
            {
                "title": _("Look inside a data source"),
                "body": _(
                    "Click a card in the Sources rail to see the database "
                    "behind it: the tables that source actually reads, their "
                    "columns and types, and a diagram of how they connect. "
                    "Structure only — no data is shown."
                ),
                "perm": "reporting.sources.schema",
                "endpoint": "reporting",
                "icon": "diagram-project",
            },
            {
                "title": _("Dashboards you can arrange"),
                "body": _(
                    "Adding a card asks everything in one dialog — which saved "
                    "report, how to draw it, its title and its size. In edit "
                    "mode drag a tile anywhere and resize it by its corner "
                    "grip, and the Whole report tile shows a saved report "
                    "exactly as the Library does."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "grip",
            },
            {
                "title": _("Meet Eddard"),
                "body": _(
                    "The reporting assistant has a name and a face — the little "
                    "black hole in the top bar. Ask it a question in plain "
                    "language and open what it built in the builder before you "
                    "trust the number."
                ),
                "perm": "reporting.ai.use",
                "endpoint": "reporting",
                "icon": "wand-magic-sparkles",
            },
            {
                "title": _("Charts in your colours"),
                "body": _(
                    "The palette button in the chart toolbar recolours each "
                    "series and the title, and can move a series onto its own "
                    "right-hand axis so a few hundred stays readable next to "
                    "tens of thousands. Your picks are saved with the report."
                ),
                "perm": "reporting.view",
                "endpoint": "reporting",
                "icon": "palette",
            },
            {
                "title": _("Press ? for the shortcuts"),
                "body": _(
                    "A cheatsheet of every keyboard shortcut on the page, one "
                    "keypress away. Press ? anywhere outside a text box."
                ),
                "perm": None,
                "endpoint": None,
                "icon": "keyboard",
            },
            {
                "title": _("Everything loads quicker"),
                "body": _(
                    "Pages are compressed in transit, their scripts are cached "
                    "between visits, and the reporting page stopped fetching "
                    "the same lists eight times per load."
                ),
                "perm": None,
                "endpoint": None,
                "icon": "bolt",
            },
            {
                "title": _("Who can do what, on one page"),
                "body": _(
                    "The new permission matrix under Admin shows every access "
                    "profile against every permission in a single grid, so a "
                    "missing grant is something you can see instead of hunt."
                ),
                "perm": "admin.view",
                "endpoint": "admin_permission_matrix",
                "icon": "table-cells",
            },
        ],
    },
    {
        "version": "3.2.2",
        "date": "2026-08-25",
        "entries": [
            {
                "title": _("Imports, exports and backlog on one chart"),
                "body": _(
                    "Document Processing gained date-anchored measures: pick "
                    "documents or pages imported, exported and the backlog "
                    "together over time and they all plot on one shared date "
                    "axis. The separate Backlog History source is retired — the "
                    "new Backlog measure replaces it."
                ),
                "perm": "reporting.source.docprocessing",
                "endpoint": "reporting",
                "icon": "chart-line",
            },
            {
                "title": _("The reporting AI panel gets out of your way"),
                "body": _(
                    "The chat panel now floats instead of blocking the page: "
                    "drag it by its header, keep working behind it, and select "
                    "or copy any answer or generated SQL."
                ),
                "perm": "reporting.ai.use",
                "endpoint": "reporting",
                "icon": "comments",
            },
            {
                "title": _("Large workitem searches load faster"),
                "body": _(
                    "Big result sets arrive in two phases, so the first rows "
                    "show up right away. Typing a partial id now matches by "
                    "prefix and the closest hits are ranked first."
                ),
                "perm": "workitems.view",
                "endpoint": "workitems_overview",
                "icon": "gauge-high",
            },
            {
                "title": _("Tell us what you think"),
                "body": _(
                    "The new Feedback page (profile dropdown → Feedback) sends "
                    "your praise, gripes and ideas straight to the nexora team."
                ),
                "perm": None,
                "endpoint": "feedback",
                "icon": "comment-dots",
            },
            {
                "title": _("Dark mode, polished"),
                "body": _(
                    "The light flash on page loads is gone, checkboxes, menus "
                    "and tables follow the theme everywhere, and Appearance "
                    'adds a "Fireflies" page background.'
                ),
                "perm": None,
                "endpoint": "appearance",
                "icon": "moon",
            },
        ],
    },
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
                "endpoint": "generali_base_services",
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
                "endpoint": "generali_base_services",
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


def _load_seen_version(userid):
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


def load_seen_version(userid):
    """The user's stored seen-marker; None when never stamped or on DB error.

    Called from ``_inject_whats_new`` on every HTML render, so it is read
    through the same per-process TTL cache as permissions/ui_prefs
    (nx_lib/user_cache.py) rather than hitting NexoraDB every time.
    """
    return user_cache.get_or_load("whats_new_seen", userid, lambda: _load_seen_version(userid))


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
        user_cache.forget(userid)

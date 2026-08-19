"""Status-page data layer: component snapshots + incident history in NexoraDB.

``nx_lib/outage.py`` deliberately stays pure (no DB, no probes) because
``ops/outage_monitor.py`` has to keep alerting when NexoraDB is itself the thing
that is down -- its working state lives in ``var/outage-state.json``. This module
is the *reporting* half of the split (issue #167): after each run the monitor
mirrors what it saw into ``dbo.StatusComponents`` / ``dbo.StatusIncidents``
(best-effort -- a failed write must never cost an alert mail), and the admin
status page reads it back. The eventual public status page, which has to live
outside the app to survive a full app outage, consumes the same two tables.

Everything above ``--- persistence ---`` is pure and unit-tested; the DB halves
are thin.
"""

from contextlib import suppress
from datetime import UTC, datetime, time, timedelta

# A monitor that has stopped running is the dangerous failure mode: an all-green
# page fed by three-day-old rows is worse than no page. Anything older than this
# is reported as stale rather than believed. Sized for the 5 min poll interval.
DEFAULT_STALE_AFTER_S = 15 * 60

DEFAULT_HISTORY_DAYS = 30

# Worst-first: the overall banner takes the first state any component matches.
_SEVERITY = ("outage", "degraded", "operational")


def pretty_name(key, stored=None):
    """Human label for a monitor component key.

    The keys are stable dedupe ids chosen for the state file (``db:NexoraDB``,
    ``http:site``, ``octo:prd-dps.sydoc.ch``) and must not change -- renaming one
    would re-open every incident it has. So the prettifying happens here, at
    read time, instead.
    """
    if key.startswith("db:"):
        return key[3:]
    if key == "http:site":
        return "Application (IIS)"
    if key.startswith("octo:"):
        return f"Octo runtime ({key[5:]})"
    if key == "graph:mail":
        return "Microsoft Graph (mail)"
    if key == "api:v1":
        return "Nexora API (/api/v1)"
    if key == "api:key":
        return "Nexora API (key auth)"
    return stored or key


# Grouping is display-only: twelve flat rows all read the same, and the eye has
# nothing to anchor on. "Which layer is broken" is the first question during an
# incident, so the grid answers it structurally.
GROUPS = ("Application", "Databases", "Integrations")


def component_group(key):
    if key.startswith("db:"):
        return "Databases"
    if key == "http:site" or key.startswith("api:"):
        return "Application"
    return "Integrations"


def component_group_order(components):
    """``[(group, [component, ...]), ...]`` in GROUPS order, empty groups dropped.

    Within a group the worst state sorts first: during an incident the broken row
    must be the one you land on, not the ninth green row you scroll past.
    """
    ordered = []
    for group in GROUPS:
        members = [c for c in components if c["group"] == group]
        if members:
            members.sort(key=lambda c: (_SEVERITY.index(c["state"]), c["name"].lower()))
            ordered.append((group, members))
    return ordered


def component_state(comp):
    """Map one ``nx_lib.outage`` component state dict to a display state.

    ``degraded`` is the interesting one: a component that is failing probes but
    has not yet crossed its fail threshold. The monitor stays deliberately quiet
    there (no mail until it is convincing), but the page should show that
    something is wobbling.
    """
    if comp.get("open_since"):
        return "outage"
    if comp.get("fail_streak"):
        return "degraded"
    return "operational"


def overall_state(states, stale=False, maintenance=False):
    """Fold component states into the single headline state.

    Maintenance wins the *headline* but never rewrites a component's own state:
    planned downtime shouldn't read as an outage, and a real breakage during a
    maintenance window shouldn't be hidden by it either.
    """
    if maintenance:
        return "maintenance"
    if stale or not states:
        return "unknown"
    for level in _SEVERITY:
        if level in states:
            return level
    return "operational"


def humanize_duration(seconds):
    """``93600`` -> ``"1 d 2 h"``. Coarse on purpose -- this labels incidents."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def uptime_strip(incidents, now, days=DEFAULT_HISTORY_DAYS, first_seen=None):
    """One cell per day for the last ``days``, newest last.

    Days before ``first_seen`` are ``unknown`` rather than green -- the strip
    must not claim uptime for a period nothing was watching. An open incident
    (``ended_at`` None) counts as down through ``now``.
    """
    first_day = (now - timedelta(days=days - 1)).date()
    cells = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)
        if first_seen is not None and day_end <= first_seen:
            cells.append({"date": day.isoformat(), "state": "unknown"})
            continue
        down = any(
            inc["started_at"] < day_end and (inc["ended_at"] or now) > day_start
            for inc in incidents
        )
        cells.append({"date": day.isoformat(), "state": "outage" if down else "operational"})
    return cells


# --------------------------------- persistence -------------------------------- #


def _naive_utc(dt):
    """pyodbc binds DATETIME2 from naive datetimes; the monitor works in aware UTC."""
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _as_dt(value):
    """Coerce a fetched DATETIME2 to a datetime.

    The ODBC driver in use hands DATETIME2 back as ``str`` rather than
    ``datetime`` (the same trap ``maintenance._maintenance_iso`` guards against),
    and every duration and strip calculation here needs real datetimes.
    """
    if value is None or hasattr(value, "isoformat"):
        return value
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _iso_utc(dt):
    """Stored naive values are UTC by construction; label them so JS can parse."""
    dt = _as_dt(dt)
    return None if dt is None else dt.replace(tzinfo=UTC).isoformat()


def persist_run(engine, snapshots, events, now):
    """Mirror one monitor run into the two status tables.

    ``snapshots`` is ``[{key, name, state, detail, ok}]`` for the *fixed*
    components only (log storms are incident-only -- see migration 0055).
    ``events`` is ``[{key, name, kind, started_at, detail, excerpt}]`` with kind
    ``open`` or ``recover``.

    Raises on DB failure; the caller is expected to swallow it. Losing the
    status-page mirror is an inconvenience, losing the alert mail is the bug
    this whole feature exists to prevent.
    """
    now = _naive_utc(now)
    conn = engine.raw_connection()
    try:
        cursor = conn.cursor()
        for snap in snapshots:
            cursor.execute(
                """
                UPDATE dbo.StatusComponents
                   SET ComponentName = ?, State = ?, Detail = ?, LastCheckedAt = ?,
                       LastOkAt = CASE WHEN ? = 1 THEN ? ELSE LastOkAt END
                 WHERE ComponentKey = ?
                """,
                (
                    snap["name"],
                    snap["state"],
                    (snap.get("detail") or "")[:1000] or None,
                    now,
                    1 if snap.get("ok") else 0,
                    now,
                    snap["key"],
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO dbo.StatusComponents
                        (ComponentKey, ComponentName, State, Detail,
                         FirstSeenAt, LastCheckedAt, LastOkAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap["key"],
                        snap["name"],
                        snap["state"],
                        (snap.get("detail") or "")[:1000] or None,
                        now,
                        now,
                        now if snap.get("ok") else None,
                    ),
                )

        for event in events:
            if event["kind"] == "open":
                # The filtered unique index makes a duplicate open impossible;
                # the guard keeps a re-run from raising instead of no-opping.
                cursor.execute(
                    """
                    INSERT INTO dbo.StatusIncidents
                        (ComponentKey, ComponentName, StartedAt, Detail, Excerpt)
                    SELECT ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dbo.StatusIncidents
                        WHERE ComponentKey = ? AND EndedAt IS NULL
                    )
                    """,
                    (
                        event["key"],
                        event["name"],
                        _naive_utc(event.get("started_at")) or now,
                        (event.get("detail") or "")[:1000] or None,
                        event.get("excerpt"),
                        event["key"],
                    ),
                )
            else:
                cursor.execute(
                    "UPDATE dbo.StatusIncidents SET EndedAt = ? "
                    "WHERE ComponentKey = ? AND EndedAt IS NULL",
                    (now, event["key"]),
                )
        conn.commit()
    finally:
        with suppress(Exception):
            conn.close()


def _fetch(engine, sql, params=()):
    conn = engine.raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        with suppress(Exception):
            conn.close()


def load_status(
    engine,
    now=None,
    history_days=DEFAULT_HISTORY_DAYS,
    stale_after_s=DEFAULT_STALE_AFTER_S,
    maintenance=False,
):
    """Everything the status page renders, in one dict.

    Never raises for "the monitor has never run" -- that is the normal state on
    INT and on a freshly deployed PROD, and it reports as ``unknown`` + a
    "no data yet" flag rather than as an error.
    """
    now = _naive_utc(now or datetime.now(UTC))
    since = now - timedelta(days=history_days)

    rows = _fetch(
        engine,
        """
        SELECT ComponentKey, ComponentName, State, Detail,
               FirstSeenAt, LastCheckedAt, LastOkAt
          FROM dbo.StatusComponents
         ORDER BY ComponentKey
        """,
    )
    incidents = _fetch(
        engine,
        """
        SELECT ComponentKey, ComponentName, StartedAt, EndedAt, Detail, Excerpt
          FROM dbo.StatusIncidents
         WHERE EndedAt IS NULL OR EndedAt >= ?
         ORDER BY StartedAt DESC
        """,
        (since,),
    )

    # Normalise the driver's DATETIME2-as-str once, here, so nothing downstream
    # has to care (see _as_dt).
    rows = [(*r[:4], _as_dt(r[4]), _as_dt(r[5]), _as_dt(r[6])) for r in rows]
    incidents = [(r[0], r[1], _as_dt(r[2]), _as_dt(r[3]), r[4], r[5]) for r in incidents]

    by_component = {}
    for key, name, started, ended, detail, excerpt in incidents:
        by_component.setdefault(key, []).append(
            {
                "started_at": started,
                "ended_at": ended,
                "detail": detail,
                "excerpt": excerpt,
                "name": name,
            }
        )

    components = []
    for key, name, state, detail, first_seen, last_checked, last_ok in rows:
        components.append(
            {
                "key": key,
                "name": pretty_name(key, name),
                "group": component_group(key),
                "state": state,
                "detail": detail,
                "last_checked_at": _iso_utc(last_checked),
                "last_ok_at": _iso_utc(last_ok),
                "strip": uptime_strip(
                    by_component.get(key, []), now, days=history_days, first_seen=first_seen
                ),
            }
        )

    history = [
        {
            "key": key,
            "name": pretty_name(key, name),
            "started_at": _iso_utc(started),
            "ended_at": _iso_utc(ended),
            "duration": humanize_duration(((ended or now) - started).total_seconds()),
            "open": ended is None,
            "detail": detail,
            "excerpt": excerpt,
        }
        for key, name, started, ended, detail, excerpt in incidents
    ]

    last_checked = max((r[5] for r in rows), default=None)
    stale = last_checked is None or (now - last_checked).total_seconds() > stale_after_s
    counts = {level: sum(1 for c in components if c["state"] == level) for level in _SEVERITY}
    return {
        "components": components,
        "groups": component_group_order(components),
        "counts": counts,
        "total": len(components),
        "history": history,
        "open_incidents": [h for h in history if h["open"]],
        "last_checked_at": _iso_utc(last_checked),
        "stale": stale,
        "never_ran": last_checked is None,
        "history_days": history_days,
        "overall": overall_state(
            {c["state"] for c in components}, stale=stale, maintenance=maintenance
        ),
    }

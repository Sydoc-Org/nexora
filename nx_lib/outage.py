"""Outage detection: log-storm scanning, alert hysteresis, state persistence.

Pure logic only -- no probes, no mail, no DB. ``ops/outage_monitor.py`` runs the
actual probes (DB pings, HTTP GET, Octo token, log tail) and feeds the results
in here, mirroring the ``nx_lib/reporting/schedule.py`` +
``ops/run_scheduled_reports.py`` split so the interesting parts stay testable
without a live PROD.

The alert-hygiene rules exist because a naive "mail on every failed probe"
monitor floods the support inbox the moment something flaps (the ping_prdsrv
incident: ~200 mails from one flapping link). Three guards, all in
``update_component``:

* **fail threshold** -- N consecutive bad probes before an incident opens, so a
  single blip during an app-pool recycle stays quiet.
* **dedupe** -- while an incident is open, further bad probes update the
  evidence but send nothing.
* **min-hold** -- an open incident cannot close until it has been open for
  ``min_hold_s``, so a component toggling every poll yields one open mail and
  one recovery mail, not a pair per toggle.
"""

import contextlib
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta

# --- Alert hysteresis defaults ------------------------------------------------
# Tuned for a ~5 minute poll interval: 2 consecutive failures (~10 min) before
# alerting, 2 consecutive successes plus a 30 minute hold before all-clear.
DEFAULT_FAIL_THRESHOLD = 2
DEFAULT_RECOVER_THRESHOLD = 2
DEFAULT_MIN_HOLD_S = 30 * 60

# --- Log-storm defaults -------------------------------------------------------
# The reference case (issue #166) was `Invalid object name 'dbo.WorkitemTags'`
# repeating for hours while every DB ping stayed green -- logic-level breakage
# that only the log can see.
DEFAULT_STORM_WINDOW_MIN = 15
DEFAULT_STORM_MIN_COUNT = 10
# WARNING is scanned too -- a logic-level fault often only warns (the reporting
# catalog spent months emitting a WARNING per request that nothing watched).
# It needs its own, much higher bar: warnings are routine, errors are not.
# 60 in a 15-minute window is 4/minute sustained, well above ordinary chatter.
DEFAULT_STORM_WARN_MIN_COUNT = 60

# app_logging._LOG_FORMAT: "%(asctime)s [%(levelname)s] %(name)s %(module)s:%(lineno)d %(message)s"
# asctime renders as "2026-08-05 09:12:33,123" in *local* time (logging uses
# time.localtime), which is why the scan functions take a naive local `now`.
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(?P<ms>\d{3}) "
    r"\[(?P<level>[A-Z]+)\] (?P<rest>.*)$"
)

# Variable parts of a message that must NOT split one storm into many
# signatures: ids, guids, hex blobs, quoted literals, timings.
_NORMALIZERS = (
    (
        re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
        "<guid>",
    ),
    (re.compile(r"0x[0-9a-fA-F]+"), "<hex>"),
    (re.compile(r"'[^']*'"), "'<s>'"),
    (re.compile(r'"[^"]*"'), '"<s>"'),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<n>"),
    (re.compile(r"\s+"), " "),
)


def normalize_signature(message):
    """Collapse the variable parts of a log message into a stable storm key.

    Two errors that differ only by workitem id, GUID, or quoted table name are
    the *same* storm and must dedupe onto one incident.
    """
    out = message.strip()
    for pattern, replacement in _NORMALIZERS:
        out = pattern.sub(replacement, out)
    return out.strip()


def parse_log_lines(text):
    """Yield ``(naive_local_datetime, level, message)`` for each parsable line.

    Traceback continuation lines and anything else not matching the handler
    format are skipped -- the storm signal is the repeated header line.
    """
    for line in text.splitlines():
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        yield ts, m.group("level"), m.group("rest")


def detect_error_storms(
    text,
    now_local,
    window_min=DEFAULT_STORM_WINDOW_MIN,
    min_count=DEFAULT_STORM_MIN_COUNT,
    levels=("ERROR", "CRITICAL", "WARNING"),
    warn_min_count=DEFAULT_STORM_WARN_MIN_COUNT,
):
    """Find error signatures repeating at least ``min_count`` times in the window.

    ``now_local`` is naive local time to match the log's asctime. Returns a list
    of ``{key, signature, count, first_seen, last_seen, sample}`` sorted by count
    descending -- ``key`` is the stable component id used for incident state.
    """
    cutoff = now_local - timedelta(minutes=window_min)
    groups: dict[str, dict] = {}
    for ts, level, message in parse_log_lines(text):
        if level not in levels or ts < cutoff:
            continue
        signature = normalize_signature(message)
        entry = groups.get(signature)
        if entry is None:
            groups[signature] = {
                "signature": signature,
                "count": 1,
                "first_seen": ts,
                "last_seen": ts,
                "sample": message.strip(),
                "level": level,
            }
            continue
        # A signature seen at two levels takes the louder one, so one stray
        # WARNING cannot lower an ERROR storm's bar.
        if entry["level"] == "WARNING" and level != "WARNING":
            entry["level"] = level
        entry["count"] += 1
        entry["first_seen"] = min(entry["first_seen"], ts)
        entry["last_seen"] = max(entry["last_seen"], ts)

    storms = []
    for entry in groups.values():
        floor = warn_min_count if entry["level"] == "WARNING" else min_count
        if entry["count"] < floor:
            continue
        digest = hashlib.sha1(entry["signature"].encode("utf-8")).hexdigest()[:10]
        storms.append(
            {
                "key": f"log:{digest}",
                "label": storm_label(entry["sample"], entry["level"]),
                **entry,
            }
        )
    storms.sort(key=lambda s: s["count"], reverse=True)
    return storms


# "nx_lib ui_prefs:65 load_ui_prefs error: ..." -> the "ui_prefs:65" part.
_ORIGIN_RE = re.compile(r"^\S+\s+(\S+:\d+)\s")


def storm_label(sample, level="ERROR"):
    """A human-readable component name for a storm.

    The state key is a hash (stable across line-number churn), but a support
    ticket titled ``OUTAGE: log:8a8920493d`` tells the reader nothing -- the
    subject line should name the code site that is screaming, and whether it is
    screaming or merely grumbling.
    """
    kind = "warn storm" if level == "WARNING" else "log storm"
    m = _ORIGIN_RE.match(sample or "")
    return f"{kind} @ {m.group(1)}" if m else kind


def tail_text(path, max_bytes=2 * 1024 * 1024):
    """Read the last ``max_bytes`` of a (possibly huge, possibly absent) log file.

    Returns "" when the file is missing -- a monitor must never crash because
    the app has not written a log yet.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            raw = fh.read()
    except OSError:
        return ""
    # A mid-file seek can land inside a multi-byte char; the partial first line
    # is dropped by the line regex anyway.
    return raw.decode("utf-8", errors="replace")


def update_component(
    prev,
    ok,
    detail,
    now,
    fail_threshold=DEFAULT_FAIL_THRESHOLD,
    recover_threshold=DEFAULT_RECOVER_THRESHOLD,
    min_hold_s=DEFAULT_MIN_HOLD_S,
):
    """Fold one probe result into a component's incident state.

    Returns ``(new_state, event)`` where event is ``None``, ``"open"`` or
    ``"recover"``. Only the two non-None events produce mail -- everything else
    (repeat failures on an already-open incident, recoveries still inside the
    min-hold window) updates state silently. See the module docstring for why.
    """
    prev = prev or {}
    fail_streak = prev.get("fail_streak", 0)
    ok_streak = prev.get("ok_streak", 0)
    open_since = prev.get("open_since")
    first_fail_at = prev.get("first_fail_at")

    if ok:
        ok_streak += 1
        fail_streak = 0
    else:
        fail_streak += 1
        ok_streak = 0
        if fail_streak == 1:
            first_fail_at = now.isoformat()

    event = None
    if not ok and open_since is None and fail_streak >= fail_threshold:
        open_since = now.isoformat()
        event = "open"
    elif ok and open_since is not None and ok_streak >= recover_threshold:
        # min-hold: a component that flaps green/red faster than this sends one
        # open mail and stays open until it is genuinely stable.
        if (now - datetime.fromisoformat(open_since)).total_seconds() >= min_hold_s:
            event = "recover"
            open_since = None
            first_fail_at = None

    state = {
        "fail_streak": fail_streak,
        "ok_streak": ok_streak,
        "open_since": open_since,
        "first_fail_at": first_fail_at,
        "last_detail": detail,
        "updated_at": now.isoformat(),
    }
    return state, event


def prune_state(state, now, max_age_days=7):
    """Drop closed components untouched for ``max_age_days``.

    Only dynamic log-storm keys ever go stale -- the fixed DB/HTTP/Octo
    components are rewritten every run. Without this the state file would grow a
    permanent entry per distinct error signature ever seen.
    """
    cutoff = now - timedelta(days=max_age_days)
    kept = {}
    for key, comp in (state.get("components") or {}).items():
        if comp.get("open_since"):
            kept[key] = comp
            continue
        try:
            if datetime.fromisoformat(comp["updated_at"]) >= cutoff:
                kept[key] = comp
        except (KeyError, TypeError, ValueError):
            continue  # unparsable entry: let it go
    return {**state, "components": kept}


def load_state(path):
    """Read the persisted incident state; a missing/corrupt file starts empty.

    Persisting matters for dedupe: without it every monitor run would look like
    a first sighting and re-alert on an incident that is already open.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return {"components": {}}
    if not isinstance(state, dict) or not isinstance(state.get("components"), dict):
        return {"components": {}}
    return state


def save_state(path, state):
    """Write state atomically so a killed run cannot leave a truncated file."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _esc(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# One root cause (a DB going down) trips every call site that touches it, so a
# single batch can legitimately carry dozens of components. Listing them all in
# the subject makes the ticket unreadable in an inbox; the body still has every
# one.
_SUBJECT_MAX_NAMES = 3


def _subject_names(events):
    names = [e["component"] for e in events]
    if len(names) <= _SUBJECT_MAX_NAMES:
        return ", ".join(names)
    head = ", ".join(names[:_SUBJECT_MAX_NAMES])
    return f"{head} (+{len(names) - _SUBJECT_MAX_NAMES} more)"


def render_alert(events, environment, now):
    """Build ``(subject, html_body)`` for a batch of same-kind events.

    Batched on purpose: one DB server going down trips every DB component plus
    the HTTP probe, and support wants one ticket for that, not five.
    ``events`` is ``[{component, kind, first_seen, detail, excerpt}]`` and must
    be non-empty and all the same ``kind``.
    """
    kind = events[0]["kind"]
    names = _subject_names(events)
    if kind == "open":
        subject = f"[nexora {environment}] OUTAGE: {names}"
        lead = (
            f"<p>Automated outage detection found "
            f"<strong>{len(events)}</strong> failing component(s) on "
            f"<strong>{_esc(environment)}</strong>.</p>"
        )
    else:
        subject = f"[nexora {environment}] RECOVERED: {names}"
        lead = (
            f"<p><strong>{len(events)}</strong> component(s) on "
            f"<strong>{_esc(environment)}</strong> are healthy again.</p>"
        )

    parts = [lead]
    for e in events:
        parts.append(f"<h3>{_esc(e['component'])}</h3><ul>")
        if e.get("first_seen"):
            parts.append(f"<li>First seen: {_esc(e['first_seen'])}</li>")
        parts.append(f"<li>Evidence: {_esc(e.get('detail') or 'n/a')}</li>")
        parts.append("</ul>")
        if e.get("excerpt"):
            parts.append(
                "<pre style='background:#f5f5f5;padding:8px;overflow:auto'>"
                f"{_esc(e['excerpt'])}</pre>"
            )
    parts.append(
        f"<p style='color:#888'>Generated {_esc(now.strftime('%Y-%m-%d %H:%M:%S'))} UTC "
        f"by ops/outage_monitor.py.</p>"
    )
    return subject, "".join(parts)

"""Tests for nx_lib.status — the pure half of the status page's data layer.

The uptime strip and the staleness rule carry the risk here: a strip that paints
un-monitored days green, or an overall state that reports "operational" from
three-day-old rows, is a status page that lies during exactly the incident it
exists to surface (#167).
"""

from datetime import datetime, timedelta

from nx_lib import status

NOW = datetime(2026, 8, 5, 12, 0, 0)


def _incident(start_days_ago, end_days_ago=None):
    return {
        "started_at": NOW - timedelta(days=start_days_ago),
        "ended_at": None if end_days_ago is None else NOW - timedelta(days=end_days_ago),
    }


# --- naming -------------------------------------------------------------------


def test_pretty_name_maps_each_monitor_key_prefix():
    assert status.pretty_name("db:NexoraDB") == "NexoraDB"
    assert status.pretty_name("http:site") == "Application (IIS)"
    assert status.pretty_name("octo:prd-dps.sydoc.ch") == "Octo runtime (prd-dps.sydoc.ch)"
    assert status.pretty_name("graph:mail") == "Microsoft Graph (mail)"
    assert status.pretty_name("bexio:api") == "Bexio API"


def test_pretty_name_falls_back_to_stored_label_for_log_storms():
    assert status.pretty_name("log:8a89204", "log storm @ ui_prefs:65") == "log storm @ ui_prefs:65"
    assert status.pretty_name("log:8a89204") == "log:8a89204"


# --- component state ----------------------------------------------------------


def test_component_state_open_incident_is_outage():
    assert (
        status.component_state({"open_since": "2026-08-05T10:00:00", "fail_streak": 4}) == "outage"
    )


def test_component_state_failing_below_threshold_is_degraded():
    # The monitor is deliberately silent here (no mail until it is convincing),
    # so the page is the only place this is visible.
    assert status.component_state({"open_since": None, "fail_streak": 1}) == "degraded"


def test_component_state_clean_is_operational():
    assert status.component_state({"open_since": None, "fail_streak": 0}) == "operational"


# --- overall ------------------------------------------------------------------


def test_overall_takes_the_worst_component():
    assert status.overall_state({"operational", "degraded", "outage"}) == "outage"
    assert status.overall_state({"operational", "degraded"}) == "degraded"
    assert status.overall_state({"operational"}) == "operational"


def test_overall_is_unknown_when_data_is_stale():
    assert status.overall_state({"operational"}, stale=True) == "unknown"


def test_overall_is_unknown_with_no_components():
    assert status.overall_state(set()) == "unknown"


def test_maintenance_wins_the_headline():
    assert status.overall_state({"outage"}, maintenance=True) == "maintenance"


# --- durations ----------------------------------------------------------------


def test_humanize_duration_scales_by_magnitude():
    assert status.humanize_duration(45) == "45 s"
    assert status.humanize_duration(600) == "10 min"
    assert status.humanize_duration(3600) == "1 h"
    assert status.humanize_duration(3600 * 2 + 900) == "2 h 15 min"
    assert status.humanize_duration(86400 * 3) == "3 d"
    assert status.humanize_duration(86400 + 7200) == "1 d 2 h"


def test_humanize_duration_clamps_negatives():
    assert status.humanize_duration(-10) == "0 s"


# --- uptime strip -------------------------------------------------------------


def test_strip_has_one_cell_per_day_ending_today():
    cells = status.uptime_strip([], NOW, days=30)
    assert len(cells) == 30
    assert cells[-1]["date"] == "2026-08-05"
    assert cells[0]["date"] == "2026-07-07"


def test_strip_is_all_green_without_incidents():
    cells = status.uptime_strip([], NOW, days=7)
    assert {c["state"] for c in cells} == {"operational"}


def test_strip_marks_only_the_days_an_incident_spanned():
    cells = status.uptime_strip([_incident(3, 3)], NOW, days=7)
    outage_days = [c["date"] for c in cells if c["state"] == "outage"]
    assert outage_days == ["2026-08-02"]


def test_strip_marks_every_day_a_multi_day_incident_covered():
    cells = status.uptime_strip([_incident(4, 2)], NOW, days=7)
    outage_days = [c["date"] for c in cells if c["state"] == "outage"]
    assert outage_days == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_open_incident_marks_through_today():
    cells = status.uptime_strip([_incident(1)], NOW, days=7)
    assert cells[-1]["state"] == "outage"
    assert cells[-2]["state"] == "outage"


def test_days_before_monitoring_began_are_unknown_not_green():
    # The whole point: a fresh deploy must not claim 30 days of uptime.
    cells = status.uptime_strip([], NOW, days=7, first_seen=NOW - timedelta(days=2))
    # first_seen is 2026-08-03 12:00, so 08-03 itself already counts as watched.
    assert [c["state"] for c in cells] == [
        "unknown",
        "unknown",
        "unknown",
        "unknown",
        "operational",
        "operational",
        "operational",
    ]


def test_first_seen_mid_day_counts_that_whole_day_as_monitored():
    first_seen = datetime(2026, 8, 4, 23, 30, 0)
    cells = status.uptime_strip([], NOW, days=3, first_seen=first_seen)
    assert [c["state"] for c in cells] == ["unknown", "operational", "operational"]

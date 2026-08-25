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
    assert status.pretty_name("api:v1") == "Nexora API (/api/v1)"
    assert status.pretty_name("api:key") == "Nexora API (key auth)"


def test_component_group_puts_the_api_probes_next_to_the_app():
    # The API is a second entry point into the same app, not a third-party
    # integration -- during an incident it must read next to Application (IIS).
    assert status.component_group("api:v1") == "Application"
    assert status.component_group("api:key") == "Application"
    assert status.component_group("http:site") == "Application"
    assert status.component_group("db:NexoraDB") == "Databases"
    assert status.component_group("graph:mail") == "Integrations"


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


# --------------------------- latency sparklines (0071) ---------------------------


def test_latency_parsed_from_every_detail_shape_the_monitor_writes():
    assert status.latency_from_detail("158 ms") == 158
    assert status.latency_from_detail("timeout (5001 ms)") == 5001
    assert status.latency_from_detail("https://h/: HTTP 200 (204 ms)") == 204
    assert status.latency_from_detail("https://h/: HTTP 500") is None
    assert status.latency_from_detail(None) is None


def test_absurd_latency_is_a_parse_accident_not_a_measurement():
    """A four-hour "probe" means the regex hit an id, not a duration."""
    assert status.latency_from_detail("99999999 ms") is None


def _samples(now, count, ms=100, step_min=5, ok=True):
    return [(now - timedelta(minutes=step_min * i), ms, ok) for i in range(count)]


def test_spark_series_buckets_a_day_of_samples():
    series = status.spark_series(_samples(NOW, 288), NOW, window_h=24, buckets=24)
    assert series["count"] == 288
    assert len(series["points"]) == 24
    assert series["last_ms"] == 100
    assert None not in series["points"]


def test_spark_series_keeps_the_spike_rather_than_averaging_it_away():
    """A 5-minute stall is the whole point of the graph; a mean would hide it."""
    samples = _samples(NOW, 12, ms=100)
    samples.append((NOW - timedelta(minutes=3), 4000, True))
    series = status.spark_series(samples, NOW, window_h=24, buckets=24)
    assert series["max_ms"] == 4000
    assert series["points"][-1] == 4000


def test_spark_series_leaves_gaps_where_the_monitor_was_not_running():
    """Interpolating would draw a healthy flat line straight through an outage."""
    old = [
        (NOW - timedelta(hours=20), 100, True),
        (NOW - timedelta(hours=20, minutes=5), 100, True),
    ]
    series = status.spark_series(old + _samples(NOW, 3), NOW, window_h=24, buckets=24)
    assert series["points"].count(None) > 0


def test_spark_series_marks_buckets_that_failed():
    series = status.spark_series(_samples(NOW, 4, ms=5000, ok=False), NOW)
    assert any(series["failed"])
    # Counted as well as flagged: the marker is a red square, which says nothing
    # to a screen reader or a greyscale print -- the label has to say it.
    assert series["failed_buckets"] == 1


def test_spark_series_reports_no_failures_when_every_probe_passed():
    assert status.spark_series(_samples(NOW, 40), NOW)["failed_buckets"] == 0


def test_spark_series_needs_two_points_to_be_a_trend():
    """One dot implies a direction it cannot support."""
    assert status.spark_series([], NOW) is None
    assert status.spark_series([(NOW, 100, True)], NOW) is None


def test_spark_series_ignores_samples_outside_the_window():
    stale = [(NOW - timedelta(days=3), 100, True) for _ in range(50)]
    assert status.spark_series(stale, NOW) is None


def test_spark_geometry_is_zero_based_so_height_means_duration():
    """A min..max fit turns ordinary jitter into cliffs and alarms nobody usefully."""
    series = status.spark_series(
        [(NOW - timedelta(minutes=5 * i), 100 if i else 200, True) for i in range(200)],
        NOW,
    )
    geom = status.spark_geometry(series, width=100, height=24, pad=2)
    ys = [float(p.split(",")[1]) for seg in geom["segments"] for p in seg.split()]
    # 200 ms sits at the top (pad), 100 ms halfway down the 20-unit plot area.
    assert min(ys) == 2.0
    assert 11.5 <= max(ys) <= 12.5


def test_spark_geometry_breaks_the_line_where_samples_are_missing():
    gappy = [(NOW - timedelta(minutes=5 * i), 100, True) for i in range(6)]
    gappy += [(NOW - timedelta(hours=12, minutes=5 * i), 100, True) for i in range(6)]
    geom = status.spark_geometry(status.spark_series(gappy, NOW))
    # Two clusters an hour apart: one is wide enough to be a line, the newest
    # falls in a single bucket and survives as a dot rather than vanishing.
    assert len(geom["segments"]) + len(geom["dots"]) == 2
    assert geom["dots"], "the newest bucket must still be drawn"


def test_spark_geometry_marks_failed_probes_for_the_template():
    series = status.spark_series(
        [(NOW - timedelta(minutes=5 * i), 5000, False) for i in range(6)], NOW
    )
    assert status.spark_geometry(series)["marks"]


def test_spark_geometry_has_nothing_to_draw_without_a_series():
    assert status.spark_geometry(None) is None

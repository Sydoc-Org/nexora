"""Tests for nx_lib.outage — log-storm detection and alert hysteresis.

The hysteresis tests are the point of this file: the whole feature is worthless
if it either stays silent during a real outage or floods support during a flap.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from nx_lib import outage

NOW = datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC)
LOCAL_NOW = datetime(2026, 8, 5, 12, 0, 0)


def _log(ts, level, message):
    return f"{ts:%Y-%m-%d %H:%M:%S},000 [{level}] nx_main workitems:412 {message}"


# --- signature normalization --------------------------------------------------


def test_normalize_collapses_ids_guids_and_quoted_literals():
    a = outage.normalize_signature("Invalid object name 'dbo.WorkitemTags' for id 4711")
    b = outage.normalize_signature("Invalid object name 'dbo.Other' for id 99")
    assert a == b, "same error shape must collapse to one storm signature"


def test_normalize_keeps_genuinely_different_errors_apart():
    a = outage.normalize_signature("Invalid object name 'dbo.X'")
    b = outage.normalize_signature("Login failed for user 'dbo.X'")
    assert a != b


# --- log parsing / storm detection --------------------------------------------


def test_parse_skips_traceback_continuation_lines():
    text = "\n".join(
        [
            _log(LOCAL_NOW, "ERROR", "boom"),
            "Traceback (most recent call last):",
            '  File "x.py", line 1, in <module>',
        ]
    )
    parsed = list(outage.parse_log_lines(text))
    assert len(parsed) == 1
    assert parsed[0][1] == "ERROR"


def test_storm_detected_when_signature_repeats_past_threshold():
    text = "\n".join(
        _log(LOCAL_NOW - timedelta(minutes=i % 10), "ERROR", f"Invalid object name 'dbo.T{i}'")
        for i in range(12)
    )
    storms = outage.detect_error_storms(text, LOCAL_NOW, window_min=15, min_count=10)
    assert len(storms) == 1
    assert storms[0]["count"] == 12
    assert storms[0]["key"].startswith("log:")


def test_no_storm_below_threshold():
    text = "\n".join(_log(LOCAL_NOW, "ERROR", "Invalid object name 'dbo.T'") for _ in range(3))
    assert outage.detect_error_storms(text, LOCAL_NOW, window_min=15, min_count=10) == []


def test_errors_outside_the_window_are_ignored():
    """Yesterday's resolved storm must not re-alert today."""
    old = LOCAL_NOW - timedelta(hours=5)
    text = "\n".join(_log(old, "ERROR", "Invalid object name 'dbo.T'") for _ in range(50))
    assert outage.detect_error_storms(text, LOCAL_NOW, window_min=15, min_count=10) == []


def test_warnings_do_not_count_as_a_storm():
    text = "\n".join(_log(LOCAL_NOW, "WARNING", "slow query") for _ in range(50))
    assert outage.detect_error_storms(text, LOCAL_NOW, window_min=15, min_count=10) == []


def test_storm_label_names_the_screaming_code_site():
    """A support ticket titled 'OUTAGE: log:8a89204' tells the reader nothing."""
    assert (
        outage.storm_label("nx_lib ui_prefs:65 load_ui_prefs error: x") == "log storm @ ui_prefs:65"
    )


def test_storm_label_falls_back_when_origin_is_unparsable():
    assert outage.storm_label("garbage") == "log storm"


def test_storm_key_is_stable_across_runs():
    """Dedupe depends on the same storm producing the same component id."""
    text = "\n".join(_log(LOCAL_NOW, "ERROR", f"Invalid object name 'dbo.T{i}'") for i in range(12))
    first = outage.detect_error_storms(text, LOCAL_NOW, min_count=10)[0]["key"]
    second = outage.detect_error_storms(text, LOCAL_NOW, min_count=10)[0]["key"]
    assert first == second


# --- hysteresis: the alert-flood guard ----------------------------------------


def _run(sequence, **kwargs):
    """Fold a sequence of (ok, minutes_offset) through update_component."""
    state, events = None, []
    for ok, offset in sequence:
        state, event = outage.update_component(
            state, ok, "detail", NOW + timedelta(minutes=offset), **kwargs
        )
        if event:
            events.append((event, offset))
    return state, events


def test_single_blip_does_not_alert():
    _state, events = _run([(True, 0), (False, 5), (True, 10)])
    assert events == [], "one failed probe is a blip, not an outage"


def test_opens_after_consecutive_failures():
    _state, events = _run([(False, 0), (False, 5)])
    assert events == [("open", 5)]


def test_repeated_failures_send_exactly_one_open():
    _state, events = _run([(False, i * 5) for i in range(20)])
    assert events == [("open", 5)], "an open incident must not re-mail every poll"


def test_recovery_sends_one_mail_after_min_hold():
    seq = [(False, 0), (False, 5), (True, 60), (True, 65)]
    _state, events = _run(seq, min_hold_s=600)
    assert events == [("open", 5), ("recover", 65)]


def test_flapping_component_sends_one_open_and_one_recover():
    """The ping_prdsrv lesson: ~200 mails from a link toggling every minute."""
    seq = [(False, 0), (False, 1)]
    for i in range(2, 40):  # alternate green/red every minute for 38 polls
        seq.append((i % 2 == 0, i))
    seq += [(True, 200), (True, 201)]  # then genuinely stable, past min-hold
    _state, events = _run(seq, min_hold_s=1800)
    assert [e for e, _ in events] == ["open", "recover"]


def test_recovery_suppressed_inside_min_hold():
    seq = [(False, 0), (False, 1), (True, 2), (True, 3)]
    state, events = _run(seq, min_hold_s=1800)
    assert events == [("open", 1)]
    assert state["open_since"] is not None, "incident stays open through min-hold"


def test_first_fail_at_records_the_first_bad_probe_not_the_open():
    state, _events = _run([(False, 0), (False, 5), (False, 10)])
    assert state["first_fail_at"] == NOW.isoformat()


def test_recovery_clears_incident_fields():
    state, _events = _run([(False, 0), (False, 5), (True, 100), (True, 105)], min_hold_s=600)
    assert state["open_since"] is None
    assert state["first_fail_at"] is None


def test_fail_threshold_of_one_opens_immediately():
    """Log storms alert on first sighting — the N-in-M window is their hysteresis."""
    _state, events = _run([(False, 0)], fail_threshold=1)
    assert events == [("open", 0)]


# --- state persistence --------------------------------------------------------


def test_load_state_missing_file_starts_empty(tmp_path):
    assert outage.load_state(tmp_path / "nope.json") == {"components": {}}


def test_load_state_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert outage.load_state(path) == {"components": {}}


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "state.json"
    state = {"components": {"db:NexoraDB": {"fail_streak": 2, "open_since": NOW.isoformat()}}}
    outage.save_state(path, state)
    assert outage.load_state(path) == state


def test_save_state_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    outage.save_state(path, {"components": {}})
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_persisted_open_incident_does_not_realert():
    """Restart safety: reloading an open incident must stay silent."""
    state, _ = outage.update_component(None, False, "d", NOW)
    state, _ = outage.update_component(state, False, "d", NOW + timedelta(minutes=5))
    reloaded = json.loads(json.dumps(state))  # survive a save/load cycle
    _state, event = outage.update_component(reloaded, False, "d", NOW + timedelta(minutes=10))
    assert event is None


# --- pruning ------------------------------------------------------------------


def test_prune_drops_stale_closed_components():
    old = (NOW - timedelta(days=30)).isoformat()
    state = {"components": {"log:abc": {"open_since": None, "updated_at": old}}}
    assert outage.prune_state(state, NOW)["components"] == {}


def test_prune_keeps_open_incidents_however_old():
    old = (NOW - timedelta(days=30)).isoformat()
    state = {"components": {"log:abc": {"open_since": old, "updated_at": old}}}
    assert "log:abc" in outage.prune_state(state, NOW)["components"]


def test_prune_drops_entries_with_an_unparsable_timestamp():
    """A hand-edited or half-written state file must not crash the monitor."""
    state = {"components": {"log:abc": {"open_since": None, "updated_at": "not-a-date"}}}
    assert outage.prune_state(state, NOW)["components"] == {}


def test_load_state_rejects_wrong_shape(tmp_path):
    """A JSON file that parses but is not our schema starts empty, not crashes."""
    path = tmp_path / "state.json"
    path.write_text('["not", "a", "dict"]', encoding="utf-8")
    assert outage.load_state(path) == {"components": {}}


def test_parse_skips_lines_with_an_impossible_timestamp():
    text = "2026-13-45 99:99:99,000 [ERROR] nx_main x:1 boom"
    assert list(outage.parse_log_lines(text)) == []


def test_prune_keeps_recent_components():
    recent = (NOW - timedelta(hours=1)).isoformat()
    state = {"components": {"db:NexoraDB": {"open_since": None, "updated_at": recent}}}
    assert "db:NexoraDB" in outage.prune_state(state, NOW)["components"]


# --- tail + rendering ---------------------------------------------------------


def test_tail_missing_file_returns_empty():
    assert outage.tail_text("/no/such/app.log") == ""


def test_tail_reads_only_the_last_chunk(tmp_path):
    path = tmp_path / "app.log"
    path.write_text("A" * 5000 + "\nTAIL\n", encoding="utf-8")
    assert "TAIL" in outage.tail_text(path, max_bytes=100)


@pytest.mark.parametrize("kind,marker", [("open", "OUTAGE"), ("recover", "RECOVERED")])
def test_render_alert_subject_reflects_kind(kind, marker):
    events = [{"component": "db:NexoraDB", "kind": kind, "first_seen": "x", "detail": "timeout"}]
    subject, _body = outage.render_alert(events, "PROD", NOW)
    assert marker in subject and "db:NexoraDB" in subject


def test_render_alert_batches_components_into_one_mail():
    events = [
        {"component": "db:NexoraDB", "kind": "open", "first_seen": "x", "detail": "timeout"},
        {"component": "http:site", "kind": "open", "first_seen": "x", "detail": "HTTP 503"},
    ]
    subject, body = outage.render_alert(events, "PROD", NOW)
    assert "db:NexoraDB" in subject and "http:site" in subject
    assert "timeout" in body and "HTTP 503" in body


def test_render_alert_caps_the_subject_but_keeps_every_component_in_the_body():
    """A real INT run produced 39 simultaneous storms; the subject was unusable."""
    events = [
        {"component": f"log storm @ mod:{i}", "kind": "open", "first_seen": "x", "detail": f"d{i}"}
        for i in range(39)
    ]
    subject, body = outage.render_alert(events, "PROD", NOW)
    assert "(+36 more)" in subject
    assert len(subject) < 120
    assert "log storm @ mod:38" in body, "body must still list every component"


def test_render_alert_escapes_log_excerpt():
    events = [
        {
            "component": "log:abc",
            "kind": "open",
            "first_seen": "x",
            "detail": "d",
            "excerpt": "<script>alert(1)</script>",
        }
    ]
    _subject, body = outage.render_alert(events, "PROD", NOW)
    assert "<script>" not in body and "&lt;script&gt;" in body

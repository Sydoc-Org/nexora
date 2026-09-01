import nx_lib.views.workitems as wv
from nx_lib.views.workitems import (
    _norm_field_token,
    drop_sensitive_options,
    strip_sensitive_fields,
)
from nx_lib.workitems import sensitivity


def test_norm_collapses_case_space_punct():
    assert _norm_field_token("Validation User") == "validationuser"
    assert _norm_field_token("validation_user") == "validationuser"
    assert _norm_field_token("ValidationUser") == "validationuser"
    assert _norm_field_token(None) == ""


def test_strip_removes_matching_octo_fields():
    fields = {"Validation User": "alice", "Amount": "50"}
    out = strip_sensitive_fields(fields, {"validationuser"})
    assert out == {"Amount": "50"}
    assert fields == {"Validation User": "alice", "Amount": "50"}  # input untouched


def test_strip_empty_blockset_is_noop_copy():
    fields = {"Validation User": "alice"}
    out = strip_sensitive_fields(fields, set())
    assert out == fields and out is not fields


def test_drop_sensitive_options_filters_by_value():
    opts = {
        "p1": [
            {"value": "validationuser", "label": "Validation User"},
            {"value": "doctype", "label": "Doc Type"},
        ]
    }
    out = drop_sensitive_options(opts, {"validationuser"})
    assert out == {"p1": [{"value": "doctype", "label": "Doc Type"}]}


def test_sensitive_blocked_keys_holds_perm_is_always_empty(monkeypatch):
    """The pure core (nx_lib.workitems.sensitivity, Flask-free, D4): the
    already-resolved permission bool is passed in explicitly rather than
    read from session -- no session/request/current_app in this module."""
    monkeypatch.setattr(sensitivity, "get_sensitive_field_keys", lambda: {"validationuser"})
    assert sensitivity.sensitive_blocked_keys(True) == set()
    assert sensitivity.sensitive_blocked_keys(False) == {"validationuser"}


def test_sensitive_blocked_keys_coerces_failed_lookup_to_empty_set(monkeypatch):
    """A None lookup (DB blip) must never widen to "block everything" -- it
    fails OPEN in-app, same as before the extraction."""
    monkeypatch.setattr(sensitivity, "get_sensitive_field_keys", lambda: None)
    assert sensitivity.sensitive_blocked_keys(False) == set()


def test_sensitive_blocked_tokens_holds_perm_is_always_empty(monkeypatch):
    monkeypatch.setattr(sensitivity, "get_sensitive_field_tokens", lambda: {"validationuser"})
    assert sensitivity.sensitive_blocked_tokens(True) == set()
    assert sensitivity.sensitive_blocked_tokens(False) == {"validationuser"}


def test_strip_export_fields_is_in_place_and_respects_empty_blockset():
    details_map = {
        ("default", 1): {"fields": {"Validation User": "alice", "Amount": "50"}},
        ("default", 2): {"fields": {}},
    }
    sensitivity.strip_export_fields(details_map, {"validationuser"})
    assert details_map[("default", 1)]["fields"] == {"Amount": "50"}

    unchanged = {("default", 1): {"fields": {"Validation User": "alice"}}}
    sensitivity.strip_export_fields(unchanged, set())
    assert unchanged[("default", 1)]["fields"] == {"Validation User": "alice"}


def test_strip_sensitive_from_detail_strips_fields_and_field_sources():
    data = {
        "fields": {"Validation User": "alice", "Amount": "50"},
        "field_sources": [{"key": "Validation User"}, {"key": "Amount"}],
    }
    out = sensitivity.strip_sensitive_from_detail(data, {"validationuser"})
    assert out["fields"] == {"Amount": "50"}
    assert out["field_sources"] == [{"key": "Amount"}]
    # Input untouched.
    assert data["fields"] == {"Validation User": "alice", "Amount": "50"}


def test_strip_sensitive_from_detail_empty_blockset_is_noop():
    data = {"fields": {"Amount": "50"}, "field_sources": [{"key": "Amount"}]}
    assert sensitivity.strip_sensitive_from_detail(data, set()) is data


def test_sensitive_blocked_wrapper_matches_core(monkeypatch):
    """nx_lib.views.workitems.sensitive_blocked_keys/tokens (the 0-arg,
    session-reading wrappers) duplicate -- rather than delegate to --
    nx_lib.workitems.sensitivity.sensitive_blocked_keys/tokens (the pure core,
    which takes the already-resolved permission bool explicitly, D4). That
    duplication is deliberate, but nothing else asserts the two stay in sync;
    this guards against a silent divergence for both permission states."""
    # Patch both bindings: the wrapper imported these names directly (`from
    # ..workitems.sensitivity import get_sensitive_field_keys, ...`), so it
    # holds its own reference independent of sensitivity's module attribute.
    monkeypatch.setattr(sensitivity, "get_sensitive_field_keys", lambda: {"validationuser"})
    monkeypatch.setattr(sensitivity, "get_sensitive_field_tokens", lambda: {"validationuser"})
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    monkeypatch.setattr(wv, "get_sensitive_field_tokens", lambda: {"validationuser"})

    for has_perm in (True, False):
        monkeypatch.setattr(wv, "has_permission", lambda code, _v=has_perm: _v)
        assert wv.sensitive_blocked_keys() == sensitivity.sensitive_blocked_keys(has_perm)
        assert wv.sensitive_blocked_tokens() == sensitivity.sensitive_blocked_tokens(has_perm)

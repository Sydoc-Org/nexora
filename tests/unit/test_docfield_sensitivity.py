from nx_lib.views.workitems import (
    _norm_field_token,
    drop_sensitive_options,
    strip_sensitive_fields,
)


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

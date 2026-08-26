# tests/unit/test_reporting_scope.py
"""Unit tests for the reporting scope resolver (clients + processes union).

`_effective_scope` is pure: it takes a report definition's `scope` and the
caller's allowed `<client>.<process>` list and returns the processes actually in
scope. The `reporting.scope.process.*` grant (the `allowed` arg) is the security
boundary — anything requested but not granted is dropped.
"""

import pytest

from nx_lib.views.reporting import _client_of, _effective_scope

ALLOWED = [
    "compass.01_Invoice_SAP",
    "elektromaterial.02_Invoice",
    "privera.02_InitialScan",
    "privera.02_Posteingang",
    "privera.03_Invoice_New",
]


def _rd(**scope):
    return {"scope": scope}


def test_client_of_splits_on_first_dot():
    assert _client_of("privera.02_InitialScan") == "privera"
    assert _client_of("compass.01_Invoice_SAP") == "compass"
    # No dot -> the whole string is the client.
    assert _client_of("loose") == "loose"


def test_empty_scope_returns_all_allowed():
    assert _effective_scope(_rd(), ALLOWED) == ALLOWED
    assert _effective_scope(_rd(clients=[], processes=[]), ALLOWED) == ALLOWED
    assert _effective_scope({}, ALLOWED) == ALLOWED


def test_missing_scope_key_returns_all_allowed():
    # _effective_scope must tolerate a definition with no scope at all.
    assert _effective_scope({"scope": None}, ALLOWED) == ALLOWED


def test_processes_only_intersect_with_allowed():
    out = _effective_scope(_rd(processes=["privera.02_InitialScan"]), ALLOWED)
    assert out == ["privera.02_InitialScan"]


def test_processes_drop_non_allowed():
    # A requested process the caller isn't granted is silently dropped.
    out = _effective_scope(_rd(processes=["privera.02_InitialScan", "secret.99_Hidden"]), ALLOWED)
    assert out == ["privera.02_InitialScan"]


def test_clients_only_expand_to_all_their_processes():
    out = _effective_scope(_rd(clients=["privera"]), ALLOWED)
    assert out == [
        "privera.02_InitialScan",
        "privera.02_Posteingang",
        "privera.03_Invoice_New",
    ]


def test_clients_drop_non_allowed():
    # A client the caller has no grants under contributes nothing.
    out = _effective_scope(_rd(clients=["privera", "acme"]), ALLOWED)
    assert out == [
        "privera.02_InitialScan",
        "privera.02_Posteingang",
        "privera.03_Invoice_New",
    ]


def test_clients_and_processes_compose_by_union():
    # A whole client OR a single extra process from another client.
    out = _effective_scope(_rd(clients=["compass"], processes=["privera.02_Posteingang"]), ALLOWED)
    assert out == ["compass.01_Invoice_SAP", "privera.02_Posteingang"]


def test_result_preserves_allowed_order_and_dedupes():
    # Requesting a process AND its client must not double-count it.
    out = _effective_scope(_rd(clients=["privera"], processes=["privera.02_InitialScan"]), ALLOWED)
    assert out == [
        "privera.02_InitialScan",
        "privera.02_Posteingang",
        "privera.03_Invoice_New",
    ]


# ---------------------------------------------------------------------------
# _labeled_field_values: labelWith pair shaping + grantScoped filtering for
# /api/reporting/field_values (backlog_history process picker).
# ---------------------------------------------------------------------------

from nx_lib.views.reporting import _labeled_field_values  # noqa: E402

PAIR_ROWS = [
    ("01_EasyTax", "Bucherer"),
    ("01_Invoice_SAP", "Compass"),
    ("02_InitialScan", "Privera"),
    ("05_MGBE", "Sydoc"),
]


def test_labeled_field_values_builds_lowercased_client_labels():
    values, labels = _labeled_field_values(PAIR_ROWS)
    assert values == ["01_EasyTax", "01_Invoice_SAP", "02_InitialScan", "05_MGBE"]
    assert labels["01_Invoice_SAP"] == "compass.01_Invoice_SAP"
    assert labels["01_EasyTax"] == "bucherer.01_EasyTax"


def test_labeled_field_values_grant_scope_drops_unpermitted():
    allowed = {"compass.01_Invoice_SAP", "privera.02_InitialScan"}
    values, labels = _labeled_field_values(PAIR_ROWS, allowed)
    assert values == ["01_Invoice_SAP", "02_InitialScan"]
    assert set(labels) == set(values)


def test_labeled_field_values_duplicate_value_falls_back_to_bare_label():
    rows = [("02_Invoice", "Compass"), ("02_Invoice", "Privera")]
    values, labels = _labeled_field_values(rows)
    assert values == ["02_Invoice"]
    assert labels["02_Invoice"] == "02_Invoice"
    # bare label is never in the client.process grant set -> scoped out
    assert _labeled_field_values(rows, {"compass.02_Invoice"})[0] == []


def test_labeled_field_values_null_companion_labels_bare():
    values, labels = _labeled_field_values([("01_SPARK", None)])
    assert values == ["01_SPARK"] and labels["01_SPARK"] == "01_SPARK"


# ---------------------------------------------------------------------------
# _load_process_configs / _load_field_col_maps: fail-loud guards on a
# registry load failure (mapping_config.registry() -> None must raise, never
# silently degrade to an empty catalog that looks like "no processes in
# scope" -- see the RuntimeError docstrings on both functions).
# ---------------------------------------------------------------------------

from nx_lib import mapping_config  # noqa: E402
from nx_lib.views.reporting import _load_field_col_maps, _load_process_configs  # noqa: E402


def test_load_process_configs_raises_on_registry_failure(monkeypatch):
    monkeypatch.setattr(mapping_config, "registry", lambda: None)
    with pytest.raises(RuntimeError):
        _load_process_configs(["privera.02_InitialScan"])


def test_load_field_col_maps_raises_on_registry_failure(monkeypatch):
    monkeypatch.setattr(mapping_config, "registry", lambda: None)
    with pytest.raises(RuntimeError):
        _load_field_col_maps(["privera.02_InitialScan"])

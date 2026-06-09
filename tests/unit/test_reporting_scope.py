# tests/unit/test_reporting_scope.py
"""Unit tests for the reporting scope resolver (clients + processes union).

`_effective_scope` is pure: it takes a report definition's `scope` and the
caller's allowed `<client>.<process>` list and returns the processes actually in
scope. The `reporting.scope.process.*` grant (the `allowed` arg) is the security
boundary — anything requested but not granted is dropped.
"""

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

"""Cross-tenant / cross-process IDOR gate on the workitem detail endpoints
(security audit #193, finding 1).

api_get_media_info / api_get_media_raw / get_audithistory resolve which
tenant's runtime to query from a caller-supplied ?client= hint and fetch an
arbitrary workitem id, but historically checked only the flat
workitems.details.view* permission code -- never that the caller is entitled
to the workitem's actual (ClientName, process) pair. A user granted one
process could set ?client= and iterate ids to read another tenant's document
pages, extracted fields and audit trail.

The gate now resolves the workitem's real (client, process) pair (the same
namespace the list query authorizes via t_Processes.ClientName / .Name) and
403s unless the caller holds a process.<client>.<process>.view
grant for it. Matching is case-insensitive (mirrors the DB's collation) and
fails closed when the pair can't be resolved.
"""

import pytest


def _grant(monkeypatch, perms):
    """Seed session['permissions'] via the before_request reload seam."""
    import nx_lib.hooks as hooks

    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: perms)


VIEW_PERMS = [
    "workitems.details.view",
    "workitems.details.images.view",
    "workitems.details.audit.view",
    "workitems.details.fields.view",
]


@pytest.mark.parametrize(
    "url",
    [
        "/api/get_media_info/1216?client=ms02",
        "/api/get_media_raw/1216/0?client=ms02",
        "/api/get_audithistory/1216?client=ms02",
    ],
)
def test_detail_endpoint_blocks_unentitled_pair(user_client, monkeypatch, url):
    """Caller holds a grant for (acme, procA) only; the requested workitem
    really belongs to (ms02client, procB) -> 403 on every detail endpoint."""
    import nx_lib.views.workitems as wv

    _grant(monkeypatch, [*VIEW_PERMS, "process.acme.procA.view"])
    monkeypatch.setattr(
        wv, "process_pair_for_workitem", lambda wid, client_hint=None: ("ms02client", "procB")
    )

    resp = user_client.get(url)
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "url",
    [
        "/api/get_media_info/1216?client=ms02",
        "/api/get_media_raw/1216/0?client=ms02",
        "/api/get_audithistory/1216?client=ms02",
    ],
)
def test_detail_endpoint_allows_entitled_pair_case_insensitive(user_client, monkeypatch, url):
    """Caller is entitled to (acme, procA); the workitem's pair matches but in
    different case -> must NOT be blocked (any non-403 outcome is fine; the
    Octo fetch itself may 404/500 in CI)."""
    import nx_lib.views.workitems as wv

    _grant(monkeypatch, [*VIEW_PERMS, "process.acme.procA.view"])
    monkeypatch.setattr(
        wv, "process_pair_for_workitem", lambda wid, client_hint=None: ("ACME", "PROCA")
    )
    monkeypatch.setattr(
        wv, "get_domain_for_workitem", lambda wid, client_hint=None: "d.example.com"
    )
    monkeypatch.setattr(wv, "get_workitemdata_param", lambda wid, domain: None)

    resp = user_client.get(url)
    assert resp.status_code != 403


@pytest.mark.parametrize(
    "url",
    [
        "/api/get_media_info/1216?client=ms02",
        "/api/get_media_raw/1216/0?client=ms02",
        "/api/get_audithistory/1216?client=ms02",
    ],
)
def test_detail_endpoint_fails_closed_when_pair_unresolvable(user_client, monkeypatch, url):
    """Pair can't be resolved (workitem not found / lookup error -> None):
    the gate must fail closed (403), never open."""
    import nx_lib.views.workitems as wv

    _grant(monkeypatch, [*VIEW_PERMS, "process.acme.procA.view"])
    monkeypatch.setattr(wv, "process_pair_for_workitem", lambda wid, client_hint=None: None)

    resp = user_client.get(url)
    assert resp.status_code == 403

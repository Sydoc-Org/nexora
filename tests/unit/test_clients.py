"""Client registry: default always present; octo creds resolve by domain."""

from nx_lib import clients


def test_default_client_present():
    assert "default" in clients.CLIENTS
    d = clients.CLIENTS["default"]
    assert d.code == "default"
    assert d.dialect == "tsql"


def test_octo_creds_for_unknown_domain_falls_back_to_default(monkeypatch):
    from nx_lib import config as cfg

    monkeypatch.setattr(cfg, "OCTO_CLIENT_ID", "DEF_ID")
    monkeypatch.setattr(cfg, "OCTO_CLIENT_SECRET", "DEF_SECRET")
    monkeypatch.setattr(cfg, "OCTO_GRANT_TYPE", "client_credentials")
    cid, secret, grant = clients.octo_creds_for_domain("nobody.example")
    assert cid == "DEF_ID"
    assert secret == "DEF_SECRET"
    assert grant == "client_credentials"


def test_octo_creds_resolve_by_registered_domain():
    # The default client's own domain resolves to the default creds.
    d = clients.CLIENTS["default"]
    cid, secret, grant = clients.octo_creds_for_domain(d.octo_domain)
    assert cid == d.octo_client_id
    assert secret == d.octo_secret

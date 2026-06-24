# tests/unit/test_clients_docfields.py
"""ClientConfig carries a per-client doc-field engine + dialect."""

from nx_lib.clients import CLIENTS, ClientConfig


def test_clientconfig_has_docfields_fields():
    fields = ClientConfig.__dataclass_fields__
    assert "docfields_engine" in fields
    assert "docfields_dialect" in fields


def test_default_client_docfields_dialect_is_tsql():
    assert CLIENTS["default"].docfields_dialect == "tsql"


def test_ms02_client_docfields_dialect_is_postgres_when_registered():
    # ms02 may be absent on a box without MS02 runtime creds; only assert when
    # it is registered. Its doc-field engine may still be None.
    if "ms02" in CLIENTS:
        assert CLIENTS["ms02"].docfields_dialect == "postgres"

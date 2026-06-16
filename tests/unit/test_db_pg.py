"""Postgres URL builder + MS02 engine guard."""

from sqlalchemy.engine import URL

from nx_lib.db import get_pg_url


def test_get_pg_url_shape():
    url = get_pg_url("pg.example.net", "ms02db", "ro_user", "p@ss:word/!", port="5432")
    assert isinstance(url, URL)
    assert url.drivername == "postgresql+psycopg2"
    assert url.host == "pg.example.net"
    assert url.database == "ms02db"
    assert url.username == "ro_user"
    assert url.password == "p@ss:word/!"
    assert url.port == 5432
    assert url.query.get("sslmode") == "require"


def test_get_pg_url_renders_with_sslmode():
    url = get_pg_url("h", "d", "u", "pw")
    rendered = url.render_as_string(hide_password=False)
    assert rendered.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in rendered


def test_get_pg_url_supports_cert_verification():
    # TLS hardening path: verify-full + a root-CA bundle closes the MITM gap.
    url = get_pg_url(
        "h",
        "d",
        "u",
        "pw",
        sslmode="verify-full",
        sslrootcert="/etc/ssl/azure-root.pem",
    )
    assert url.query.get("sslmode") == "verify-full"
    assert url.query.get("sslrootcert") == "/etc/ssl/azure-root.pem"


def test_get_pg_url_omits_sslrootcert_when_unset():
    # Default mode carries no sslrootcert key (no bundle provisioned yet).
    url = get_pg_url("h", "d", "u", "pw")
    assert "sslrootcert" not in url.query

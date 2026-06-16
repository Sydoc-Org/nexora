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

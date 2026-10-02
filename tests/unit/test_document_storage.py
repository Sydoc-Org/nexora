"""Unit tests for nx_lib.document_storage (issue #398): storage-name ->
engine resolution by convention. No DB: the client registry and
create_engine are patched."""

from unittest.mock import MagicMock

import pytest

from nx_lib import document_storage as ds
from nx_lib.clients import ClientConfig


def _client(code, dialect, engine):
    return ClientConfig(
        code=code,
        runtime_engine=engine,
        dialect=dialect,
        octo_domain="octo.test",
        octo_client_id=None,
        octo_secret=None,
        octo_grant_type=None,
    )


@pytest.fixture
def registry(monkeypatch):
    tsql_engine = MagicMock(name="octo")
    pg_engine = MagicMock(name="ms02")
    pg_engine.url.set.side_effect = lambda database: f"pg://{database}"
    monkeypatch.setattr(
        ds,
        "CLIENTS",
        {
            "default": _client("default", "tsql", tsql_engine),
            "ms02": _client("ms02", "postgres", pg_engine),
        },
    )
    monkeypatch.setattr(ds, "_engines", {})
    created = []

    def _create_engine(url, **kw):
        created.append(url)
        return MagicMock(name=f"engine:{url}")

    monkeypatch.setattr(ds, "create_engine", _create_engine)
    monkeypatch.setattr(ds.db, "get_db_url", lambda name: f"mssql://{name}")
    return {"created": created, "tsql": tsql_engine, "pg": pg_engine}


def test_default_storage_is_the_runtime_engine(registry):
    assert ds.storage_engine_for("default", "<Default>") is registry["tsql"]
    assert ds.storage_engine_for("default", None) is registry["tsql"]
    assert ds.storage_engine_for("default", "") is registry["tsql"]
    assert registry["created"] == []


def test_named_storage_is_a_sibling_database_created_once(registry):
    first = ds.storage_engine_for("default", "EM_Storage")
    again = ds.storage_engine_for("default", "EM_Storage")
    assert first is again
    assert registry["created"] == ["mssql://EM_Storage"]


def test_postgres_storage_swaps_the_database_on_the_runtime_url(registry):
    ds.storage_engine_for("ms02", "Documentstorage")
    assert registry["created"] == ["pg://Documentstorage"]


def test_unknown_client_and_unsafe_names_are_refused(registry):
    with pytest.raises(RuntimeError):
        ds.storage_engine_for("nope", "EM_Storage")
    for bad in ("EM Storage", "EM;DROP", "../x", "EM_Storage;Database=master"):
        with pytest.raises(RuntimeError):
            ds.storage_engine_for("default", bad)
    assert registry["created"] == []


def test_runtime_for_maps_dialects(registry):
    assert ds.runtime_for("default") == (registry["tsql"], "tsql")
    assert ds.runtime_for("ms02") == (registry["pg"], "postgres")
    assert ds.runtime_for("nope") is None


def test_list_storages_reads_the_runtime_and_skips_blank_names(registry):
    cur = MagicMock()
    cur.fetchall.return_value = [("Privera_Invoice_Storage",), (None,), ("<Default>",)]
    conn = MagicMock()
    conn.cursor.return_value = cur
    registry["tsql"].raw_connection.return_value = conn
    assert ds.list_storages("default") == ["Privera_Invoice_Storage", "<Default>"]
    assert ds.list_storages("nope") == []
    conn.close.assert_called_once()


def test_list_storages_quotes_identifiers_on_postgres(registry):
    cur = MagicMock()
    cur.fetchall.return_value = [("Documentstorage",)]
    conn = MagicMock()
    conn.cursor.return_value = cur
    registry["pg"].raw_connection.return_value = conn
    assert ds.list_storages("ms02") == ["Documentstorage"]
    sql = cur.execute.call_args[0][0]
    assert '"t_DocumentStorages"' in sql and '"Name"' in sql
    conn.close.assert_called_once()


def test_fetch_workitem_tables_binds_the_registry_resolvers(registry, monkeypatch):
    """The production entry point is the pure fetch with this module's two
    resolvers injected -- nothing else."""
    captured = {}

    def fake_fetch(ids_by_client, *, runtime_for, storage_for, logger=None):
        captured.update(
            ids=ids_by_client, runtime_for=runtime_for, storage_for=storage_for, logger=logger
        )
        return {"sentinel": True}

    monkeypatch.setattr(ds._tables, "fetch_workitem_tables", fake_fetch)
    log = MagicMock()
    assert ds.fetch_workitem_tables({"default": [1]}, logger=log) == {"sentinel": True}
    assert captured["ids"] == {"default": [1]}
    assert captured["runtime_for"] is ds.runtime_for
    assert captured["storage_for"] is ds.storage_engine_for
    assert captured["logger"] is log

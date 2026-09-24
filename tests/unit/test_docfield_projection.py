"""Unit tests for nx_lib.workitems.query.fetch_docfield_values (issue #341):
the per-page doc-field projection behind /api/v1/workitems?include=fields.

Pure: mapping_config is stubbed and both engines are fakes, so no DB.
"""

import logging
from unittest.mock import MagicMock

import pytest

from nx_lib import mapping_config
from nx_lib.mapping_config import FieldMapping, ProcessSource
from nx_lib.workitems.query import fetch_docfield_values

LOG = logging.getLogger("test")


def _src(client, process, table, alias, join_condition):
    return ProcessSource(
        client=client,
        process=process,
        table=table,
        alias=alias,
        join_condition=join_condition,
        time_filter="s.ImportDate > '2020-01-01'",
        suggestion_time_filter=None,
        export_column=None,
        import_column=None,
        workitem_column=None,
        extra_condition=None,
        id_column_type=None,
    )


def _map(client, process, key, column):
    return FieldMapping(
        client=client, process=process, field_key=key, column=column, column_type="varchar"
    )


def _fake_engine(rows):
    """raw_connection().cursor() whose fetchall() returns rows; records SQL."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, cur


@pytest.fixture
def stub_registry(monkeypatch):
    """Install mapping rows/sources per client; returns the recorder dict."""
    state = {"mappings": [], "sources": []}

    def _mappings_for(client, processes=None, field_keys=None):
        wanted = set(processes) if processes is not None else None
        keys = {k.lower() for k in field_keys} if field_keys is not None else None
        return [
            m
            for m in state["mappings"]
            if m.client == client
            and (wanted is None or m.process in wanted)
            and (keys is None or m.field_key in keys)
        ]

    def _sources_for(client, processes=None):
        wanted = set(processes) if processes is not None else None
        return [
            s
            for s in state["sources"]
            if s.client == client and (wanted is None or s.process in wanted)
        ]

    monkeypatch.setattr(mapping_config, "mappings_for", _mappings_for)
    monkeypatch.setattr(mapping_config, "sources_for", _sources_for)
    return state


def test_default_leg_projects_mapped_columns_keyed_by_client_and_id(stub_registry):
    stub_registry["sources"] = [
        _src("default", "sydoc.Inv", "dbo.InvoiceStat", "s", "t.ID = s.WID")
    ]
    stub_registry["mappings"] = [
        _map("default", "sydoc.Inv", "invoicenr", "InvoiceNr"),
        _map("default", "sydoc.Inv", "kundennr", "KundenNr"),
    ]
    eng, cur = _fake_engine([(1216, "INV-1", "44201"), (1217, None, "  ")])

    out = fetch_docfield_values(
        {"default": [1216, 1217]},
        ["sydoc.Inv"],
        {"invoicenr", "kundennr"},
        engine_statistics_db=eng,
        engine_ms02_docfields_pg=None,
        logger=LOG,
    )

    assert out == {("default", 1216): {"invoicenr": "INV-1", "kundennr": "44201"}}
    sql, params = cur.execute.call_args[0]
    assert "s.InvoiceNr" in sql and "s.KundenNr" in sql
    assert "s.WID IN (?, ?)" in sql
    assert params == [1216, 1217]
    # ponytail: keyed lookup, so no time window is applied (see the helper).
    assert "ImportDate" not in sql


def test_unrequested_and_sensitive_keys_are_never_selected(stub_registry):
    stub_registry["sources"] = [
        _src("default", "sydoc.Inv", "dbo.InvoiceStat", "s", "t.ID = s.WID")
    ]
    stub_registry["mappings"] = [
        _map("default", "sydoc.Inv", "invoicenr", "InvoiceNr"),
        _map("default", "sydoc.Inv", "ahvnr", "AhvNr"),  # sensitive -> not in allow-set
    ]
    eng, cur = _fake_engine([(1216, "INV-1")])

    out = fetch_docfield_values(
        {"default": [1216]},
        ["sydoc.Inv"],
        {"invoicenr"},
        engine_statistics_db=eng,
        engine_ms02_docfields_pg=None,
        logger=LOG,
    )

    assert out == {("default", 1216): {"invoicenr": "INV-1"}}
    sql = cur.execute.call_args[0][0]
    assert "AhvNr" not in sql


def test_empty_allow_set_queries_nothing(stub_registry):
    eng = MagicMock()
    assert (
        fetch_docfield_values(
            {"default": [1]},
            ["sydoc.Inv"],
            set(),
            engine_statistics_db=eng,
            engine_ms02_docfields_pg=None,
            logger=LOG,
        )
        == {}
    )
    eng.raw_connection.assert_not_called()


def test_ms02_leg_matches_ids_as_text(stub_registry):
    stub_registry["sources"] = [_src("ms02", "sydoc.PDBS", 'public."DossierStatistik"', None, "")]
    stub_registry["mappings"] = [_map("ms02", "sydoc.PDBS", "invoicenr", "InvoiceNr")]
    eng, cur = _fake_engine([("1216", "MS02-1")])
    # id column comes off ProcessSource.join_condition via _ms02_id_column
    stub_registry["sources"][0] = _src(
        "ms02", "sydoc.PDBS", 'public."DossierStatistik"', "s", 't."ID" = s.WorkItemID'
    )

    out = fetch_docfield_values(
        {"ms02": [1216]},
        ["sydoc.PDBS"],
        {"invoicenr"},
        engine_statistics_db=None,
        engine_ms02_docfields_pg=eng,
        logger=LOG,
    )

    assert out == {("ms02", 1216): {"invoicenr": "MS02-1"}}
    sql, params = cur.execute.call_args[0]
    assert '"WorkItemID"::text = ANY(%s)' in sql
    assert params == [["1216"]]


def test_ms02_without_engine_fails_closed_to_no_fields(stub_registry):
    stub_registry["sources"] = [
        _src("ms02", "sydoc.PDBS", 'public."DossierStatistik"', "s", 't."ID" = s.WorkItemID')
    ]
    stub_registry["mappings"] = [_map("ms02", "sydoc.PDBS", "invoicenr", "InvoiceNr")]

    out = fetch_docfield_values(
        {"ms02": [1216]},
        ["sydoc.PDBS"],
        {"invoicenr"},
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        logger=LOG,
    )
    assert out == {}


def test_unsafe_column_identifier_is_dropped(stub_registry):
    stub_registry["sources"] = [
        _src("default", "sydoc.Inv", "dbo.InvoiceStat", "s", "t.ID = s.WID")
    ]
    stub_registry["mappings"] = [
        _map("default", "sydoc.Inv", "invoicenr", "InvoiceNr; DROP TABLE x--"),
    ]
    eng = MagicMock()

    out = fetch_docfield_values(
        {"default": [1216]},
        ["sydoc.Inv"],
        {"invoicenr"},
        engine_statistics_db=eng,
        engine_ms02_docfields_pg=None,
        logger=LOG,
    )
    assert out == {}
    eng.raw_connection.assert_not_called()


def test_db_failure_propagates_so_the_page_fails_strictly(stub_registry):
    stub_registry["sources"] = [
        _src("default", "sydoc.Inv", "dbo.InvoiceStat", "s", "t.ID = s.WID")
    ]
    stub_registry["mappings"] = [_map("default", "sydoc.Inv", "invoicenr", "InvoiceNr")]
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError("StatisticsDB down")

    with pytest.raises(RuntimeError):
        fetch_docfield_values(
            {"default": [1216]},
            ["sydoc.Inv"],
            {"invoicenr"},
            engine_statistics_db=eng,
            engine_ms02_docfields_pg=None,
            logger=LOG,
        )

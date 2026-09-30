"""Unit tests for nx_lib.workitems.tables (issue #398): the SystemTableList
XML parser, the leaf-document rule and the per-page fetch behind
/api/v1/workitems?include=tables.

Pure: engines are fakes recording the SQL they were given, so no DB.
"""

from unittest.mock import MagicMock

import pytest

from nx_lib.workitems.tables import (
    DEFAULT_STORAGE_NAME,
    SYSTEM_TABLE_LIST_MEDIA_TYPE,
    fetch_workitem_tables,
    leaf_documents,
    parse_table_list,
)

# The shape as stored on INT/PROD (utf-8 BOM, XML declaration, is-null cells).
XML_TABLES = (
    '﻿<?xml version="1.0" encoding="utf-8"?>\r\n'
    "<ModelObjectList>\r\n"
    "  <Item>\r\n"
    '    <STGTable type="Table">\r\n'
    '      <internalRows type="Rows">\r\n'
    '        <item type="Row">\r\n'
    '          <ID type="String">row-1</ID>\r\n'
    '          <internalCells type="Cells">\r\n'
    '            <item type="Cell">\r\n'
    '              <CellValue type="Value"><Text type="String">195.2</Text></CellValue>\r\n'
    '              <ColumnName type="String">TabNetAmount</ColumnName>\r\n'
    '              <CapturedValue type="String">0.00</CapturedValue>\r\n'
    "            </item>\r\n"
    '            <item type="Cell">\r\n'
    '              <CellValue type="Value"><Text type="String" is-null="true" /></CellValue>\r\n'
    '              <ColumnName type="String">TabVatAmount</ColumnName>\r\n'
    '              <CapturedValue type="String" is-null="true" />\r\n'
    "            </item>\r\n"
    '            <item type="Cell">\r\n'
    '              <CellValue type="Value"><Text type="String" is-null="true" /></CellValue>\r\n'
    '              <ColumnName type="String">TabVatRate</ColumnName>\r\n'
    '              <CapturedValue type="String">8.1</CapturedValue>\r\n'
    "            </item>\r\n"
    '            <item type="Cell">\r\n'
    '              <CellValue type="Value"><Text type="String"></Text></CellValue>\r\n'
    '              <ColumnName type="String">TabVatCode</ColumnName>\r\n'
    "            </item>\r\n"
    "          </internalCells>\r\n"
    "        </item>\r\n"
    '        <item type="Row">\r\n'
    '          <ID type="String">row-2</ID>\r\n'
    '          <internalCells type="Cells">\r\n'
    '            <item type="Cell">\r\n'
    '              <CellValue type="Value"><Text type="String" is-null="true" /></CellValue>\r\n'
    '              <ColumnName type="String">TabNetAmount</ColumnName>\r\n'
    "            </item>\r\n"
    "          </internalCells>\r\n"
    "        </item>\r\n"
    "      </internalRows>\r\n"
    '      <internalColumnDefinition type="ColumnDefs">\r\n'
    '        <item type="ColumnDef"><Name type="String">TabNetAmount</Name></item>\r\n'
    '        <item type="ColumnDef"><Name type="String">TabVatAmount</Name></item>\r\n'
    '        <item type="ColumnDef"><Name type="String">TabVatRate</Name></item>\r\n'
    '        <item type="ColumnDef"><Name type="String">TabVatCode</Name></item>\r\n'
    "      </internalColumnDefinition>\r\n"
    '      <TableName type="String">TabVat</TableName>\r\n'
    "    </STGTable>\r\n"
    "  </Item>\r\n"
    "  <Item>\r\n"
    '    <STGTable type="Table">\r\n'
    '      <internalColumnDefinition type="ColumnDefs">\r\n'
    '        <item type="ColumnDef"><Name type="String">OrdPk</Name></item>\r\n'
    "      </internalColumnDefinition>\r\n"
    '      <TableName type="String">TabOrder</TableName>\r\n'
    "    </STGTable>\r\n"
    "  </Item>\r\n"
    "</ModelObjectList>"
)


# ---------------------------------------------------------------- parser --- #


def test_parse_applies_the_detail_endpoint_rules():
    """Null cells skipped, CapturedValue fallback, empty string kept, rows
    with no valued cell dropped, tables with no rows dropped, columns in
    first-seen valued order -- byte-identical to what _api_tables serves."""
    tables = parse_table_list(XML_TABLES.encode("utf-8"))
    assert tables == [
        {
            "title": "TabVat",
            "columns": ["TabNetAmount", "TabVatRate", "TabVatCode"],
            "rows": [
                [
                    {"column": "TabNetAmount", "value": "195.2"},
                    {"column": "TabVatRate", "value": "8.1"},
                    {"column": "TabVatCode", "value": ""},
                ]
            ],
        }
    ]


def test_parse_accepts_str_bytes_memoryview_and_empty():
    as_bytes = XML_TABLES.encode("utf-8")
    assert parse_table_list(XML_TABLES) == parse_table_list(as_bytes)
    assert parse_table_list(memoryview(as_bytes)) == parse_table_list(as_bytes)
    assert parse_table_list(b"") == []
    assert parse_table_list("") == []
    assert parse_table_list(None) == []


def test_parse_raises_on_corrupt_xml():
    # A corrupt stream is a backend failure (500), never an empty table.
    with pytest.raises(Exception):  # noqa: B017 -- any parse error will do
        parse_table_list(b"<ModelObjectList><Item>")


# ------------------------------------------------------------ leaf rule --- #


def test_leaf_documents_descends_containers_and_keeps_leaf_roots():
    children = {"root-a": ["c2", "c1"], "c1": ["g1"]}
    leaves = leaf_documents(["root-a", "root-b"], children)
    # A container contributes nothing itself; children are walked sorted.
    assert leaves == {"root-a": ["g1", "c2"], "root-b": ["root-b"]}


# ---------------------------------------------------------------- fetch --- #


class _FakeEngine:
    """raw_connection().cursor() that answers by matching the SQL text and
    records every (sql, params) it executed."""

    def __init__(self, answers):
        self.answers = answers  # list of (substring, rows)
        self.executed = []

    def raw_connection(self):
        engine = self

        class _Cursor:
            def __init__(self):
                self._rows = []

            def execute(self, sql, params=None):
                engine.executed.append((sql, params))
                for needle, rows in engine.answers:
                    if needle in sql:
                        self._rows = rows(params) if callable(rows) else rows
                        return
                self._rows = []

            def fetchall(self):
                return self._rows

            def close(self):
                pass

        conn = MagicMock()
        conn.cursor.return_value = _Cursor()
        return conn


def _runtime(rows):
    # Needle without the FROM so it matches the quoted Postgres spelling too.
    return _FakeEngine([("t_WorkItems", rows)])


def test_fetch_reads_one_storage_pass_per_page_and_keys_by_client_and_id():
    runtime = _runtime(
        [
            (1216, "AAAA-1", "EM_Storage"),
            (77, "BBBB-2", "EM_Storage"),
            (5, "CCCC-3", None),  # no storage row -> the runtime DB itself
        ]
    )
    em = _FakeEngine(
        [
            ("FROM t_Documents", []),
            (
                "FROM t_DocumentMedia",
                [("aaaa-1", XML_TABLES.encode("utf-8")), ("bbbb-2", b"")],
            ),
        ]
    )
    default_store = _FakeEngine([("FROM t_Documents", []), ("FROM t_DocumentMedia", [])])
    seen = []

    def storage_for(client, name):
        seen.append((client, name))
        return {"EM_Storage": em, DEFAULT_STORAGE_NAME: default_store}[name]

    out = fetch_workitem_tables(
        {"default": [1216, 77, 5, None]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=storage_for,
    )
    assert set(out) == {("default", 1216), ("default", 77), ("default", 5)}
    assert [t["title"] for t in out[("default", 1216)]] == ["TabVat"]
    assert out[("default", 77)] == []  # stream present but empty
    assert out[("default", 5)] == []  # no stream at all
    # One storage pass each, resolved by the runtime's storage name.
    assert seen == [("default", "EM_Storage"), ("default", DEFAULT_STORAGE_NAME)]
    media_calls = [p for sql, p in em.executed if "FROM t_DocumentMedia" in sql]
    assert len(media_calls) == 1
    assert media_calls[0][0] == SYSTEM_TABLE_LIST_MEDIA_TYPE
    # Ids are keyed lowercase whatever case the driver returned.
    assert sorted(media_calls[0][1:]) == ["aaaa-1", "bbbb-2"]


def test_fetch_uses_leaf_documents_for_containers():
    """A batch root has children; its own table stream must be ignored and
    the children's read instead (same rule as the detail endpoint)."""
    runtime = _runtime([(9, "ROOT", "Compass_Storage")])
    store = _FakeEngine(
        [
            (
                "FROM t_Documents",
                lambda params: [("kid-1", "root"), ("kid-2", "root")] if params == ["root"] else [],
            ),
            (
                "FROM t_DocumentMedia",
                lambda params: [
                    (doc, XML_TABLES.encode("utf-8"))
                    for doc in params[1:]
                    if doc in ("kid-1", "root")
                ],
            ),
        ]
    )
    out = fetch_workitem_tables(
        {"default": [9]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=lambda c, n: store,
    )
    media_calls = [p for sql, p in store.executed if "FROM t_DocumentMedia" in sql]
    assert sorted(media_calls[0][1:]) == ["kid-1", "kid-2"]  # never "root"
    assert [t["title"] for t in out[("default", 9)]] == ["TabVat"]


def test_fetch_postgres_dialect_uses_array_binds():
    runtime = _runtime([(3, "abc", "Documentstorage")])
    store = _FakeEngine([('FROM "t_Documents"', []), ('FROM "t_DocumentMedia"', [])])
    fetch_workitem_tables(
        {"ms02": [3]},
        runtime_for=lambda c: (runtime, "postgres"),
        storage_for=lambda c, n: store,
    )
    sql, params = runtime.executed[0]
    assert '"t_WorkItems"' in sql and params == [[3]]
    sql, params = next(x for x in store.executed if "t_DocumentMedia" in x[0])
    assert "::uuid[]" in sql and params == [SYSTEM_TABLE_LIST_MEDIA_TYPE, ["abc"]]


def test_fetch_colliding_ids_across_clients_stay_separate():
    rt_default = _runtime([(1216, "d-1", None)])
    rt_ms02 = _runtime([(1216, "m-1", None)])
    stores = {
        "default": _FakeEngine(
            [("FROM t_Documents", []), ("FROM t_DocumentMedia", [("d-1", XML_TABLES.encode())])]
        ),
        "ms02": _FakeEngine([('FROM "t_Documents"', []), ('FROM "t_DocumentMedia"', [])]),
    }
    out = fetch_workitem_tables(
        {"default": [1216], "ms02": [1216]},
        runtime_for=lambda c: (rt_default, "tsql") if c == "default" else (rt_ms02, "postgres"),
        storage_for=lambda c, n: stores[c],
    )
    assert out[("default", 1216)] != []
    assert out[("ms02", 1216)] == []


def test_fetch_raises_on_unknown_client_and_on_db_failure():
    with pytest.raises(RuntimeError):
        fetch_workitem_tables(
            {"nope": [1]}, runtime_for=lambda c: None, storage_for=lambda c, n: None
        )
    broken = MagicMock()
    broken.raw_connection.side_effect = OSError("db down")
    with pytest.raises(OSError):
        fetch_workitem_tables(
            {"default": [1]},
            runtime_for=lambda c: (broken, "tsql"),
            storage_for=lambda c, n: broken,
        )


def test_fetch_skips_empty_id_lists_without_touching_the_db():
    runtime = MagicMock()
    out = fetch_workitem_tables(
        {"default": [], "ms02": [None]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=lambda c, n: runtime,
    )
    assert out == {}
    runtime.raw_connection.assert_not_called()


# ------------------------------------------------------------- edge legs --- #


def test_parse_keeps_a_valued_cell_without_a_column_name():
    """A cell with a value but no ``ColumnName`` element still counts as a
    cell (column ``None``) and must not be listed under ``columns``."""
    xml = (
        "<ModelObjectList><Item><STGTable>"
        "<TableName>T</TableName><internalRows><item><internalCells>"
        "<item><CellValue><Text>x</Text></CellValue></item>"
        "<item><CellValue><Text>y</Text></CellValue><ColumnName>Col</ColumnName></item>"
        "</internalCells></item></internalRows>"
        "</STGTable></Item></ModelObjectList>"
    )
    out = parse_table_list(xml)
    assert out == [
        {
            "title": "T",
            "columns": ["Col"],
            "rows": [[{"column": None, "value": "x"}, {"column": "Col", "value": "y"}]],
        }
    ]


def test_fetch_skips_a_workitem_without_a_root_document():
    """A located workitem whose ``RootDocumentID`` is NULL has nothing to
    read: it is absent from the result and no storage is opened for it."""
    runtime = _runtime([(1, None, "EM_Storage"), (2, "DOC-2", "EM_Storage")])
    store = _FakeEngine([("FROM t_Documents", []), ("FROM t_DocumentMedia", [])])
    out = fetch_workitem_tables(
        {"default": [1, 2]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=lambda c, n: store,
    )
    assert set(out) == {("default", 2)}
    media_calls = [p for sql, p in store.executed if "FROM t_DocumentMedia" in sql]
    assert media_calls[0][1:] == ["doc-2"]


def test_fetch_tolerates_document_cycles_and_null_child_ids():
    """A child that points back at an ancestor (or a NULL id row) must not
    loop the level walk forever nor be visited twice."""
    runtime = _runtime([(9, "ROOT", "S")])

    def documents(params):
        # root -> kid; kid -> root (cycle) plus a NULL id row
        if params == ["root"]:
            return [("kid", "root")]
        if params == ["kid"]:
            return [("root", "kid"), (None, "kid")]
        return []

    store = _FakeEngine([("FROM t_Documents", documents), ("FROM t_DocumentMedia", [])])
    out = fetch_workitem_tables(
        {"default": [9]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=lambda c, n: store,
    )
    assert out == {("default", 9): []}
    doc_calls = [p for sql, p in store.executed if "FROM t_Documents" in sql]
    assert doc_calls == [["root"], ["kid"]]  # the cycle stops the walk


def test_fetch_ignores_null_media_blobs_and_logs_a_summary():
    """A ``Data`` column that is NULL is not a stream; with a logger the
    fetch reports one debug line per storage pass."""
    runtime = _runtime([(1, "d-1", "S"), (2, "d-2", "S")])
    store = _FakeEngine(
        [
            ("FROM t_Documents", []),
            ("FROM t_DocumentMedia", [("d-1", None), ("d-2", XML_TABLES.encode())]),
        ]
    )
    logger = MagicMock()
    out = fetch_workitem_tables(
        {"default": [1, 2]},
        runtime_for=lambda c: (runtime, "tsql"),
        storage_for=lambda c, n: store,
        logger=logger,
    )
    assert out[("default", 1)] == []
    assert [t["title"] for t in out[("default", 2)]] == ["TabVat"]
    logger.debug.assert_called_once()
    assert "default/S: 2 workitems, 1 table streams" in logger.debug.call_args[0][0]


def test_table_streams_with_no_documents_never_opens_a_connection():
    from nx_lib.workitems.tables import _table_streams

    engine = MagicMock()
    assert _table_streams(engine, "tsql", []) == {}
    engine.raw_connection.assert_not_called()

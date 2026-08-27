"""Unit tests for source-visualizer introspection (DB injected as a fake conn).

The fake cursor answers the four statements introspect() runs, in order:
DB_NAME(), objects+columns, row counts, foreign keys.
"""

from nx_lib.reporting import db_schema


def _row(**kw):
    return type("R", (), kw)()


class _FakeCursor:
    def __init__(self, objects, counts, fks, views=(), db="TestDB"):
        self._objects, self._counts, self._fks, self._db = objects, counts, fks, db
        self._views = list(views)
        self._rows = []

    def execute(self, sql, *params):
        if "DB_NAME()" in sql:
            self._rows = [(self._db,)]
        elif "sys.foreign_keys" in sql:
            self._rows = self._fks
        elif "sys.sql_expression_dependencies" in sql:
            self._rows = self._views
        elif "sys.partitions" in sql:
            self._rows = self._counts
        else:
            self._rows = self._objects
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, *a, **kw):
        self._cursor = _FakeCursor(*a, **kw)

    def cursor(self):
        return self._cursor


OBJECTS = [
    _row(
        sch="dbo",
        tbl="Dossier",
        otype="U ",
        col="Id",
        typ="int",
        maxlen=4,
        prec=10,
        scale_=0,
        nullable=0,
        is_pk=1,
    ),
    _row(
        sch="dbo",
        tbl="Dossier",
        otype="U ",
        col="Name",
        typ="nvarchar",
        maxlen=256,
        prec=0,
        scale_=0,
        nullable=1,
        is_pk=0,
    ),
    _row(
        sch="dbo",
        tbl="Page",
        otype="U ",
        col="DossierId",
        typ="int",
        maxlen=4,
        prec=10,
        scale_=0,
        nullable=0,
        is_pk=0,
    ),
    _row(
        sch="dbo",
        tbl="vStats",
        otype="V",
        col="Total",
        typ="decimal",
        maxlen=9,
        prec=18,
        scale_=2,
        nullable=1,
        is_pk=0,
    ),
]
COUNTS = [_row(sch="dbo", tbl="Dossier", rowcnt=10), _row(sch="dbo", tbl="Page", rowcnt=99)]
FKS = [
    _row(
        fkname="FK_Page_Dossier",
        from_sch="dbo",
        from_tbl="Page",
        from_col="DossierId",
        to_sch="dbo",
        to_tbl="Dossier",
        to_col="Id",
    )
]


def test_introspect_shapes_tables_relations_and_fk_columns():
    out = db_schema.introspect(_FakeConn(OBJECTS, COUNTS, FKS))
    assert out["db"] == "TestDB"
    # Sorted by row count desc: Page (99) before Dossier (10) before the view.
    assert [t["name"] for t in out["tables"]] == ["Page", "Dossier", "vStats"]
    page, dossier, view = out["tables"]
    assert view["kind"] == "view" and dossier["kind"] == "table"
    assert dossier["columns"][0] == {"name": "Id", "type": "int", "nullable": False, "pk": True}
    assert dossier["columns"][1]["type"] == "nvarchar(128)"
    assert view["columns"][0]["type"] == "decimal(18,2)"
    # The FK is both an edge and a marker on the child column.
    assert out["relations"] == [
        {
            "name": "FK_Page_Dossier",
            "from": "dbo.Page",
            "to": "dbo.Dossier",
            "fromColumns": ["DossierId"],
            "toColumns": ["Id"],
            "kind": "fk",
        }
    ]
    assert page["columns"][0]["fk"] == {"table": "dbo.Dossier", "column": "Id"}
    assert out["truncated"] == 0


def test_introspect_reports_the_table_cap_and_drops_dangling_edges():
    out = db_schema.introspect(_FakeConn(OBJECTS, COUNTS, FKS), max_tables=1)
    assert out["truncated"] == 2
    assert [t["name"] for t in out["tables"]] == ["Page"]
    # dbo.Dossier fell outside the cap -- its edge would point at nothing.
    assert out["relations"] == []


def test_format_type_covers_max_and_unsized():
    assert db_schema.format_type("nvarchar", -1, 0, 0) == "nvarchar(max)"
    assert db_schema.format_type("varchar", 50, 0, 0) == "varchar(50)"
    assert db_schema.format_type("datetime", 8, 23, 3) == "datetime"


def _payload():
    return db_schema.introspect(_FakeConn(OBJECTS, COUNTS, FKS))


def test_filter_used_keeps_registry_tables_and_their_fk_neighbours():
    """A registry name matches on the bare object name (schemas/quoting vary),
    and the table it joins to comes along so the diagram keeps its edge."""
    out = db_schema.filter_used(_payload(), ["dbo.Page"])
    assert [t["name"] for t in out["tables"]] == ["Page", "Dossier"]
    assert out["filter"] == "used" and out["hidden"] == 1
    assert len(out["relations"]) == 1


def test_filter_used_without_fk_expansion_is_strict():
    out = db_schema.filter_used(_payload(), ['public."Page"'], expand_fk=False)
    assert [t["name"] for t in out["tables"]] == ["Page"]
    assert out["relations"] == []


def test_filter_used_falls_back_to_non_empty_tables():
    """Names from another database match nothing -- rather than an empty
    panel, drop only the tables that hold no rows (views have no count)."""
    out = db_schema.filter_used(_payload(), ["dbo.SomethingElse"])
    assert out["filter"] == "nonempty"
    assert [t["name"] for t in out["tables"]] == ["Page", "Dossier", "vStats"]

    empty = _payload()
    empty["tables"][0]["rows"] = 0
    out = db_schema.filter_used(empty, [])
    assert [t["name"] for t in out["tables"]] == ["Dossier", "vStats"]
    assert out["hidden"] == 1
    assert out["relations"] == []  # the dropped table's edge went with it


VIEW_DEPS = [_row(from_sch="dbo", from_tbl="vStats", to_sch="dbo", to_tbl="Dossier")]


def test_view_dependencies_become_edges_and_pull_their_tables_in():
    """A source pointed at a view is really using the tables the view reads:
    they arrive as dashed 'view' edges and survive the used-table filter."""
    out = db_schema.introspect(_FakeConn(OBJECTS, COUNTS, FKS, VIEW_DEPS))
    view_edges = [r for r in out["relations"] if r["kind"] == "view"]
    assert view_edges == [
        {
            "name": "dbo.vStats → dbo.Dossier",
            "from": "dbo.vStats",
            "to": "dbo.Dossier",
            "fromColumns": [],
            "toColumns": [],
            "kind": "view",
        }
    ]
    filtered = db_schema.filter_used(
        db_schema.introspect(_FakeConn(OBJECTS, COUNTS, FKS, VIEW_DEPS)), ["dbo.vStats"]
    )
    # vStats -> Dossier (what the view reads) -> Page (one FK hop off it).
    assert sorted(t["name"] for t in filtered["tables"]) == ["Dossier", "Page", "vStats"]
    assert filtered["filter"] == "used" and filtered["hidden"] == 0

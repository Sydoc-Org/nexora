"""Unit tests for nx_lib.mapping_config -- cached registry over migration 0074
(dbo.ProcessSources / ProcessFieldMappings / FieldLabels / FieldAliases).

Mocks engine_nexora_db.raw_connection() the same way tests/unit/test_process_helpers.py
does for the legacy config helpers.
"""

import types
from unittest.mock import MagicMock

import pytest

from nx_lib import mapping_config as mc


@pytest.fixture(autouse=True)
def clear_cache(app):
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


def _source_row(
    client="default",
    process="sydoc.Alpha",
    table="dbo.tblAlpha",
    alias=None,
    join_condition=None,
    time_filter=None,
    suggestion_time_filter=None,
    export_column="ExportDate",
    import_column="ImportDate",
    workitem_column=None,
    extra_condition=None,
    id_column_type=None,
):
    return types.SimpleNamespace(
        ClientCode=client,
        ProcessName=process,
        TableName=table,
        TableAlias=alias,
        JoinCondition=join_condition,
        TimeFilter=time_filter,
        SuggestionTimeFilter=suggestion_time_filter,
        ExportColumn=export_column,
        ImportColumn=import_column,
        WorkitemColumn=workitem_column,
        ExtraCondition=extra_condition,
        IdColumnType=id_column_type,
        OrganizationCode=None,  # 0090; the registry reads it, tests here don't group by it
    )


def _mapping_row(
    client="default", process="sydoc.Alpha", field_key="DocType", column="DocType", column_type=None
):
    return types.SimpleNamespace(
        ClientCode=client,
        ProcessName=process,
        FieldKey=field_key,
        ColumnName=column,
        ColumnType=column_type,
    )


def _label_row(field_key="doctype", en="Document Type", de=None, fr=None, it=None, sensitive=False):
    return types.SimpleNamespace(
        FieldKey=field_key,
        EnglishLabel=en,
        GermanLabel=de,
        FrenchLabel=fr,
        ItalianLabel=it,
        IsSensitive=sensitive,
    )


def _alias_row(source="col_doctype", target="doctype"):
    return types.SimpleNamespace(SourceFieldName=source, TargetKey=target)


class _FakeCursor:
    """Routes each execute() by table name to a canned result set, mirroring
    the _FakeCatalogCursor pattern in tests/unit/test_reporting_catalog.py."""

    def __init__(self, sources=(), mappings=(), labels=(), aliases=()):
        self._sources = list(sources)
        self._mappings = list(mappings)
        self._labels = list(labels)
        self._aliases = list(aliases)
        self._result = []

    def execute(self, sql, *params):
        if "FROM ProcessSources" in sql:
            self._result = self._sources
        elif "FROM ProcessFieldMappings" in sql:
            self._result = self._mappings
        elif "FROM FieldLabels" in sql:
            self._result = self._labels
        elif "FROM FieldAliases" in sql:
            self._result = self._aliases
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return self._result


def _engine_with(sources=(), mappings=(), labels=(), aliases=()):
    cur = _FakeCursor(sources=sources, mappings=mappings, labels=labels, aliases=aliases)
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, conn


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


def test_registry_loads_all_four_tables_in_one_connection(app, monkeypatch):
    eng, conn = _engine_with(
        sources=[_source_row()],
        mappings=[_mapping_row()],
        labels=[_label_row()],
        aliases=[_alias_row()],
    )
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        reg = mc.registry()

    assert reg is not None
    assert ("default", "sydoc.Alpha") in reg.sources
    assert len(reg.mappings) == 1
    assert "doctype" in reg.labels
    assert reg.aliases["col_doctype"] == "doctype"
    eng.raw_connection.assert_called_once()
    conn.close.assert_called_once()


def test_registry_load_failure_returns_none_and_is_not_cached(app, monkeypatch):
    eng = _dead_engine()
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        assert mc.registry() is None
        # second call must re-query -- a failure is never cached
        assert mc.registry() is None

    assert eng.raw_connection.call_count == 2


def test_valid_field_keys_empty_on_failure(app, monkeypatch):
    monkeypatch.setattr(mc, "engine_nexora_db", _dead_engine())
    with app.app_context():
        assert mc.valid_field_keys() == set()


def test_field_keys_for_processes_none_on_failure(app, monkeypatch):
    monkeypatch.setattr(mc, "engine_nexora_db", _dead_engine())
    with app.app_context():
        assert mc.field_keys_for_processes(["default.sydoc.Alpha"]) is None


def test_field_keys_for_processes_returns_matching_keys(app, monkeypatch):
    """Positive path: a compound ProcessName (client-prefixed, matching how
    migration 0074 copies the legacy ProcessName verbatim) must actually be
    matched by field_keys_for_processes -- regression test for the bug where
    the comparison re-prefixed m.process with m.client, which never matched
    the already-compound value and silently returned an empty set for every
    real input."""
    eng, _ = _engine_with(
        mappings=[
            _mapping_row(client="default", process="sydoc.05_PDBS", field_key="DocType"),
            _mapping_row(client="default", process="sydoc.Beta", field_key="CrdNo"),
        ],
    )
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        result = mc.field_keys_for_processes(["sydoc.05_PDBS"])

    assert result == {"doctype"}


def test_sensitive_field_keys_none_on_failure(app, monkeypatch):
    monkeypatch.setattr(mc, "engine_nexora_db", _dead_engine())
    with app.app_context():
        assert mc.sensitive_field_keys() is None


def test_mappings_for_filters_client_processes_and_fields(app, monkeypatch):
    eng, _ = _engine_with(
        sources=[_source_row()],
        mappings=[
            _mapping_row(
                client="default", process="sydoc.Alpha", field_key="DocType", column="DocType"
            ),
            _mapping_row(
                client="default", process="sydoc.Alpha", field_key="CrdNo", column="CrdNo"
            ),
            _mapping_row(
                client="default", process="sydoc.Beta", field_key="DocType", column="DType"
            ),
            _mapping_row(client="ms02", process="sydoc.Alpha", field_key="DocType", column="Other"),
        ],
    )
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        result = mc.mappings_for("default", ["sydoc.Alpha"], field_keys={"doctype"})

    assert len(result) == 1
    m = result[0]
    assert m.client == "default"
    assert m.process == "sydoc.Alpha"
    assert m.field_key == "doctype"
    assert m.column == "DocType"


def test_sources_for_default_and_ms02_partition(app, monkeypatch):
    eng, _ = _engine_with(
        sources=[
            _source_row(client="default", process="sydoc.Alpha"),
            _source_row(client="ms02", process="sydoc.05_PDBS"),
        ],
    )
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        default_sources = mc.sources_for("default")
        ms02_sources = mc.sources_for("ms02")

    assert [s.process for s in default_sources] == ["sydoc.Alpha"]
    assert [s.process for s in ms02_sources] == ["sydoc.05_PDBS"]


def test_invalidate_drops_cache(app, monkeypatch):
    eng, _ = _engine_with(sources=[_source_row()])
    monkeypatch.setattr(mc, "engine_nexora_db", eng)

    with app.app_context():
        mc.registry()
        mc.registry()
        assert eng.raw_connection.call_count == 1

        mc.invalidate_mapping_config()
        mc.registry()
        assert eng.raw_connection.call_count == 2


def test_field_aliases_empty_on_failure(app, monkeypatch):
    monkeypatch.setattr(mc, "engine_nexora_db", _dead_engine())
    with app.app_context():
        assert mc.field_aliases() == {}

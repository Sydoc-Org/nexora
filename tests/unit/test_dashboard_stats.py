"""Unit tests for the dashboard stats helpers.

Covers `_split_stat_configs` (partitions `dbo.Statconfig` rows by serving client
so the StatisticsDB T-SQL path only sees 'default' rows and the MS02 Postgres
path gets its own rows) and `_ms02_source` (resolves the MS02 stats table +
date columns from those rows, quoting the PascalCase Postgres identifiers).
"""

import types

from nx_lib.views.dashboard import _ms02_source, _split_stat_configs


def _row(client_code, name="p", table=None, exp=None, imp=None):
    return types.SimpleNamespace(
        ClientCode=client_code,
        ProcessName=name,
        TableName=table,
        ExportColumn=exp,
        ImportColumn=imp,
    )


def test_all_default_rows():
    rows = [_row("default", "a"), _row("default", "b")]
    default_rows, ms02_rows = _split_stat_configs(rows)
    assert default_rows == rows
    assert ms02_rows == []


def test_mixed_default_and_ms02():
    d1 = _row("default", "a")
    d2 = _row("default", "b")
    m1 = _row("ms02", "c")
    default_rows, ms02_rows = _split_stat_configs([d1, m1, d2])
    assert default_rows == [d1, d2]
    assert ms02_rows == [m1]


def test_none_client_code_treated_as_default():
    r = _row(None, "a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_blank_client_code_treated_as_default():
    r = _row("", "a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_ms02_only():
    m1 = _row("ms02", "a")
    m2 = _row("ms02", "b")
    default_rows, ms02_rows = _split_stat_configs([m1, m2])
    assert default_rows == []
    assert ms02_rows == [m1, m2]


def test_missing_clientcode_attribute_treated_as_default():
    # A row object that doesn't even carry a ClientCode attribute (pre-0024
    # shaped data) must still count as 'default'.
    r = types.SimpleNamespace(ProcessName="a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_empty_configs():
    default_rows, ms02_rows = _split_stat_configs([])
    assert default_rows == []
    assert ms02_rows == []


# ----------------------------- _ms02_source ----------------------------- #


def test_ms02_source_none_when_empty():
    assert _ms02_source([]) is None


def test_ms02_source_quotes_pascalcase_columns():
    r = _row(
        "ms02", "sydoc.05_PDBS", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate"
    )
    table, exp, imp = _ms02_source([r])
    # TableName passes through verbatim (already schema-qualified + quoted).
    assert table == 'public."DossierStatistik"'
    # Column names get wrapped as Postgres identifiers.
    assert exp == '"DatumInTempExport"'
    assert imp == '"ImportDate"'


def test_ms02_source_dedupes_to_first_row():
    # All MS02 rows point at the same table; we run one query off the first.
    r1 = _row("ms02", "a", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate")
    r2 = _row("ms02", "b", 'public."Other"', "X", "Y")
    table, exp, imp = _ms02_source([r1, r2])
    assert (table, exp, imp) == ('public."DossierStatistik"', '"DatumInTempExport"', '"ImportDate"')


def test_ms02_source_escapes_embedded_quote():
    r = _row("ms02", "a", "public.t", 'we"ird', "ImportDate")
    _table, exp, _imp = _ms02_source([r])
    assert exp == '"we""ird"'

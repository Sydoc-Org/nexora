"""Unit tests for the dashboard stats helpers.

Covers `_split_stat_configs`, which partitions `dbo.Statconfig` rows by serving
client so the StatisticsDB (T-SQL) path only ever sees 'default' rows and the
MS02 (Postgres) path is gated behind a single flag.
"""

import types

from nx_lib.views.dashboard import _split_stat_configs


def _row(client_code, name="p"):
    return types.SimpleNamespace(ClientCode=client_code, ProcessName=name)


def test_all_default_rows():
    rows = [_row("default", "a"), _row("default", "b")]
    default_rows, has_ms02 = _split_stat_configs(rows)
    assert default_rows == rows
    assert has_ms02 is False


def test_mixed_default_and_ms02():
    d1 = _row("default", "a")
    d2 = _row("default", "b")
    m1 = _row("ms02", "c")
    default_rows, has_ms02 = _split_stat_configs([d1, m1, d2])
    assert default_rows == [d1, d2]
    assert has_ms02 is True


def test_none_client_code_treated_as_default():
    r = _row(None, "a")
    default_rows, has_ms02 = _split_stat_configs([r])
    assert default_rows == [r]
    assert has_ms02 is False


def test_blank_client_code_treated_as_default():
    r = _row("", "a")
    default_rows, has_ms02 = _split_stat_configs([r])
    assert default_rows == [r]
    assert has_ms02 is False


def test_ms02_only():
    m1 = _row("ms02", "a")
    m2 = _row("ms02", "b")
    default_rows, has_ms02 = _split_stat_configs([m1, m2])
    assert default_rows == []
    assert has_ms02 is True


def test_missing_clientcode_attribute_treated_as_default():
    # A row object that doesn't even carry a ClientCode attribute (pre-0024
    # shaped data) must still count as 'default'.
    r = types.SimpleNamespace(ProcessName="a")
    default_rows, has_ms02 = _split_stat_configs([r])
    assert default_rows == [r]
    assert has_ms02 is False


def test_empty_configs():
    default_rows, has_ms02 = _split_stat_configs([])
    assert default_rows == []
    assert has_ms02 is False

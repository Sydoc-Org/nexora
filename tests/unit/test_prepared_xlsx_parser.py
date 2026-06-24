"""Pure parser for the MS02 'prepared documents' Excel (PID + Prepared)."""

import io

import openpyxl

import nx_lib.workitem_sources as ws


def _xlsx(rows, headers=("PID", "Prepared")):
    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(list(headers))
    for r in rows:
        sh.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parses_pid_and_prepared():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("100", True), ("200", False)]))
    assert err is None
    assert [(r["pid"], r["prepared"]) for r in rows] == [("100", True), ("200", False)]


def test_header_detection_is_case_insensitive_and_order_agnostic():
    data = _xlsx([(True, "  300 ")], headers=("prepared", "pid"))
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert rows[0]["pid"] == "300"
    assert rows[0]["prepared"] is True


def test_integer_pid_does_not_get_trailing_dot_zero():
    rows, err = ws.parse_prepared_xlsx(_xlsx([(12345, "yes")]))
    assert err is None
    assert rows[0]["pid"] == "12345"
    assert rows[0]["prepared"] is True


def test_blank_rows_and_blank_pids_skipped():
    rows, err = ws.parse_prepared_xlsx(_xlsx([(None, True), ("", False), ("400", "")]))
    assert err is None
    assert len(rows) == 1
    assert rows[0]["pid"] == "400"
    assert rows[0]["prepared"] is False


def test_duplicate_pid_first_wins():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("500", True), ("500", False)]))
    assert rows[0]["pid"] == "500"
    assert rows[0]["prepared"] is True
    assert len(rows) == 1


def test_row_cap_is_enforced():
    data_rows = [(str(i), True) for i in range(ws._PREPARED_MAX_ROWS + 50)]
    rows, err = ws.parse_prepared_xlsx(_xlsx(data_rows))
    assert err is None
    assert len(rows) == ws._PREPARED_MAX_ROWS


def test_missing_pid_column_returns_error():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("x",)], headers=("Foo", "Prepared")))
    assert rows == []
    assert err is not None


def test_garbage_bytes_returns_error_not_raise():
    rows, err = ws.parse_prepared_xlsx(b"not a workbook")
    assert rows == []
    assert err is not None


def _xlsx5(rows, headers=("PID", "Collected", "CollectedBy", "PreparedBy", "PreparedBy")):
    """Build a 5-column xlsx with the user's real (typo'd) header row."""
    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(list(headers))
    for r in rows:
        sh.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_five_column_full_row():
    rows, err = ws.parse_prepared_xlsx(_xlsx5([(30111679, 1, "Guy1", 1, "Girl2")]))
    assert err is None
    assert len(rows) == 1
    r = rows[0]
    assert r["pid"] == "30111679"
    assert r["collected"] is True
    assert r["collected_by"] == "Guy1"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Girl2"


def test_duplicate_preparedby_header_first_is_flag_second_is_name():
    """4th col 'PreparedBy' (user typo for flag), 5th col 'PreparedBy' (name)."""
    data = _xlsx5([(99, 0, "Alice", 1, "Bob")])
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    r = rows[0]
    assert r["collected"] is False
    assert r["collected_by"] == "Alice"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Bob"


def test_five_col_case_insensitive_headers():
    data = _xlsx5(
        [("PID1", 0, "Alice", 1, "Bob")],
        headers=("pid", "COLLECTED", "collectedby", "PREPARED", "preparedby"),
    )
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    r = rows[0]
    assert r["collected"] is False
    assert r["collected_by"] == "Alice"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Bob"


def test_five_col_backward_compat_two_column():
    """Two-column file (PID + Prepared only) still parses; extra fields default."""
    rows, err = ws.parse_prepared_xlsx(_xlsx([("777", True), ("888", False)]))
    assert err is None
    assert rows[0]["collected"] is False
    assert rows[0]["collected_by"] == ""
    assert rows[0]["prepared_by"] == ""


def test_five_col_name_columns_stripped():
    data = _xlsx5(
        [(10, 1, "  SpaceGuy  ", 0, "  ")],
    )
    rows, err = ws.parse_prepared_xlsx(data)
    r = rows[0]
    assert r["collected_by"] == "SpaceGuy"
    assert r["prepared_by"] == ""


def test_five_col_row_cap_enforced():
    data_rows = [(str(i), 1, "a", 0, "b") for i in range(ws._PREPARED_MAX_ROWS + 50)]
    data = _xlsx5(data_rows, headers=("PID", "Collected", "CollectedBy", "Prepared", "PreparedBy"))
    result, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert len(result) == ws._PREPARED_MAX_ROWS

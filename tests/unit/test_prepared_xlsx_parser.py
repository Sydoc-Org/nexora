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
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("100", True), ("200", False)]))
    assert err is None
    assert pairs == [("100", True), ("200", False)]


def test_header_detection_is_case_insensitive_and_order_agnostic():
    data = _xlsx([(True, "  300 ")], headers=("prepared", "pid"))
    pairs, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert pairs == [("300", True)]  # trimmed; column order swapped


def test_integer_pid_does_not_get_trailing_dot_zero():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([(12345, "yes")]))
    assert err is None
    assert pairs == [("12345", True)]


def test_blank_rows_and_blank_pids_skipped():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([(None, True), ("", False), ("400", "")]))
    assert err is None
    assert pairs == [("400", False)]


def test_duplicate_pid_first_wins():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("500", True), ("500", False)]))
    assert pairs == [("500", True)]


def test_row_cap_is_enforced():
    rows = [(str(i), True) for i in range(ws._PREPARED_MAX_ROWS + 50)]
    pairs, err = ws.parse_prepared_xlsx(_xlsx(rows))
    assert err is None
    assert len(pairs) == ws._PREPARED_MAX_ROWS


def test_missing_pid_column_returns_error():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("x",)], headers=("Foo", "Prepared")))
    assert pairs == []
    assert err is not None


def test_garbage_bytes_returns_error_not_raise():
    pairs, err = ws.parse_prepared_xlsx(b"not a workbook")
    assert pairs == []
    assert err is not None

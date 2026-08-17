"""Unit tests for _json_safe — coercing DB cells to JSON-serializable values.

Flask's default JSON encoder handles None/bool/int/float/str and
date/datetime/Decimal/UUID, but NOT bytes/bytearray/memoryview or
datetime.time — those crash jsonify with a 500. _json_safe maps the crashy
types to readable strings and passes the Flask-native ones through unchanged —
except dates, which it formats itself so result tables don't show Flask's
HTTP-date form ("Thu, 26 Mar 2026 08:56:28 GMT"), see issue #175.
"""

import datetime
import decimal
import uuid

from nx_lib.views.reporting import _json_safe


def test_passes_native_scalars_through():
    for v in (None, True, False, 0, 5, -3, 3.14, "x", ""):
        assert _json_safe(v) == v


def test_bytes_like_become_hex_strings():
    assert _json_safe(b"\x00\x01\x02") == "0x000102"
    assert _json_safe(bytearray(b"\xff")) == "0xff"
    assert _json_safe(memoryview(b"\x0a")) == "0x0a"


def test_time_becomes_iso_string():
    assert _json_safe(datetime.time(9, 5)) == "09:05:00"


def test_flask_native_types_pass_through_unchanged():
    dec = decimal.Decimal("1.50")
    assert _json_safe(dec) is dec
    u = uuid.uuid4()
    assert _json_safe(u) is u


def test_datetime_is_sortable_string_not_http_date():
    assert _json_safe(datetime.datetime(2026, 3, 26, 8, 56, 28)) == "2026-03-26 08:56:28"
    assert _json_safe(datetime.date(2026, 3, 26)) == "2026-03-26"
    # The bug this replaced: Flask's DefaultJSONProvider emitted RFC-822/HTTP
    # dates for both, which is what surfaced in result tables (issue #175).
    for v in (datetime.datetime(2026, 3, 26, 8, 56, 28), datetime.date(2026, 3, 26)):
        assert "GMT" not in _json_safe(v)


def test_unknown_type_falls_back_to_str():
    class Weird:
        def __str__(self):
            return "weird"

    assert _json_safe(Weird()) == "weird"

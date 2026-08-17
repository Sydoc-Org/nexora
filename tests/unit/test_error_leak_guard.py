"""JSON error handlers must not return raw exception text to clients
(security audit #193, finding 12).

Many per-route `except` blocks used to `jsonify({"error": str(e)}), 500`,
leaking pyodbc/SQL Server driver messages, SQL fragments and internal
identifiers -- reconnaissance that aids schema/injection probing. They now
return a generic, translated message and log the detail server-side. This
guard fails if the leaky shape is reintroduced.
"""

from pathlib import Path

import pytest

_VIEW_FILES = ["generali", "dashboard", "admin"]


@pytest.mark.parametrize("view", _VIEW_FILES)
def test_no_raw_exception_in_json_error_response(view):
    src = Path(f"nx_lib/views/{view}.py").read_text(encoding="utf-8")
    assert '"error": str(e)' not in src, (
        f"nx_lib/views/{view}.py returns raw str(e) to the client -- return a "
        f"generic message and log the detail server-side instead (#193)."
    )

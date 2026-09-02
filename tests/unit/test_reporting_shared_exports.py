"""Contract test for beautify-phase-2a Task 2 (extract the shared reporting
core into ``nx_lib/views/reporting/_shared.py``).

``nx_lib/reporting/runner.py`` does ``from ..views import reporting as rv``
and reads a fixed set of attributes off the *package* (``rv.<name>``) at
call time — never off ``_shared`` directly. Every one of those attributes
must keep resolving on ``nx_lib.views.reporting`` after the core's move into
``_shared.py``, via ``__init__.py``'s re-export. This is an explicit list
(not a loop over ``dir()``) so it fails loudly, by name, the moment one of
these stops being re-exported.
"""

from nx_lib.views import reporting as rv

# Exactly the attribute names nx_lib/reporting/runner.py reads off `rv`.
_RUNNER_CONSUMED_ATTRS = [
    "_CURATED_ENGINES",
    "_SQL_TARGETS",
    "_SQL_TARGET_PERMISSION",
    "_effective_scope",
    "_execute",
    "_get_effective_source",
    "_load_field_col_maps",
    "_load_process_configs",
    "_metrics_for_source",
    "_run_sql",
    "engine_statistics_db",
    "metric_result_columns",
]


def test_runner_consumed_attrs_resolve_on_package():
    assert len(_RUNNER_CONSUMED_ATTRS) == 12
    for name in _RUNNER_CONSUMED_ATTRS:
        assert hasattr(rv, name), f"nx_lib.views.reporting.{name} no longer resolves"
        assert getattr(rv, name) is not None


def test_runner_consumed_attrs_are_defined_in_shared_module():
    """The 12 names must actually live in _shared.py (not just be re-exported
    aliases of something else) — this is the module Task 2 introduces."""
    from nx_lib.views.reporting import _shared

    # engine_statistics_db is a DB engine imported into _shared.py too (it is
    # not *defined* there, but is bound in its namespace the same way).
    for name in _RUNNER_CONSUMED_ATTRS:
        assert hasattr(_shared, name), f"nx_lib.views.reporting._shared.{name} is missing"

"""Workitems: pure-Python building blocks factored out of
``nx_lib/views/workitems.py`` (field config, the doc-field DSL, sensitivity
gating, the list-query engine, media lookup) so they unit-test without a
database and without a Flask request/session context. The route layer in
``nx_lib/views/workitems.py`` stays Flask-aware and wires these to real
engines/session/permissions.
"""

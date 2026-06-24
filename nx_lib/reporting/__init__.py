"""Self-service reporting engine (curated table sources).

Pure-Python building blocks (schema, catalog mapping, source registry, query
builder, exporter) live here so they unit-test without a database. The Flask
view layer in nx_lib/views/reporting.py wires them to real engines.
"""

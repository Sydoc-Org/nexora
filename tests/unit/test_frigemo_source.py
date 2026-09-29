"""The Frigemo source points at the table PROD really has (#402).

Migration `0127` registered `frigemo` over `dbo.Frigemo` with invented column
names; that table only ever existed on INT, and every run on PROD failed with
"Invalid object name". `0137` repoints it at `dbo.Frigemo_Statistic`. These
guards pin the catalog to the columns that table carries on PROD (introspected
2026-09-29) so a future "tidy-up" of the vendor names cannot break it again.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "sql" / "_migrations" / "NexoraDB" / "0137_fix_frigemo_source_table.sql"

# dbo.Frigemo_Statistic on PRDSQL01\SYDOC_Statistik, column for column.
PROD_COLUMNS = {
    "DCD",
    "T_IMP_NOREP_MAILS",
    "T_IMP_NOREP_PAGES",
    "T_IMP_NOREP_DOCS",
    "OVERALL_IMP_PAGES",
    "OVERALL_EXP_PAGES",
    "OVERALL_IMP_DOCS",
    "OVERALL_EXP_DOCS",
    "OVERALL_DEL_DUNNING",
    "OVERALL_IMP_INVCRE",
    "ExportID",
}


def _sql():
    return MIGRATION.read_text(encoding="utf-8")


def _columns():
    m = re.search(r"N'(\[\{\"field\".*?\])'", _sql(), re.S)
    assert m, "no ColumnsJSON in 0137"
    return {c["field"]: c for c in json.loads(m.group(1))}


def _metric_base_fields():
    return dict(re.findall(r"\('(frigemo_[a-z_]+)',\s*'([A-Za-z_]+)'\)", _sql()))


def test_source_targets_the_prod_table():
    assert "BaseObject = 'dbo.Frigemo_Statistic'" in _sql()
    assert "dbo.Frigemo'" not in _sql().split("UPDATE", 1)[1], "still points at the INT-only table"


def test_every_catalog_field_is_a_real_prod_column():
    unknown = set(_columns()) - PROD_COLUMNS
    assert not unknown, f"0137 exposes columns PROD does not have: {sorted(unknown)}"


def test_every_metric_base_field_is_in_the_catalog():
    cols = _columns()
    bases = _metric_base_fields()
    assert len(bases) == 6, f"expected the six 0127 sum metrics, got {sorted(bases)}"
    missing = {code: f for code, f in bases.items() if f not in cols}
    assert not missing, f"metrics aggregate fields the catalog does not expose: {missing}"


def test_date_column_is_grainable_date():
    """DCD is varchar on PROD; typing it 'date' is what makes the grains CAST it
    and the pickers bind date parameters."""
    dcd = _columns()["DCD"]
    assert dcd["type"] == "date"
    assert dcd.get("grainable") is True


def test_collector_run_id_stays_internal():
    assert "ExportID" not in _columns()

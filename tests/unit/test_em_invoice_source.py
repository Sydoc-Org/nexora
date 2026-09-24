r"""The Elektro-Material billing source keeps the shape it was verified in (#329).

Migration `0130` registers `dbo.EM_Invoice` as a reporting source so the monthly
Verrechnung stops being a hand-refreshed workbook. The measures were not
invented: they were read out of that workbook's own pivot definition (rows =
`Eingang`, data fields = `Anzahl von DocBarcode` / `Summe von AnzImagesOut` /
`Summe von OrdItmPosCount`) and then checked against six published months.

Two decisions in that migration are load-bearing and silent if broken, which is
why they are pinned here rather than left to review:

* **Every measure filters on `Eingang`.** The workbook's total is the sum of its
  two rows, OPEX + E_MAIL. Across the whole table `Eingang` also takes `Nexora`
  and NULL, so an unfiltered `SUM` would bill rows the workbook never counted --
  and it would do it quietly, in a month nobody re-checks.
* **The amount and bank columns stay out of the catalogue.** `EM_Invoice` carries
  GrossAmount/NetAmount/VatAmount, IBANs, creditor numbers and names. Billing
  scan volume needs none of it, and a column absent from `ColumnsJSON` cannot be
  selected, filtered or sorted by anyone holding the source permission.

These read the migration text. The figures themselves cannot be asserted without
the statistics database, and that verification lives in the issue.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "sql" / "_migrations" / "NexoraDB" / "0130_seed_em_invoice_source.sql"

# The two intake channels the workbook's pivot shows as its rows. Anything the
# source bills has to be one of these.
BILLED_CHANNELS = {"OPEX Scan Scanner", "E_MAIL"}

# Present in EM_Invoice, deliberately not exposed. Not an exhaustive list of
# sensitive columns -- an exhaustive list would rot; these are the ones whose
# appearance would mean somebody widened the catalogue without thinking.
MUST_NOT_BE_EXPOSED = (
    "GrossAmount",
    "NetAmount",
    "VatAmount",
    "BankIBAN",
    "SPC_IBAN",
    "BankPK",
    "CrdNO",
    "CRDNAME1",
    "InvoiceNR",
)

EXPECTED_MEASURES = {
    "em_documents": "count",
    "em_opex_scans": "count",
    "em_email_documents": "count",
    "em_order_positions": "sum",
    "em_images_out": "sum",
}


def _sql():
    return MIGRATION.read_text(encoding="utf-8")


def _columns_json():
    """The source's ColumnsJSON, parsed."""
    m = re.search(r"N'(\[\{\"field\".*?\])'", _sql(), re.S)
    assert m, "could not find ColumnsJSON in the migration"
    return json.loads(m.group(1))


def _filter_jsons():
    """Every FilterJson literal in the measure insert, parsed, by measure code."""
    out = {}
    for code in EXPECTED_MEASURES:
        m = re.search(
            rf"\('{re.escape(code)}',\s*'em_invoice',.*?N'(\[\{{.*?\}}\])'",
            _sql(),
            re.S,
        )
        assert m, f"no FilterJson found for {code}"
        out[code] = json.loads(m.group(1))
    return out


def test_the_migration_exists_and_registers_the_source():
    """If this file is renamed the rest of the guards pass vacuously."""
    assert MIGRATION.exists(), f"{MIGRATION.name} is gone -- retarget this guard"
    sql = _sql()
    assert "dbo.ReportingSources" in sql
    assert "'em_invoice'" in sql
    assert "'dbo.EM_Invoice'" in sql


def test_the_source_is_gated_by_its_own_permission():
    """A table source gets no row scoping -- the permission is the whole gate."""
    sql = _sql()
    assert "reporting.source.em_invoice.use" in sql
    assert "dbo.Permission" in sql, "the permission row is not created"


def test_every_measure_is_registered_with_the_expected_aggregation():
    sql = _sql()
    for code, agg in EXPECTED_MEASURES.items():
        assert f"'{code}'" in sql, f"measure {code} is missing"
        m = re.search(rf"\('{re.escape(code)}',\s*'em_invoice',.*?'({agg})'", sql, re.S)
        assert m, f"measure {code} does not aggregate with {agg}"


def test_every_measure_is_restricted_to_the_billed_channels():
    """The one that would silently over-bill. An unfiltered sum would pick up
    the `Nexora` and NULL `Eingang` rows the workbook never counted."""
    for code, cond in _filter_jsons().items():
        fields = {c["field"] for c in cond}
        assert fields == {"Eingang"}, f"{code} filters on {fields}, expected Eingang"
        values = set()
        for c in cond:
            v = c["value"]
            values.update(v if isinstance(v, list) else [v])
        assert (
            values <= BILLED_CHANNELS
        ), f"{code} bills {values - BILLED_CHANNELS}, which the workbook never counted"


def test_the_split_measures_cover_the_total_between_them():
    """Opex + e-mail must be exactly what the combined measures bill, or the
    two halves stop reconciling with the total the customer is invoiced."""
    f = _filter_jsons()
    halves = set()
    for code in ("em_opex_scans", "em_email_documents"):
        for c in f[code]:
            halves.add(c["value"])
    assert halves == BILLED_CHANNELS
    for code in ("em_documents", "em_order_positions", "em_images_out"):
        values = set()
        for c in f[code]:
            values.update(c["value"])
        assert values == BILLED_CHANNELS, f"{code} does not cover both channels"


def test_the_date_column_is_the_real_datetime_not_the_text_one():
    """ExportEM is nvarchar holding 'dd.mm.yyyy HH:MM:SS' -- unsortable and
    ungrainable, and the reason the old report needs a human to tick timestamps
    out of a filter list every month."""
    fields = {c["field"]: c for c in _columns_json()}
    assert "ExportEM_dt" in fields, "the source does not expose ExportEM_dt"
    assert fields["ExportEM_dt"]["type"] == "date"
    assert fields["ExportEM_dt"].get("grainable") is True, "cannot group by month"
    assert "ExportEM" not in fields, "the text export column must stay out"


def test_amount_and_bank_columns_are_not_exposed():
    """Billing scan volume needs none of it, and what is not in the catalogue
    cannot be queried by a permission holder."""
    exposed = {c["field"] for c in _columns_json()}
    leaked = exposed & set(MUST_NOT_BE_EXPOSED)
    assert not leaked, f"catalogue exposes {sorted(leaked)} -- not needed to bill volume"


def test_measures_carry_all_four_languages():
    """A missing translation shows the English label to a German user, which is
    how a billing figure gets misread."""
    sql = _sql()
    for code in EXPECTED_MEASURES:
        m = re.search(rf"\('{re.escape(code)}',\s*'em_invoice',\s*(.*?)'(count|sum)'", sql, re.S)
        assert m, f"cannot read the label block for {code}"
        labels = re.findall(r"N'((?:[^']|'')*)'", m.group(1))
        assert len(labels) == 4, f"{code} has {len(labels)} labels, expected 4"
        assert all(label.strip() for label in labels), f"{code} has a blank label"

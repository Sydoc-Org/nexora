r"""Compass Group and Privera billing sources keep their verified shape (#329).

Migrations `0131` and `0132` follow `0130` (Elektro-Material, guarded in
`test_em_invoice_source.py`). All three replace a hand-refreshed workbook on the
R: drive with a source over the table that workbook's Power Query already reads.

Each customer's pivot turned out to be a *different* shape, and the differences
are the whole risk here -- they look like inconsistencies somebody would later
"tidy up", and tidying any of them changes an invoice:

* Elektro-Material filters every measure on `Eingang`, because its pivot totals
  two channel rows.
* **Compass filters nothing.** Its pivot has no channel split and the unfiltered
  count reproduces the published total exactly. Adding a filter for symmetry
  with 0130 would change the number.
* **Compass bills on `UploadDatetime`, not `DocDate`**, even though DocDate is
  what the pivot shows as its rows. Documents uploaded in one month carry
  document dates spread over years.
* **Privera splits on `DocSource`, not on the workbook's `FileName` filter.**

Verified before these were written: Compass exact in 6 of 8 published months
(off by one in the other two), Privera exact in 5 of 6 published figures. The
one gap is documented in `test_privera_mail_measure_is_the_honest_definition`.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "sql" / "_migrations" / "NexoraDB"

COMPASS = MIGRATIONS / "0131_seed_compass_invoice_source.sql"
PRIVERA = MIGRATIONS / "0132_seed_privera_invoice_source.sql"
EM = MIGRATIONS / "0130_seed_em_invoice_source.sql"

ALL_BILLING = {"em_invoice": EM, "compass_invoice": COMPASS, "privera_invoice": PRIVERA}

# Columns that exist in these tables and must never reach a catalogue. Billing
# document volume needs none of them. The Privera ones are the sharpest:
# LiegenschaftsNr and EigentuemerNr identify a property and its owner.
NEVER_EXPOSED = (
    "GrossAmount",
    "NetAmount",
    "VatAmount",
    "BankIBAN",
    "SPC_IBAN",
    "IBAN",
    "ESR",
    "BankPK",
    "CrdNO",
    "CRD_NR",
    "CRDNAME1",
    "CRD_NAME_1",
    "InvoiceNR",
    "LiegenschaftsNr",
    "EigentuemerNr",
)


def _sql(path):
    return path.read_text(encoding="utf-8")


def _columns(path):
    m = re.search(r"N'(\[\{\"field\".*?\])'", _sql(path), re.S)
    assert m, f"no ColumnsJSON in {path.name}"
    return {c["field"]: c for c in json.loads(m.group(1))}


def _measure_block(path, code):
    """The VALUES row for one measure, as raw text."""
    m = re.search(
        rf"\('{re.escape(code)}',\s*'[a-z_]+',(.*?)\n\s*\)?\)?,?\s*(?=\('|\) AS v)",
        _sql(path),
        re.S,
    )
    assert m, f"measure {code} not found in {path.name}"
    return m.group(1)


def _filter_of(path, code):
    """Parsed FilterJson for a measure, or None when it has none."""
    block = _measure_block(path, code)
    m = re.search(r"N'(\[\{.*?\}\])'", block, re.S)
    return json.loads(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Shared across every billing source.
# --------------------------------------------------------------------------


def test_all_three_billing_migrations_exist():
    for code, path in ALL_BILLING.items():
        assert path.exists(), f"{path.name} is gone -- retarget these guards"
        assert f"'{code}'" in _sql(path)


def test_every_billing_source_creates_its_own_permission():
    """A table source gets no row scoping, so the permission is the whole gate
    between one internal customer's figures and another's."""
    for code, path in ALL_BILLING.items():
        sql = _sql(path)
        assert f"reporting.source.{code}.use" in sql
        assert "dbo.Permission" in sql, f"{path.name} never creates the permission row"


def test_no_billing_source_exposes_amounts_bank_details_or_property_ids():
    for code, path in ALL_BILLING.items():
        leaked = set(_columns(path)) & set(NEVER_EXPOSED)
        assert not leaked, f"{code} exposes {sorted(leaked)} -- not needed to bill volume"


# --------------------------------------------------------------------------
# Compass Group.
# --------------------------------------------------------------------------


def test_compass_bills_on_the_upload_date():
    """DocDate is what the pivot *shows*; UploadDatetime is what it *filters*.
    Counting by DocDate bills a different set of documents entirely -- the May
    2026 workbook has rows dated 2022, 2024 and 2025, and 235 with no usable
    date at all."""
    cols = _columns(COMPASS)
    assert "UploadDatetime" in cols, "the billing period column is not exposed"
    assert cols["UploadDatetime"]["type"] == "date"
    assert cols["UploadDatetime"].get("grainable") is True, "cannot group by month"


def test_compass_measure_has_no_channel_filter():
    """Deliberately unlike 0130. Compass's pivot has no channel split and its
    unfiltered count reproduces the published total exactly, so 'harmonising'
    it with Elektro-Material would change an invoice."""
    assert (
        _filter_of(COMPASS, "compass_documents") is None
    ), "compass_documents gained a filter -- its published total is unfiltered"


def test_compass_keeps_channel_as_a_dimension_not_a_filter():
    assert "Eingang" in _columns(COMPASS), "Eingang should stay available to group by"


# --------------------------------------------------------------------------
# Privera Rechnungseingang.
# --------------------------------------------------------------------------


def test_privera_registers_the_three_published_figures():
    """gesamt / Mail / eBill -- the workbook publishes three pivots, so three
    measures."""
    sql = _sql(PRIVERA)
    for code in ("privera_documents", "privera_mail_documents", "privera_ebill_documents"):
        assert f"'{code}'" in sql, f"{code} is missing"


def test_privera_total_counts_every_source():
    assert (
        _filter_of(PRIVERA, "privera_documents") is None
    ), "the total must not be filtered -- it counts every document exported"


def test_privera_splits_on_docsource_not_filename():
    """The workbook splits Mail from eBill with a list of ticked file names,
    which is neither reproducible nor meaningful. DocSource carries the same
    classification as data and partitions the month exactly."""
    for code, expected in (
        ("privera_mail_documents", "MAIL"),
        ("privera_ebill_documents", "eBill"),
    ):
        cond = _filter_of(PRIVERA, code)
        assert cond, f"{code} has no filter"
        assert {c["field"] for c in cond} == {
            "DocSource"
        }, f"{code} should key on DocSource, not on file names"
        assert [c["value"] for c in cond] == [expected]


def test_privera_mail_measure_is_the_honest_definition():
    """The known, deliberate difference. The old Mail pivot dropped mail
    documents with no Mandant while its total counted them, so its August 2026
    figure was 5 lower. That is an inconsistency in the report, not a billing
    rule, so it is not welded into the metric -- Mandant stays a dimension so
    anyone who wants the old behaviour can filter for it."""
    cond = _filter_of(PRIVERA, "privera_mail_documents")
    assert {c["field"] for c in cond} == {"DocSource"}, (
        "a Mandant condition crept into the mail measure -- that was an artefact "
        "of the old workbook, not a rule anyone agreed"
    )
    assert "Mandant" in _columns(
        PRIVERA
    ), "Mandant must stay a dimension, or the old behaviour is unreachable"


def test_privera_bills_on_the_export_date():
    cols = _columns(PRIVERA)
    assert "ExportDate" in cols
    assert cols["ExportDate"].get("grainable") is True


def test_privera_measures_carry_all_four_languages():
    for code in ("privera_documents", "privera_mail_documents", "privera_ebill_documents"):
        block = _measure_block(PRIVERA, code)
        labels = re.findall(r"N'((?:[^']|'')*)'", block.split("'count'")[0])
        assert len(labels) == 4, f"{code} has {len(labels)} labels, expected 4"
        assert all(x.strip() for x in labels), f"{code} has a blank label"

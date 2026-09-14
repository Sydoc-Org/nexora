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
NACHSEND = MIGRATIONS / "0133_seed_privera_nachsendungen_source.sql"
NEUZUG = MIGRATIONS / "0134_seed_privera_neuzugaenge_source.sql"
POSTEIN = MIGRATIONS / "0135_seed_privera_posteingang_source.sql"
EM = MIGRATIONS / "0130_seed_em_invoice_source.sql"

ALL_BILLING = {
    "em_invoice": EM,
    "compass_invoice": COMPASS,
    "privera_invoice": PRIVERA,
    "privera_nachsendungen": NACHSEND,
    "privera_neuzugaenge": NEUZUG,
    "privera_posteingang": POSTEIN,
}

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
    "MietverhaeltnisNr",
    "Empfaenger",
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


def test_all_billing_migrations_exist():
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


# --------------------------------------------------------------------------
# Privera physische Zustellung -- the first source in another database.
# --------------------------------------------------------------------------


def test_nachsendungen_points_at_the_other_database():
    """Every earlier source is 'dbo.<table>' in SYDOC_Statistik. This one is
    three-part, and it is the reason the identifier guard had to stop refusing
    names that start with a digit."""
    from nx_lib.reporting.table_query import _quote_object

    m = re.search(r"'(01_Privera_Posteingang\.dbo\.[A-Za-z0-9_]+)'", _sql(NACHSEND))
    assert m, "the three-part BaseObject is gone from the migration"
    # Not just present in the text: the query layer has to accept it.
    assert _quote_object(m.group(1)).startswith("[01_Privera_Posteingang].")


def test_nachsendungen_registers_both_published_figures():
    sql = _sql(NACHSEND)
    for code in ("privera_nachsendungen_total", "privera_nachsendungen_ohne_tec"):
        assert f"'{code}'" in sql, f"{code} is missing"
    assert (
        _filter_of(NACHSEND, "privera_nachsendungen_total") is None
    ), "the total must count every forwarding"


def test_ohne_tec_excludes_the_forwarding_type_not_the_branch():
    """The trap. August 2026 published 1,667 total and 1,042 'ohne TEC'. The
    difference, 625, is the 'Rechnungen Privera TEC' *Nachsendungstyp* row --
    excluding the TEC *Niederlassung* instead gives 1,057, which looks just as
    plausible and is wrong. Both verified against July and August."""
    cond = _filter_of(NACHSEND, "privera_nachsendungen_ohne_tec")
    assert cond, "the ohne-TEC measure lost its filter"
    assert {c["field"] for c in cond} == {"Nachsendungstyp"}, (
        "ohne TEC must exclude a forwarding type, not a branch -- excluding the "
        "TEC Niederlassung gives a different number"
    )
    assert cond[0]["op"] == "ne"
    assert cond[0]["value"] == "Rechnungen Privera TEC"


# --------------------------------------------------------------------------
# Privera Neuzugänge -- a view that is already aggregated per month.
# --------------------------------------------------------------------------


def test_neuzugaenge_registers_the_three_published_rows():
    """The workbook's pivot has three data rows: Dossiers, Register, Seiten."""
    sql = _sql(NEUZUG)
    for code in (
        "privera_neuzugaenge_dossiers",
        "privera_neuzugaenge_register",
        "privera_neuzugaenge_seiten",
    ):
        assert f"'{code}'" in sql, f"{code} is missing"
        assert _filter_of(NEUZUG, code) is None, f"{code} should not be filtered"


def test_neuzugaenge_does_not_reproduce_the_summed_year():
    """The workbook's pivot carries a fourth data field, "Summe von
    JahrExport" -- somebody dropping the year into the values by accident. It
    totals 32,416 for 2026 and means nothing. Copying a source faithfully means
    copying what it *meant*, not every field that ended up in it."""
    sql = _sql(NEUZUG)
    assert "'sum', 'JahrExport'" not in sql, "the year is being summed as a measure"
    for code in (
        "privera_neuzugaenge_dossiers",
        "privera_neuzugaenge_register",
        "privera_neuzugaenge_seiten",
    ):
        block = _measure_block(NEUZUG, code)
        assert "JahrExport" not in block, f"{code} aggregates the year"


def test_neuzugaenge_treats_year_and_month_as_dimensions_not_a_date():
    """The view has no date column -- only a year and a month number -- because
    it is already aggregated per month. Declaring either as a grainable date
    would ask SQL Server to read an integer as one."""
    cols = _columns(NEUZUG)
    for f in ("JahrExport", "MonatExportNr"):
        assert f in cols, f"{f} is not exposed"
        assert cols[f]["type"] == "number", f"{f} must be a number, not a date"
        assert not cols[f].get("grainable"), f"{f} must not claim a date grain"


# --------------------------------------------------------------------------
# Privera Posteingang -- the one whose date column is text.
# --------------------------------------------------------------------------


def test_posteingang_does_not_claim_its_text_column_is_a_date():
    """The load-bearing one. ExportDatetime is nvarchar holding 'dd.MM.yyyy',
    and the connection runs us_english, so asking SQL Server to read it as a
    date gives 1 February back as 2 January and raises outright on any day past
    the 12th -- both measured against PROD. Declaring it a date here would ship
    a billing report that fails most months and is wrong the rest of the time."""
    cols = _columns(POSTEIN)
    assert "ExportDatetime" in cols, "the export column is not exposed at all"
    spec = cols["ExportDatetime"]
    assert spec["type"] == "string", (
        "ExportDatetime is nvarchar 'dd.MM.yyyy HH:mm:ss' -- typing it as a date "
        "makes SQL Server parse it under us_english: silently wrong, then failing"
    )
    assert not spec.get("grainable"), "a text column cannot carry a month grain"


def test_posteingang_counts_documents_unfiltered():
    """The workbook's single data field, "Anzahl von Barcode". The month is a
    filter the user applies, not part of the measure."""
    assert "'privera_posteingang_documents'" in _sql(POSTEIN)
    assert _filter_of(POSTEIN, "privera_posteingang_documents") is None


def test_posteingang_keeps_the_workbooks_two_dimensions():
    """Rows Register, columns Niederlassung -- without both, the grid the
    customer is used to seeing cannot be rebuilt."""
    cols = _columns(POSTEIN)
    for f in ("Register", "Niederlassung"):
        assert f in cols, f"{f} is missing, so the workbook layout is unreachable"


def test_posteingang_tells_the_user_how_to_pick_a_month():
    """A text date is surprising enough that the measure has to say so; there is
    nowhere else the reader would find out."""
    block = _measure_block(POSTEIN, "privera_posteingang_documents")
    assert "contains" in block, "the description must explain the contains filter"

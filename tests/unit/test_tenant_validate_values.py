"""_validate_values role handling for generated CRUD pages (views/tenant.py):
'person' is stamped from the session, 'flag' coerces to 0/1."""

from flask import session

from nx_lib.tenant.registry import TenantEntity, TenantField
from nx_lib.views.tenant import _validate_values


def _field(column, role):
    return TenantField(
        tenant="sydoc",
        entity="mediamarkt",
        column=column,
        semantic_role=role,
        lookup_entity=None,
        labels={"en": column},
        visible=True,
        sort_order=0,
    )


ENTITY = TenantEntity(
    tenant="sydoc",
    key="mediamarkt",
    source_object="dbo.MediaMarkt_Batches",
    kind="entries",
    client_code="default",
    engine_role="stats",
    id_column="ID",
    labels={"en": "MediaMarkt batches"},
    sort_order=0,
)
FIELDS = [
    _field("ID", "identifier"),
    _field("Pieces", "count"),
    _field("Corrections", "count"),
    _field("Done", "flag"),
    _field("Visum", "person"),
]


def test_person_is_stamped_from_session_and_flag_coerces(app):
    with app.test_request_context("/"):
        session["username"] = "mah"
        values, errors = _validate_values(
            ENTITY, FIELDS, {"Pieces": "12", "Corrections": "", "Done": True, "Visum": "spoofed"}
        )
    assert errors == []
    assert values == {"Pieces": 12, "Corrections": None, "Done": 1, "Visum": "mah"}


def test_flag_absent_or_false_is_zero_and_person_never_missing(app):
    with app.test_request_context("/"):
        session["username"] = "bap"
        values, errors = _validate_values(ENTITY, FIELDS, {"Pieces": "3", "Corrections": "2"})
    assert errors == []
    assert values["Done"] == 0
    assert values["Visum"] == "bap"

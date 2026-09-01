"""Generali tenant: documents/evaluation/stats/filter, reporting, attendance,
additional services, base services, project management, PDQM, import status.

Split from a single ``generali.py`` module into this package (mechanical move,
see the beautify-phase-0-1 plan, Task 13). Every public function AND every
name the test suite monkeypatches directly on this package object (e.g.
``import nx_lib.views.generali as gv; monkeypatch.setattr(gv, "...", ...)``)
is re-exported below under its original import path, so nothing changes for
callers or tests.
"""

from ...db import engine_generali_db, engine_nexora_db
from ...security import (
    PermissionDenied,
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)
from . import attendance, baseservices, documents, importstatus, pdqm, projectmanagement, reporting
from ._scope import _generali_orgs_for_userids, _generali_scope_where, _generali_userids_in_org
from .attendance import (
    api_generali_attendance_add,
    api_generali_attendance_categories,
    api_generali_attendance_delete,
    api_generali_attendance_edit,
    api_generali_attendance_filter_users,
    api_generali_attendance_list,
    api_generali_attendance_org_users,
    api_generali_attendance_organizations,
    generali_additional_services,
    generali_additionalservices_monthreport,
)
from .baseservices import (
    VALID_BASE_CATEGORIES,
    api_generali_baseservices_add,
    api_generali_baseservices_delete,
    api_generali_baseservices_edit,
    api_generali_baseservices_filter_users,
    api_generali_baseservices_list,
    api_generali_baseservices_org_users,
    api_generali_baseservices_organizations,
    generali_base_services,
    generali_baseservices_monthreport,
)
from .documents import (
    api_generali_document_detail,
    api_generali_documents,
    api_generali_filter_options,
    api_generali_stats,
    generali_documents,
    generali_evaluation,
)
from .importstatus import api_generali_importstatus_list, generali_import_status
from .pdqm import (
    api_generali_pdqm_add,
    api_generali_pdqm_categories,
    api_generali_pdqm_delete,
    api_generali_pdqm_edit,
    api_generali_pdqm_filter_users,
    api_generali_pdqm_list,
    api_generali_pdqm_org_users,
    api_generali_pdqm_organizations,
    generali_pdqm,
    generali_pdqm_monthreport,
)
from .projectmanagement import (
    api_generali_projectmanagement_add,
    api_generali_projectmanagement_delete,
    api_generali_projectmanagement_edit,
    api_generali_projectmanagement_filter_users,
    api_generali_projectmanagement_list,
    api_generali_projectmanagement_org_users,
    api_generali_projectmanagement_organizations,
    generali_project_management,
    generali_projectmanagement_monthreport,
)
from .reporting import (
    REPORTING_CATEGORIES,
    REPORTING_CATEGORY_LABELS,
    api_generali_reporting_add,
    api_generali_reporting_delete,
    api_generali_reporting_edit,
    api_generali_reporting_filter_users,
    api_generali_reporting_list,
    api_generali_reporting_organizations,
    generali_reporting,
    generali_reporting_monthreport,
)

__all__ = [
    "REPORTING_CATEGORIES",
    "REPORTING_CATEGORY_LABELS",
    "VALID_BASE_CATEGORIES",
    "PermissionDenied",
    "_check_add_deadline",
    "_check_generali_record_org",
    "_generali_orgs_for_userids",
    "_generali_scope_where",
    "_generali_userids_in_org",
    "api_generali_attendance_add",
    "api_generali_attendance_categories",
    "api_generali_attendance_delete",
    "api_generali_attendance_edit",
    "api_generali_attendance_filter_users",
    "api_generali_attendance_list",
    "api_generali_attendance_org_users",
    "api_generali_attendance_organizations",
    "api_generali_baseservices_add",
    "api_generali_baseservices_delete",
    "api_generali_baseservices_edit",
    "api_generali_baseservices_filter_users",
    "api_generali_baseservices_list",
    "api_generali_baseservices_org_users",
    "api_generali_baseservices_organizations",
    "api_generali_document_detail",
    "api_generali_documents",
    "api_generali_filter_options",
    "api_generali_importstatus_list",
    "api_generali_pdqm_add",
    "api_generali_pdqm_categories",
    "api_generali_pdqm_delete",
    "api_generali_pdqm_edit",
    "api_generali_pdqm_filter_users",
    "api_generali_pdqm_list",
    "api_generali_pdqm_org_users",
    "api_generali_pdqm_organizations",
    "api_generali_projectmanagement_add",
    "api_generali_projectmanagement_delete",
    "api_generali_projectmanagement_edit",
    "api_generali_projectmanagement_filter_users",
    "api_generali_projectmanagement_list",
    "api_generali_projectmanagement_org_users",
    "api_generali_projectmanagement_organizations",
    "api_generali_reporting_add",
    "api_generali_reporting_delete",
    "api_generali_reporting_edit",
    "api_generali_reporting_filter_users",
    "api_generali_reporting_list",
    "api_generali_reporting_organizations",
    "api_generali_stats",
    "engine_generali_db",
    "engine_nexora_db",
    "generali_additional_services",
    "generali_additionalservices_monthreport",
    "generali_base_services",
    "generali_baseservices_monthreport",
    "generali_documents",
    "generali_evaluation",
    "generali_import_status",
    "generali_pdqm",
    "generali_pdqm_monthreport",
    "generali_project_management",
    "generali_projectmanagement_monthreport",
    "generali_reporting",
    "generali_reporting_monthreport",
    "has_permission",
    "page_visibility",
    "register_routes",
    "require_any_permission",
    "require_permission",
]


def register_routes(app):
    """Fan out to each submodule's register_routes, in the same order the
    original monolithic generali.py registered them."""
    documents.register_routes(app)
    reporting.register_routes(app)
    attendance.register_routes(app)
    baseservices.register_routes(app)
    projectmanagement.register_routes(app)
    pdqm.register_routes(app)
    importstatus.register_routes(app)

"""Admin pages: overview, organizations, maintenance banners, logs, sessions,
user CRUD, access control, permissions.

Split from a single ``admin.py`` module into this package (mechanical move,
see the beautify-phase-0-1 plan, Task 16). Every public function AND every
name the test suite monkeypatches directly on this package object (e.g.
``import nx_lib.views.admin as admin_module; monkeypatch.setattr(admin_module,
"...", ...)``) is re-exported below under its original import path, so
nothing changes for callers or tests. Some tests were retargeted to patch a
specific submodule's own binding instead (e.g.
``nx_lib.views.admin.system.has_permission``) -- each submodule re-imports
``has_permission`` independently, so a single shared binding at this level can
no longer stand in for all of them.
"""

from ... import clients as clients_registry
from ... import mapping_config, status
from ...branding import _HEX_RE, invalidate_branding
from ...branding import registry as branding_registry
from ...clients import _ENGINE_KEYS
from ...config import DOTENV_KEYS, IS_PROD, PATHS, REPO_ROOT
from ...db import (
    engine_generali_db,
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_nexora_db,
    engine_octo_db,
    engine_statistics_db,
    ping_dbs_parallel,
)
from ...files import is_file_allowed
from ...maintenance import (
    _MAINTENANCE_BLOCK_CACHE,
    _get_blocking_maintenance,
    _maintenance_parse_payload,
    _maintenance_row_to_dict,
)
from ...mapping_config import invalidate_mapping_config
from ...security import (
    _revoke_session_by_id,
    has_permission,
    load_permissions_for_user,
    page_visibility,
    require_permission,
)
from . import clients, logs, organizations, overview, permissions, processes, system, users
from .clients import (
    _CLIENT_CODE_RE,
    _CLIENTS_ALLOWED_DIALECTS,
    _SECRET_REF_RE,
    _validate_client_payload,
    admin_clients_view,
    api_admin_clients_add,
    api_admin_clients_delete,
    api_admin_clients_edit,
)
from .logs import (
    _build_logs_where_clause,
    admin_logs_view,
    api_admin_logs_export,
    api_admin_logs_search,
)
from .organizations import (
    _ORG_CODE_RE,
    BRANDING_LOGO_EXTS,
    BRANDING_MAX_BYTES,
    _branding_logo_target,
    _delete_branding_logo,
    _org_exists,
    admin_add_organization,
    admin_delete_organization,
    admin_edit_organization,
    admin_organizations_view,
    api_admin_organization_branding_save,
    api_admin_organizations_list,
)
from .overview import admin_dashboard
from .permissions import (
    admin_access_control,
    admin_permissions_page,
    api_admin_permission_add,
    api_admin_permission_delete,
    api_admin_permission_edit,
    api_admin_permission_holders,
    api_admin_permission_users,
    api_admin_permissions_list,
    api_admin_profile_grants_save,
    api_admin_user_all_permissions,
    api_admin_user_effective_permissions,
    get_user_overrides,
    get_users_admin_access_control,
    save_access_profile,
    save_user_overrides,
)
from .processes import (
    _COLUMN_TYPE_RE,
    _FIELD_KEY_RE,
    _IDENT,
    _PROCESS_NAME_RE,
    _client_code_exists,
    _client_codes,
    _permission_reduction,
    _process_field_dict,
    _process_source_dict,
    _process_source_values,
    _reduction_conflict,
    _validate_field_mapping_payload,
    _validate_identifier_fields,
    _validate_process_identity,
    _validate_process_source_payload,
    _validation_error,
    admin_processes_view,
    api_admin_field_mapping_add,
    api_admin_field_mapping_delete,
    api_admin_field_mapping_edit,
    api_admin_process_source_add,
    api_admin_process_source_delete,
    api_admin_process_source_edit,
    api_admin_processes_list,
)
from .system import (
    _SWITCHABLE_ENVS,
    _restart_allowed,
    admin_maintenance_view,
    admin_status_view,
    api_admin_maintenance_add,
    api_admin_maintenance_delete,
    api_admin_maintenance_edit,
    api_admin_maintenance_list,
    api_admin_restart,
)
from .users import (
    admin_active_sessions,
    admin_add_user,
    admin_delete_user,
    admin_edit_user,
    admin_recent_logs,
    admin_revoke_all_sessions,
    admin_revoke_session,
    admin_sessions_view,
    admin_user_detail,
    api_admin_user_activity,
    api_admin_users_list,
)

__all__ = [
    "BRANDING_LOGO_EXTS",
    "BRANDING_MAX_BYTES",
    "DOTENV_KEYS",
    "IS_PROD",
    "PATHS",
    "REPO_ROOT",
    "_CLIENTS_ALLOWED_DIALECTS",
    "_CLIENT_CODE_RE",
    "_COLUMN_TYPE_RE",
    "_ENGINE_KEYS",
    "_FIELD_KEY_RE",
    "_HEX_RE",
    "_IDENT",
    "_MAINTENANCE_BLOCK_CACHE",
    "_ORG_CODE_RE",
    "_PROCESS_NAME_RE",
    "_SECRET_REF_RE",
    "_SWITCHABLE_ENVS",
    "_branding_logo_target",
    "_build_logs_where_clause",
    "_client_code_exists",
    "_client_codes",
    "_delete_branding_logo",
    "_get_blocking_maintenance",
    "_maintenance_parse_payload",
    "_maintenance_row_to_dict",
    "_org_exists",
    "_permission_reduction",
    "_process_field_dict",
    "_process_source_dict",
    "_process_source_values",
    "_reduction_conflict",
    "_restart_allowed",
    "_revoke_session_by_id",
    "_validate_client_payload",
    "_validate_field_mapping_payload",
    "_validate_identifier_fields",
    "_validate_process_identity",
    "_validate_process_source_payload",
    "_validation_error",
    "admin_access_control",
    "admin_active_sessions",
    "admin_add_organization",
    "admin_add_user",
    "admin_clients_view",
    "admin_dashboard",
    "admin_delete_organization",
    "admin_delete_user",
    "admin_edit_organization",
    "admin_edit_user",
    "admin_logs_view",
    "admin_maintenance_view",
    "admin_organizations_view",
    "admin_permissions_page",
    "admin_processes_view",
    "admin_recent_logs",
    "admin_revoke_all_sessions",
    "admin_revoke_session",
    "admin_sessions_view",
    "admin_status_view",
    "admin_user_detail",
    "api_admin_clients_add",
    "api_admin_clients_delete",
    "api_admin_clients_edit",
    "api_admin_field_mapping_add",
    "api_admin_field_mapping_delete",
    "api_admin_field_mapping_edit",
    "api_admin_logs_export",
    "api_admin_logs_search",
    "api_admin_maintenance_add",
    "api_admin_maintenance_delete",
    "api_admin_maintenance_edit",
    "api_admin_maintenance_list",
    "api_admin_organization_branding_save",
    "api_admin_organizations_list",
    "api_admin_permission_add",
    "api_admin_permission_delete",
    "api_admin_permission_edit",
    "api_admin_permission_holders",
    "api_admin_permission_users",
    "api_admin_profile_grants_save",
    "api_admin_permissions_list",
    "api_admin_process_source_add",
    "api_admin_process_source_delete",
    "api_admin_process_source_edit",
    "api_admin_processes_list",
    "api_admin_restart",
    "api_admin_user_activity",
    "api_admin_user_all_permissions",
    "api_admin_user_effective_permissions",
    "api_admin_users_list",
    "branding_registry",
    "clients_registry",
    "engine_generali_db",
    "engine_ms02_docfields_pg",
    "engine_ms02_pg",
    "engine_ms02_stats_pg",
    "engine_nexora_db",
    "engine_octo_db",
    "engine_statistics_db",
    "get_user_overrides",
    "get_users_admin_access_control",
    "has_permission",
    "invalidate_branding",
    "invalidate_mapping_config",
    "is_file_allowed",
    "load_permissions_for_user",
    "mapping_config",
    "page_visibility",
    "ping_dbs_parallel",
    "register_routes",
    "require_permission",
    "save_access_profile",
    "save_user_overrides",
    "status",
]


def register_routes(app):
    """Fan out to each submodule's register_routes, in the same order the
    original monolithic admin.py registered them."""
    overview.register_routes(app)
    organizations.register_routes(app)
    clients.register_routes(app)
    processes.register_routes(app)
    system.register_routes(app)
    logs.register_routes(app)
    users.register_routes(app)
    permissions.register_routes(app)

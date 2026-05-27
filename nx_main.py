""" "nx_main — WSGI entry point.

wfastcgi expects ``app:app`` so this module stays at the repo root and
exposes the Flask application via the ``nx_lib.create_app()`` factory.

All cross-cutting setup (config, DB engines, extensions, request hooks,
error handlers, security helpers, maintenance lockout) lives in the
``nx_lib/`` package. Routes are being migrated module-by-module under
``nx_lib/views/``. What is still in this file will move there in
subsequent passes.

Backwards compatibility: ``scripts/news/sendReleaseNotice.py`` does
``from app import GRAPH_TENANT_ID, ..., engineNexoraDB``. Those names are
re-exported here via the ``from nx_lib.* import ...`` lines below.
"""

# --- stdlib ---
import base64
import csv
import io
import json
import math
import os
import re
import time
import urllib
import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
    TimeoutError as FuturesTimeoutError,
)
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

# --- third-party ---
import bcrypt
import magic
import pyodbc
import requests
from PIL import Image
from flask import (
    abort,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    session,
    url_for,
)
from flask_babel import gettext, ngettext, _
from pyodbc import DatabaseError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

# --- nx_lib package ---
from nx_lib import create_app
from nx_lib.config import (
    IS_PROD,
    DB_UID,
    DB_PWD,
    DB_SERVER_PRD,
    DB_NEXORA,
    DB_STATISTICS,
    DB_OCTO_RUNTIME,
    DB_GENERALI,
    GRAPH_TENANT_ID,
    GRAPH_CLIENT_ID,
    GRAPH_USERNAME,
    GRAPH_PASSWORD,
    GRAPH_CLIENT_SECRET,
    OCTO_CLIENT_SECRET,
    OCTO_CLIENT_ID,
    OCTO_GRANT_TYPE,
    OCTO_DOMAIN,
    BEXIO_PAT,
)
from nx_lib.db import (
    engineOctoDB,
    engineNexoraDB,
    engineStatisticsDB,
    engineGeneraliDB,
    ping_db,
    ping_dbs_parallel,
    getDBUrl,
)
from nx_lib.extensions import limiter, cache, csrf, s
from nx_lib.i18n import get_locale, get_timezone
from nx_lib.security import (
    PermissionDenied,
    has_permission,
    require_permission,
    require_any_permission,
    load_permissions_for_user,
    _revoke_session_by_id,
    _check_generali_record_org,
    _get_add_min_date,
    _check_add_deadline,
    startpage_redirect_to,
    pageVisability,
)
from nx_lib.maintenance import (
    MAINTENANCE_SEVERITIES,
    _maintenance_iso,
    _maintenance_row_to_dict,
    _maintenance_parse_payload,
    _get_blocking_maintenance,
    _user_has_maintenance_bypass,
    _maintenance_blocks_user,
)
from nx_lib.files import ALLOWED_MIME_TYPES, is_file_allowed
from nx_lib.notifications import create_notification
from nx_lib.users import get_all_portal_users, resolve_user_icon_url
from nx_lib.hooks import get_ip
from nx_lib.octo import (
    get_access_token,
    get_activity_type_name,
    get_domain_for_workitem,
    get_extensions_urls_fields,
    get_index_field_mappings,
    get_media,
    get_workitemdata_param,
)
from nx_lib.process_helpers import (
    build_stat_query,
    get_activityinstancesToIgnore,
    get_params_from_process_list,
    prepare_process_selection_sql,
)

# Build the Flask app via the package factory. All routes live in nx_lib/views/.
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_RUN_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)

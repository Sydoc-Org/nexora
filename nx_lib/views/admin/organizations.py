"""Admin organizations: CRUD + branding.

Branding attaches to the Organization (the customer -- PRVR, LKTR, ...),
never to ClientCode (the runtime source). See nx_lib/branding.py.
"""

import os
import re
from pathlib import Path

import pyodbc
from flask import current_app, jsonify, render_template, request, session
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from ... import clients as clients_registry
from ... import mapping_config
from ...branding import _HEX_RE, invalidate_branding
from ...branding import registry as branding_registry
from ...config import PATHS
from ...db import engine_nexora_db
from ...files import is_file_allowed
from ...security import has_permission, page_visibility, require_permission
from ...tenant.registry import registry as tenant_registry


@require_permission("admin.organizations.view")
def admin_organizations_view():
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT organizationcode, organization, TenantCode AS tenant_code "
            "FROM organizations ORDER BY organization"
        )
        organizations = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        # #98 phase 4: current branding per org, for the panel's initial state.
        # registry() returns None when the load fails (or when the database
        # predates migration 0081) -- degrade to "nothing branded", never error.
        brands = branding_registry() or {}
        for org in organizations:
            org_code = org.get("organizationcode")
            brand = (brands.get(org_code) if isinstance(org_code, str) else None) or {}
            org["brand_name"] = brand.get("name")
            org["brand_accent_hex"] = brand.get("accent_hex")
            org["brand_logo_file"] = brand.get("logo_file")

        # 0090: tenant display names come from the cached registry (None when
        # dbo.Tenants is unavailable, e.g. on TEST -- the code is shown instead).
        treg = tenant_registry()
        for org in organizations:
            t = (
                treg.tenants.get(org.get("tenant_code") or "")
                if treg and org.get("tenant_code")
                else None
            )
            org["tenant_name"] = t.display_name if t else None

        # Picker for the edit modal: an organization belongs to a tenant (or
        # none). An unreadable registry empties the picker, never fails the page.
        tenants = [
            {"code": t.code, "name": t.display_name}
            for t in sorted(
                (treg.tenants.values() if treg else []), key=lambda t: t.display_name.lower()
            )
        ]

        # Users per organization and the data connection each one reaches --
        # the latter derived from its process sources, since an organization
        # has no connection column of its own.
        users_by_org = {
            r[0]: r[1]
            for r in cursor.execute(
                "SELECT organizationCode, COUNT(*) FROM Users "
                "WHERE organizationCode IS NOT NULL GROUP BY organizationCode"
            ).fetchall()
        }
        clients_by_org = _org_client_codes()
        for org in organizations:
            code = org.get("organizationcode")
            org["user_count"] = users_by_org.get(code, 0)
            org["connection"], org["connection_state"] = _org_connection(clients_by_org.get(code))
            org["branding_summary"] = _branding_summary(org)

        return render_template(
            "admin/organizations.html",
            organizations=organizations,
            tenants=tenants,
            orphan_count=sum(1 for o in organizations if not o.get("tenant_code")),
            can_edit_branding=has_permission("admin.organizations.branding.edit"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch organizations: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _tenant_code(data):
    """TenantCode from the modal payload -- an empty pick becomes NULL, i.e. "not
    in a tenant". Referential validity is FK_Organizations_Tenants' job (0090)."""
    return (data.get("tenantcode") or "").strip() or None


def _org_client_codes():
    """{organization code: [client code, ...]} from the process-source registry.

    An organization has no connection column of its own -- it reaches whatever
    its process sources point at. {} when the registry failed to load, so the
    column degrades to "none" rather than raising.
    """
    reg = mapping_config.registry()
    if reg is None:
        return {}
    by_org: dict[str, list[str]] = {}
    for src in reg.sources.values():
        if not src.organization:
            continue
        codes = by_org.setdefault(src.organization, [])
        if src.client not in codes:
            codes.append(src.client)
    return {org: sorted(codes) for org, codes in by_org.items()}


def _org_connection(codes):
    """(label, state) for an organization's Data connection cell. "Configured"
    is the dbo.Clients row; "loaded" is whether the runtime actually built it."""
    if not codes:
        return None, "none"
    missing = [c for c in codes if c not in clients_registry.CLIENTS]
    if missing:
        return ", ".join(missing), "unloaded"
    return ", ".join(codes), "loaded"


def _branding_summary(org):
    """Which of the two brand overrides an organization actually sets."""
    has_logo = bool(org.get("brand_logo_file"))
    has_accent = bool(org.get("brand_accent_hex"))
    if has_logo and has_accent:
        return "both"
    if has_accent:
        return "accent"
    if has_logo:
        return "logo"
    return "default"


@require_permission("admin.organizations.view")
def admin_organization_detail_view(organizationcode):
    """One organization: its users, access profiles, data and processes,
    branding and tenant membership.

    Absorbs what used to be spread across the organizations modal, the
    branding panel and the Process Configurations page -- the process sources
    shown here are exactly this organization's, not every client's.
    """
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT organizationcode, organization, TenantCode AS tenant_code "
            "FROM organizations WHERE organizationcode = ?",
            (organizationcode,),
        )
        row = cursor.fetchone()
        if not row:
            return render_template("handlers/404.html"), 404
        org = dict(zip([c[0] for c in cursor.description], row, strict=False))

        brand = (branding_registry() or {}).get(org["organizationcode"]) or {}
        org["brand_name"] = brand.get("name")
        org["brand_accent_hex"] = brand.get("accent_hex")
        org["brand_logo_file"] = brand.get("logo_file")
        org["branding_summary"] = _branding_summary(org)

        cursor.execute(
            "SELECT u.username, u.Fullname, u.LastLoginAt, ap.Name AS profile "
            "FROM Users u LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessid "
            "WHERE u.organizationCode = ? ORDER BY u.Fullname, u.username",
            (organizationcode,),
        )
        users = [
            dict(zip([c[0] for c in cursor.description], r, strict=False))
            for r in cursor.fetchall()
        ]

        # Bound profiles belong to this organization; global ones are shared.
        cursor.execute(
            "SELECT ap.AccessID, ap.Name, ap.OrganizationCode, "
            "(SELECT COUNT(*) FROM Users u WHERE u.accessid = ap.AccessID) AS user_count "
            "FROM AccessProfile ap WHERE ap.OrganizationCode = ? OR ap.OrganizationCode IS NULL "
            "ORDER BY ap.OrganizationCode DESC, ap.Name",
            (organizationcode,),
        )
        profiles = [
            dict(zip([c[0] for c in cursor.description], r, strict=False))
            for r in cursor.fetchall()
        ]

        treg = tenant_registry()
        t = (
            treg.tenants.get(org.get("tenant_code") or "")
            if treg and org.get("tenant_code")
            else None
        )
        org["tenant_name"] = t.display_name if t else None
        tenants = [
            {"code": x.code, "name": x.display_name}
            for x in sorted(
                (treg.tenants.values() if treg else []), key=lambda x: x.display_name.lower()
            )
        ]

        # This organization's process sources, with their field mappings, read
        # through the cached registry rather than raw SQL (same contract as the
        # Process Configurations page).
        reg = mapping_config.registry()
        sources: list[dict] = []
        if reg is not None:
            for (client, process), src in sorted(reg.sources.items()):
                if src.organization != organizationcode:
                    continue
                sources.append(
                    {
                        "client": client,
                        "process": process,
                        "table": src.table,
                        "alias": src.alias,
                        "export_column": src.export_column,
                        "import_column": src.import_column,
                        "workitem_column": src.workitem_column,
                        "id_column_type": src.id_column_type,
                        "fields": sorted(
                            (
                                {
                                    "field_key": m.field_key,
                                    "column": m.column,
                                    "column_type": m.column_type,
                                }
                                for m in reg.mappings
                                if m.client == client and m.process == process
                            ),
                            key=lambda m: m["field_key"] or "",
                        ),
                    }
                )

        codes = sorted({str(s["client"]) for s in sources})
        org["connection"], org["connection_state"] = _org_connection(codes)
        connections = _connection_cards(cursor, codes)

        return render_template(
            "admin/organization_detail.html",
            org=org,
            users=users,
            profiles=profiles,
            tenants=tenants,
            sources=sources,
            connections=connections,
            mapping_config_available=reg is not None,
            client_codes=sorted(clients_registry.CLIENTS),
            can_edit_branding=has_permission("admin.organizations.branding.edit"),
            can_edit_processes=has_permission("admin.processes.edit"),
            can_edit_clients=has_permission("admin.clients.edit"),
            engine_keys=clients_registry._ENGINE_KEYS,
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to render organization {organizationcode}: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _connection_cards(cursor, codes):
    """The dbo.Clients rows behind an organization's process sources."""
    if not codes:
        return []
    marks = ",".join("?" * len(codes))
    try:
        cursor.execute(
            "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, StatsEngineKey, "
            "StatsDialect, DocfieldsEngineKey, DocfieldsDialect, OctoDomain, SecretRef, "
            f"IsActive FROM dbo.Clients WHERE ClientCode IN ({marks}) ORDER BY ClientCode",
            codes,
        )
    except Exception as e:
        current_app.logger.warning(f"dbo.Clients unavailable for the organization detail: {e}")
        return []
    rows = [
        dict(zip([c[0] for c in cursor.description], r, strict=False)) for r in cursor.fetchall()
    ]
    for c in rows:
        c["loaded"] = c["ClientCode"] in clients_registry.CLIENTS
    return rows


@require_permission("admin.organizations.add")
def admin_add_organization():
    import re as _re

    data = request.get_json()
    organization = data.get("organizationname")

    if not organization:
        return jsonify({"success": False, "message": _("All fields are required.")}), 400

    clean_name = _re.sub(r"[^A-Z0-9]", "", organization.upper())
    consonants = _re.sub(r"[AEIOU]", "", clean_name)
    vowels = _re.sub(r"[^AEIOU]", "", clean_name)
    code = consonants + vowels
    organizationcode = code[:4].ljust(4, "X")

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO organizations (organizationcode, organization, TenantCode) VALUES (?,?,?)",
            (organizationcode, organization, _tenant_code(data)),
        )
        conn.commit()
        return jsonify({"success": True, "message": _("Organization created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({"success": False, "message": _("Organization already exists.")}), 409
    except Exception as e:
        current_app.logger.error(f"Error adding organization: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.organizations.edit")
def admin_edit_organization(organizationcode):
    data = request.get_json()
    organization = data.get("organizationname")
    current_user_id = session["userid"]

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE organizations SET organization=?, TenantCode=? WHERE organizationcode=?",
            (organization, _tenant_code(data), organizationcode),
        )
        conn.commit()
        return jsonify({"success": True, "message": _("Organization updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error editing Organization {current_user_id}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.organizations.delete")
def admin_delete_organization(organizationcode):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM organizations WHERE organizationcode=?", (organizationcode,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Organization not found.")}), 404

        # A delete mutates the branding registry exactly like a save does: skip
        # this and the dead org keeps its brand -- and /branding/<code>/logo
        # keeps serving its image -- for up to the 60s TTL. The file has to go
        # too, or it is orphaned forever and would be re-exposed verbatim if the
        # same org code is ever created again (#98 phase 4).
        _delete_branding_logo(organizationcode)
        invalidate_branding()

        return jsonify({"success": True, "message": _("Organization deleted successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error deleting Organization {organizationcode}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.organizations.view")
def api_admin_organizations_list():
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT organizationcode, organization FROM organizations ORDER BY organization"
        )
        orgs = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(orgs)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch organizations list: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ------------------------------ organization branding ----------------------- #

BRANDING_MAX_BYTES = 512 * 1024
# Narrows is_file_allowed's own table, which also knows pdf/xlsx. The ext check
# short-circuits before the sniff, so a PDF never reaches the stream at all.
BRANDING_LOGO_EXTS = ("svg", "png", "jpg", "jpeg")
# The org code is used to build a filename, so it must be a plain code. Task 10's
# serve route defends itself independently (os.path.basename on the stored name).
_ORG_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


def _branding_logo_target(branding_dir: Path, filename: str) -> Path | None:
    """Resolve ``filename`` inside ``branding_dir``, or None if it escapes it.

    The single path derivation + traversal check shared by the upload and the
    delete side (the serve side in nx_lib/views/core.py defends itself with the
    same basename/containment idiom against a hostile stored value)."""
    target = (branding_dir / os.path.basename(filename)).resolve()
    if target.parent != branding_dir.resolve():
        return None
    return target


def _delete_branding_logo(organizationcode: str) -> None:
    """Remove the logo files an organization's uploads left in var/branding/.

    Sweeps every allowed extension rather than trusting BrandLogoFile: the row
    is already gone by the time this runs, a NULL BrandLogoFile can still
    coexist with a file on disk (switching formats leaves the old extension
    behind), and every upload writes exactly ``<orgcode>.<ext>``. A missing
    file is not an error."""
    if not _ORG_CODE_RE.match(organizationcode or ""):
        return
    branding_dir = Path(PATHS.branding)
    for ext in BRANDING_LOGO_EXTS:
        target = _branding_logo_target(branding_dir, f"{organizationcode}.{ext}")
        if target is None:
            continue
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            current_app.logger.warning(f"branding logo unlink failed for {target}: {e}")


def _org_exists(cursor, organizationcode):
    cursor.execute(
        "SELECT organizationcode FROM organizations WHERE organizationcode = ?",
        (organizationcode,),
    )
    return cursor.fetchone() is not None


@require_permission("admin.organizations.branding.edit")
def api_admin_organization_branding_save(organizationcode):
    """Save an organization's brand name, accent hex and logo (#98 phase 4).

    Accepts JSON (name/accent only) or multipart/form-data (plus ``logo``).

    Upload safety is nx_lib/files.py's ``is_file_allowed`` -- secure_filename
    plus a libmagic sniff of the actual bytes. The client-declared content type
    is never consulted. SVG is allowed (spec D9) and is script-capable, which is
    why branding_logo() serves every logo with a sandbox CSP + nosniff.

    Path traversal: ``organizationcode`` reaches a filesystem path, so it is
    matched against _ORG_CODE_RE first and the resolved target is re-checked to
    live directly inside PATHS.branding. The stored filename is derived from the
    org code, never from the uploaded filename.
    """
    if not _ORG_CODE_RE.match(organizationcode or ""):
        return jsonify({"success": False, "message": _("Organization not found.")}), 404

    data = (request.get_json(silent=True) or {}) if request.is_json else request.form

    brand_name = (data.get("brand_name") or "").strip() or None
    accent = (data.get("brand_accent_hex") or "").strip() or None
    if accent is not None and not _HEX_RE.match(accent):
        return (
            jsonify(
                {"success": False, "message": _("Accent colour must be a hex value like #336699.")}
            ),
            400,
        )

    logo = request.files.get("logo")
    logo_bytes = None
    logo_filename = None
    if logo is not None and logo.filename:
        safe_name = secure_filename(logo.filename)
        ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if ext not in BRANDING_LOGO_EXTS:
            return (
                jsonify(
                    {"success": False, "message": _("Logo must be an SVG, PNG or JPEG image.")}
                ),
                400,
            )
        # Size before sniff, and both before anything touches the disk.
        logo.stream.seek(0, os.SEEK_END)
        size = logo.stream.tell()
        logo.stream.seek(0)
        if size > BRANDING_MAX_BYTES:
            return (
                jsonify({"success": False, "message": _("Logo is too large (max 512 KB).")}),
                400,
            )
        if not is_file_allowed(safe_name, logo.stream):
            return (
                jsonify(
                    {"success": False, "message": _("Logo must be an SVG, PNG or JPEG image.")}
                ),
                400,
            )
        logo_bytes = logo.stream.read()
        logo_filename = f"{organizationcode}.{ext}"

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if not _org_exists(cursor, organizationcode):
            return jsonify({"success": False, "message": _("Organization not found.")}), 404

        if logo_bytes is not None:
            assert logo_filename is not None  # set together with logo_bytes above
            branding_dir = Path(PATHS.branding)
            branding_dir.mkdir(parents=True, exist_ok=True)
            target = _branding_logo_target(branding_dir, logo_filename)
            if target is None:
                return jsonify({"success": False, "message": _("Organization not found.")}), 404
            target.write_bytes(logo_bytes)
            cursor.execute(
                "UPDATE organizations SET BrandName=?, BrandAccentHex=?, BrandLogoFile=? "
                "WHERE organizationcode=?",
                (brand_name, accent, logo_filename, organizationcode),
            )
        else:
            cursor.execute(
                "UPDATE organizations SET BrandName=?, BrandAccentHex=? WHERE organizationcode=?",
                (brand_name, accent, organizationcode),
            )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving branding for {organizationcode}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Must run on every successful save -- otherwise the edit looks broken for
    # up to the registry's 60s TTL.
    invalidate_branding()
    return jsonify(
        {
            "success": True,
            "message": _("Branding saved."),
            # brand_logo_file is null when this save carried no upload: the
            # stored logo is left untouched, so the caller keeps what it had.
            "brand": {
                "brand_name": brand_name,
                "brand_accent_hex": accent,
                "brand_logo_file": logo_filename,
            },
        }
    )


def register_routes(app):
    app.add_url_rule(
        "/admin/organizations",
        endpoint="admin_organizations_view",
        view_func=admin_organizations_view,
    )
    app.add_url_rule(
        "/admin/organizations/detail/<organizationcode>",
        endpoint="admin_organization_detail_view",
        view_func=admin_organization_detail_view,
    )
    app.add_url_rule(
        "/admin/organizations/add",
        endpoint="admin_add_organization",
        view_func=admin_add_organization,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/organizations/edit/<organizationcode>",
        endpoint="admin_edit_organization",
        view_func=admin_edit_organization,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/organizations/delete/<organizationcode>",
        endpoint="admin_delete_organization",
        view_func=admin_delete_organization,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/admin/organizations/list",
        endpoint="api_admin_organizations_list",
        view_func=api_admin_organizations_list,
    )
    app.add_url_rule(
        "/admin/organizations/<organizationcode>/branding",
        endpoint="api_admin_organization_branding_save",
        view_func=api_admin_organization_branding_save,
        methods=["POST"],
    )

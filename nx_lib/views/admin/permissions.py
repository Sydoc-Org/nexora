"""Admin access control & permissions: profiles, overrides, permission CRUD."""

from contextlib import suppress

from flask import current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...security import (
    assignable_profile_ids,
    has_permission,
    load_permissions_for_user,
    page_visibility,
    require_permission,
)


@require_permission("admin.view.accessprofiles.useroverrides")
def admin_access_control():
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ap.AccessID, ap.Name, ap.Description, COUNT(u.userID) AS UserCount
            FROM AccessProfile ap
            LEFT JOIN Users u ON u.accessID = ap.AccessID
            GROUP BY ap.AccessID, ap.Name, ap.Description
            ORDER BY ap.Name
        """)
        profiles = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT PermissionID, Code, Description FROM Permission
            ORDER BY
                LEFT(Code, LEN(Code) - CHARINDEX('.', REVERSE(Code))),
                CASE
                    WHEN Code LIKE '%.view'    THEN 1
                    WHEN Code LIKE '%.add'     THEN 2
                    WHEN Code LIKE '%.add.%'   THEN 3
                    WHEN Code LIKE '%.edit%'   THEN 4
                    WHEN Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                Code
        """)
        all_permissions = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        organizations = []
        assignable_profiles = []
        if has_permission("admin.view.users"):
            cursor.execute(
                "SELECT organizationcode, organization FROM Organizations ORDER BY organization"
            )
            organizations = [
                dict(zip([column[0] for column in cursor.description], row, strict=False))
                for row in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT ap.name profile, ap.accessid accessid FROM AccessProfile ap ORDER BY ap.name"
            )
            all_ap = [
                dict(zip([column[0] for column in cursor.description], row, strict=False))
                for row in cursor.fetchall()
            ]
            assignable = assignable_profile_ids()
            assignable_profiles = [ap for ap in all_ap if ap["accessid"] in assignable]

        return render_template(
            "admin/access_control.html",
            profiles=profiles,
            all_permissions=all_permissions,
            organizations=organizations,
            assignable_profiles=assignable_profiles,
            can_edit_accessprofile=has_permission("admin.edit.accessprofile"),
            can_view_users=has_permission("admin.view.users"),
            can_create_user=has_permission("admin.create.user"),
            can_edit_user=has_permission("admin.edit.user"),
            can_delete_user=has_permission("admin.delete.user"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading access control: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def admin_permission_matrix():
    """Read-only user x permission matrix (#172) -- filterable either
    direction. Editing stays on access_control / user_detail; this page only
    links through to them."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT PermissionID, Code, Description FROM Permission
            ORDER BY
                LEFT(Code, LEN(Code) - CHARINDEX('.', REVERSE(Code))),
                CASE
                    WHEN Code LIKE '%.view'    THEN 1
                    WHEN Code LIKE '%.add'     THEN 2
                    WHEN Code LIKE '%.add.%'   THEN 3
                    WHEN Code LIKE '%.edit%'   THEN 4
                    WHEN Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                Code
        """)
        all_permissions = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT u.userID, u.username, u.Fullname, u.organizationCode, o.organization
            FROM Users u
            LEFT JOIN Organizations o ON o.organizationcode = u.organizationCode
            ORDER BY u.Fullname
        """)
        all_users = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        return render_template(
            "admin/permission_matrix.html",
            all_permissions=all_permissions,
            all_users=all_users,
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading permission matrix: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_permission_holders(permission_id):
    """Mirror of api_admin_user_effective_permissions with the axes flipped:
    one permission, resolved across every user."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT PermissionID, Code, Description FROM Permission WHERE PermissionID = ?",
            (permission_id,),
        )
        p = cursor.fetchone()
        if not p:
            return jsonify({"success": False, "message": "Permission not found"}), 404

        cursor.execute(
            """
            SELECT u.userID, u.username, u.Fullname, u.organizationCode, o.organization,
                   CASE WHEN ap_perm.PermissionID IS NULL THEN NULL ELSE 'A' END AS ProfileEffect,
                   uo.Effect      AS OverrideEffect
            FROM Users u
            LEFT JOIN Organizations o ON o.organizationcode = u.organizationCode
            LEFT JOIN AccessProfilePermission ap_perm
                   ON ap_perm.AccessID = u.accessid
                  AND ap_perm.PermissionID = ?
            LEFT JOIN UserPermissionOverride uo
                   ON uo.UserID = u.userID
                  AND uo.PermissionID = ?
            ORDER BY u.Fullname
        """,
            (permission_id, permission_id),
        )

        holders = []
        for r in cursor.fetchall():
            override = r.OverrideEffect
            profile = r.ProfileEffect
            if override == "A":
                source = "override-allow"
            elif override == "D":
                continue  # explicitly denied -- not a holder
            elif profile == "A":
                source = "profile"
            else:
                continue  # no grant, no override -- not a holder

            holders.append(
                {
                    "userID": r.userID,
                    "username": r.username,
                    "fullname": r.Fullname,
                    "organizationCode": r.organizationCode,
                    "organization": r.organization,
                    "source": source,
                }
            )

        return jsonify(
            {
                "success": True,
                "permission": {
                    "PermissionID": p.PermissionID,
                    "Code": p.Code,
                    "Description": p.Description,
                },
                "holders": holders,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to compute holders for permission {permission_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_users_admin_access_control():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    profile_filter = request.args.get("profile", "").strip()
    org_filter = request.args.get("organization", "").strip()

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        where_parts = ["1=1"]
        params = []
        if profile_filter:
            where_parts.append("ap.Name = ?")
            params.append(profile_filter)
        if org_filter:
            where_parts.append("o.organizationcode = ?")
            params.append(org_filter)
        where_clause = " AND ".join(where_parts)

        query = f"""
            SELECT
                u.userID, u.username, u.fullname, u.email,
                ap.Name AS AccessProfileName, ap.AccessID AS AccessProfileID,
                o.organizationcode,
                o.organization,
                (SELECT COUNT(*) FROM UserPermissionOverride upo WHERE upo.UserID = u.userID) AS OverrideCount
            FROM Users u
            LEFT JOIN AccessProfile ap ON u.accessid = ap.AccessID
            LEFT JOIN Organizations o ON u.organizationcode = o.organizationcode
            WHERE {where_clause}
            ORDER BY u.fullname
        """
        cursor.execute(query, params)

        users = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(users)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch users for access control: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_profile_details(access_id):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT PermissionID, 'A' AS Effect
            FROM AccessProfilePermission
            WHERE AccessID = ?
            """,
            (access_id,),
        )
        assigned_perms = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "permissions": assigned_perms})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def save_access_profile():
    data = request.get_json()
    access_id = data.get("accessId")
    name = data.get("name")
    description = data.get("description")
    permissions = data.get("permissions")

    if not name:
        return jsonify({"success": False, "message": _("Name is required")}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if access_id:
            cursor.execute(
                "UPDATE AccessProfile SET Name=?, Description=? WHERE AccessID=?",
                (name, description, access_id),
            )
            cursor.execute("DELETE FROM AccessProfilePermission WHERE AccessID=?", (access_id,))
        else:
            # A new profile's Rank must default to the creating actor's own
            # Rank, not the column's DEFAULT 0 (#238 Phase 1 review finding):
            # since assignable_profile_ids() treats Rank<=own-Rank as
            # assignable, a Rank-0 profile would be assignable by every
            # profiled actor, including one just granted powerful
            # permissions. Self-limiting per spec D5 -- an actor can never
            # create a profile ranked above their own. Fails closed to 0
            # only if the actor genuinely has no profile of their own; a
            # lookup problem here must not block profile creation.
            cursor.execute(
                """
                SELECT ISNULL(MAX(me.Rank), 0)
                FROM dbo.Users u JOIN dbo.AccessProfile me ON me.AccessID = u.accessid
                WHERE u.userID = ?
                """,
                (session.get("userid"),),
            )
            rank_row = cursor.fetchone()
            creator_rank = rank_row[0] if rank_row and rank_row[0] is not None else 0
            cursor.execute(
                "INSERT INTO AccessProfile (Name, Description, Rank) "
                "OUTPUT INSERTED.AccessID VALUES (?, ?, ?)",
                (name, description, creator_rank),
            )
            inserted = cursor.fetchone()
            assert inserted is not None  # INSERT ... OUTPUT always returns the new row
            access_id = inserted[0]

        if permissions:
            params = [(access_id, p["PermissionID"]) for p in permissions if p.get("Effect") == "A"]
            if params:
                cursor.executemany(
                    "INSERT INTO AccessProfilePermission (AccessID, PermissionID) VALUES (?, ?)",
                    params,
                )
        conn.commit()
        session["permissions"] = load_permissions_for_user(session["userid"])
        return jsonify({"success": True, "message": _("Profile saved successfully")})
    except Exception as e:
        current_app.logger.error(f"Error saving profile: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_user_overrides(user_id):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT AccessID FROM Users WHERE UserID = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "User not found"}), 404
        base_access_id = row[0]
        cursor.execute(
            "SELECT PermissionID, Effect FROM UserPermissionOverride WHERE UserID = ?", (user_id,)
        )
        overrides = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        base_perms = {}
        if base_access_id:
            cursor.execute(
                "SELECT PermissionID, 'A' AS Effect FROM AccessProfilePermission WHERE AccessID = ?",
                (base_access_id,),
            )
            base_perms = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        return jsonify(
            {
                "success": True,
                "overrides": overrides,
                "base_permissions": base_perms,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_user_effective_permissions(user_id):
    """Compute the merged permission set: profile-grant unless an override
    flips it. Source on each entry tells the UI whether it came from the
    profile or from an Allow override."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT u.userID, u.username, u.AccessID, ap.Name AS ProfileName
            FROM Users u
            LEFT JOIN AccessProfile ap ON ap.AccessID = u.AccessID
            WHERE u.userID = ?
        """,
            (user_id,),
        )
        u = cursor.fetchone()
        if not u:
            return jsonify({"success": False, "message": "User not found"}), 404

        cursor.execute(
            """
            SELECT p.PermissionID, p.Code, p.Description,
                   CASE WHEN ap_perm.PermissionID IS NULL THEN NULL ELSE 'A' END AS ProfileEffect,
                   uo.Effect      AS OverrideEffect
            FROM Permission p
            LEFT JOIN AccessProfilePermission ap_perm
                   ON ap_perm.PermissionID = p.PermissionID
                  AND ap_perm.AccessID = ?
            LEFT JOIN UserPermissionOverride uo
                   ON uo.PermissionID = p.PermissionID
                  AND uo.UserID = ?
            ORDER BY
                LEFT(p.Code, LEN(p.Code) - CHARINDEX('.', REVERSE(p.Code))),
                CASE
                    WHEN p.Code LIKE '%.view'    THEN 1
                    WHEN p.Code LIKE '%.add'     THEN 2
                    WHEN p.Code LIKE '%.add.%'   THEN 3
                    WHEN p.Code LIKE '%.edit%'   THEN 4
                    WHEN p.Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                p.Code
        """,
            (u.AccessID, user_id),
        )

        granted: list = []
        denied: list = []
        for r in cursor.fetchall():
            override = r.OverrideEffect
            profile = r.ProfileEffect
            if override == "A":
                source = "override-allow"
                effective = True
            elif override == "D":
                source = "override-deny"
                effective = False
            elif profile == "A":
                source = "profile"
                effective = True
            elif profile == "D":
                source = "profile-deny"
                effective = False
            else:
                continue  # No grant, no override — irrelevant

            entry = {
                "PermissionID": r.PermissionID,
                "Code": r.Code,
                "Description": r.Description,
                "source": source,
            }
            (granted if effective else denied).append(entry)

        return jsonify(
            {
                "success": True,
                "user": {
                    "userID": u.userID,
                    "username": u.username,
                    "profile": u.ProfileName,
                },
                "granted": granted,
                "denied": denied,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to compute effective permissions for user {user_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.edit.user.override")
def save_user_overrides():
    data = request.get_json()
    user_id = data.get("userId")
    overrides = data.get("overrides")

    if not user_id:
        return jsonify({"success": False, "message": "User ID required"}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM UserPermissionOverride WHERE UserID=?", (user_id,))

        if overrides:
            params = [(user_id, p["PermissionID"], p["Effect"]) for p in overrides]
            cursor.executemany(
                "INSERT INTO UserPermissionOverride (UserID, PermissionID, Effect) VALUES (?, ?, ?)",
                params,
            )

        conn.commit()
        session["permissions"] = load_permissions_for_user(session["userid"])
        return jsonify({"success": True, "message": _("Overrides updated successfully")})
    except Exception as e:
        current_app.logger.error(f"Error saving overrides: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_permissions_list():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.PermissionID, p.Code, p.Description,
                (SELECT COUNT(*) FROM AccessProfilePermission a WHERE a.PermissionID = p.PermissionID) AS ProfileCount,
                (SELECT COUNT(*) FROM UserPermissionOverride o WHERE o.PermissionID = p.PermissionID) AS OverrideCount
            FROM Permission p
            ORDER BY
                LEFT(p.Code, LEN(p.Code) - CHARINDEX('.', REVERSE(p.Code))),
                CASE
                    WHEN p.Code LIKE '%.view'    THEN 1
                    WHEN p.Code LIKE '%.add'     THEN 2
                    WHEN p.Code LIKE '%.add.%'   THEN 3
                    WHEN p.Code LIKE '%.edit%'   THEN 4
                    WHEN p.Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                p.Code
        """)
        perms = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(perms)
    except Exception as e:
        current_app.logger.error(f"Error listing permissions: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_permission_users(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Code FROM Permission WHERE PermissionID = ?", (perm_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        perm_code = row[0]
        cursor.execute(
            """
            SELECT
                u.userID, u.username, u.fullname,
                ap.Name AS AccessProfileName,
                CAST(dbo.fnUserHasPermission(u.userID, ?) AS INT) AS HasPermission,
                upo.Effect AS OverrideEffect,
                CASE WHEN app.PermissionID IS NULL THEN NULL ELSE 'A' END AS ProfileEffect
            FROM Users u
            LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessID
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = u.userID AND upo.PermissionID = ?
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = ?
            ORDER BY u.fullname
        """,
            (perm_code, perm_id, perm_id),
        )
        users = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "users": users})
    except Exception as e:
        current_app.logger.error(f"Error fetching users for permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_user_all_permissions(user_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                p.PermissionID, p.Code, p.Description,
                CAST(dbo.fnUserHasPermission(?, p.Code) AS INT) AS IsEffective,
                upo.Effect AS OverrideEffect,
                CASE WHEN app.PermissionID IS NULL THEN NULL ELSE 'A' END AS ProfileEffect
            FROM Permission p
            LEFT JOIN Users u ON u.userID = ?
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = ? AND upo.PermissionID = p.PermissionID
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = p.PermissionID
            ORDER BY p.Code
        """,
            (user_id, user_id, user_id),
        )
        perms = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "permissions": perms})
    except Exception as e:
        current_app.logger.error(f"Error fetching all permissions for user {user_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_add():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get("code") or "").strip()
    description = (data.get("description") or "").strip()
    if not code or not description:
        return jsonify({"success": False, "message": _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Permission (Code, Description) OUTPUT INSERTED.PermissionID VALUES (?, ?)",
            (code, description),
        )
        inserted = cursor.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        new_id = inserted[0]
        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": _("Permission created successfully"),
                "permissionId": new_id,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error creating permission: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_edit(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get("code") or "").strip()
    description = (data.get("description") or "").strip()
    if not code or not description:
        return jsonify({"success": False, "message": _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Permission SET Code=?, Description=? WHERE PermissionID=?",
            (code, description, perm_id),
        )
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        conn.commit()
        return jsonify({"success": True, "message": _("Permission updated successfully")})
    except Exception as e:
        current_app.logger.error(f"Error updating permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_delete(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM AccessProfilePermission WHERE PermissionID=?", (perm_id,)
        )
        profile_refs_row = cursor.fetchone()
        assert profile_refs_row is not None  # SELECT COUNT(*) always returns exactly one row
        profile_refs = profile_refs_row[0]
        cursor.execute(
            "SELECT COUNT(*) FROM UserPermissionOverride WHERE PermissionID=?", (perm_id,)
        )
        override_refs_row = cursor.fetchone()
        assert override_refs_row is not None  # SELECT COUNT(*) always returns exactly one row
        override_refs = override_refs_row[0]
        if profile_refs > 0 or override_refs > 0:
            return jsonify(
                {
                    "success": False,
                    "message": _(
                        "Cannot delete: used in %(p)d profile(s) and %(o)d override(s). Remove all assignments first."
                    )
                    % {"p": profile_refs, "o": override_refs},
                }
            ), 400
        cursor.execute("DELETE FROM Permission WHERE PermissionID=?", (perm_id,))
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        conn.commit()
        return jsonify({"success": True, "message": _("Permission deleted successfully")})
    except Exception as e:
        current_app.logger.error(f"Error deleting permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/admin/access_control", endpoint="admin_access_control", view_func=admin_access_control
    )
    app.add_url_rule(
        "/admin/permission_matrix",
        endpoint="admin_permission_matrix",
        view_func=admin_permission_matrix,
    )
    app.add_url_rule(
        "/api/admin/permissions/<int:permission_id>/holders",
        endpoint="api_admin_permission_holders",
        view_func=api_admin_permission_holders,
    )
    app.add_url_rule(
        "/api/admin/users",
        endpoint="get_users_admin_access_control",
        view_func=get_users_admin_access_control,
    )
    app.add_url_rule(
        "/api/admin/access_profile/<int:access_id>/details",
        endpoint="get_profile_details",
        view_func=get_profile_details,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/access_profile/save",
        endpoint="save_access_profile",
        view_func=save_access_profile,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/user_overrides/<int:user_id>",
        endpoint="get_user_overrides",
        view_func=get_user_overrides,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/users/<int:user_id>/effective_permissions",
        endpoint="api_admin_user_effective_permissions",
        view_func=api_admin_user_effective_permissions,
    )
    app.add_url_rule(
        "/api/admin/user_overrides/save",
        endpoint="save_user_overrides",
        view_func=save_user_overrides,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/list",
        endpoint="api_admin_permissions_list",
        view_func=api_admin_permissions_list,
    )
    app.add_url_rule(
        "/api/admin/permissions/<int:perm_id>/users",
        endpoint="api_admin_permission_users",
        view_func=api_admin_permission_users,
    )
    app.add_url_rule(
        "/api/admin/users/<int:user_id>/all_permissions",
        endpoint="api_admin_user_all_permissions",
        view_func=api_admin_user_all_permissions,
    )
    app.add_url_rule(
        "/api/admin/permissions/add",
        endpoint="api_admin_permission_add",
        view_func=api_admin_permission_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/edit/<int:perm_id>",
        endpoint="api_admin_permission_edit",
        view_func=api_admin_permission_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/delete/<int:perm_id>",
        endpoint="api_admin_permission_delete",
        view_func=api_admin_permission_delete,
        methods=["DELETE"],
    )

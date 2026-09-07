"""Generali shared org helpers used across the reporting/attendance/baseservices/
projectmanagement/pdqm submodules."""

from flask import current_app, session

from ...db import engine_nexora_db


def _generali_orgs_for_userids(user_ids):
    if not user_ids:
        return []
    # local import: re-resolve against the live package object so test
    # monkeypatching of gv.engine_nexora_db still works post-split
    # (nx_lib/views/generali/__init__.py owns this name; a top-of-file
    # import here would bind a stale copy at import time for callers that
    # are exercised through a monkeypatched gv.engine_nexora_db, e.g. the
    # reporting/pdqm "organizations" endpoints).
    from . import engine_nexora_db

    nx_conn = engine_nexora_db.raw_connection()
    try:
        nx_cur = nx_conn.cursor()
        placeholders = ",".join(["?"] * len(user_ids))
        nx_cur.execute(
            f"""
            SELECT DISTINCT u.organizationcode, o.organization
            FROM Users u
            LEFT JOIN organizations o ON o.organizationcode = u.organizationcode
            WHERE u.userid IN ({placeholders}) AND u.organizationcode IS NOT NULL
            ORDER BY o.organization, u.organizationcode
        """,
            user_ids,
        )
        return [{"code": r[0], "name": r[1] or r[0]} for r in nx_cur.fetchall()]
    finally:
        nx_conn.close()


def _generali_userids_in_org(org_code):
    nx_conn = engine_nexora_db.raw_connection()
    try:
        nx_cur = nx_conn.cursor()
        nx_cur.execute("SELECT userid FROM Users WHERE organizationcode = ?", [org_code])
        return [r[0] for r in nx_cur.fetchall()]
    finally:
        nx_conn.close()


def _generali_scope_where(perm_prefix, user_column, requested_org_code):
    """WHERE fragment enforcing a Generali list query's org/self visibility from
    the caller's GRANTS -- never from a client-supplied organizationcode (#193
    cross-org read). Returns (clauses, params):

    - <perm>.edit.all: honour an optional requested org filter,
      otherwise no constraint (all orgs).
    - <perm>.edit.org only: clamp to the caller's SESSION org; any
      requested organizationcode is ignored.
    - neither grant: clamp to the caller's own user id.

    Emits a fail-closed "1=0" clause when the target org resolves to no users,
    so an empty/unknown org can never widen the result set.
    """
    # local import: re-resolve against the live package object so test
    # monkeypatching of gv.has_permission / gv._generali_userids_in_org still
    # works post-split (nx_lib/views/generali/__init__.py owns these names;
    # a top-of-file import here would bind a stale copy at import time).
    from . import _generali_userids_in_org, has_permission

    if has_permission(f"{perm_prefix}.edit.all"):
        if not requested_org_code:
            return [], []
        org_scope = requested_org_code
    elif has_permission(f"{perm_prefix}.edit.org"):
        org_scope = session.get("organizationcode")
    else:
        return [f"{user_column} = ?"], [session.get("userid")]

    ids = _generali_userids_in_org(org_scope)
    if not ids:
        current_app.logger.info(
            f"Generali scope: org {org_scope!r} resolved to no users; failing closed"
        )
        return ["1=0"], []
    placeholders = ",".join(["?"] * len(ids))
    return [f"{user_column} IN ({placeholders})"], list(ids)

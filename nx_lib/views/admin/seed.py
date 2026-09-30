"""Admin: seed the INT databases with synthetic data, and clear it again.

Two buttons on the admin overview (INT only) over ``nx_lib/seed.py``: *Seed
INT data* runs a seeder and *Clear seed* deletes exactly the rows the tracked
runs wrote (``dbo.SeedRuns``). Every route 404s outside INT -- the real
collectors own these tables everywhere else -- and the module's own guard
(``seed_refusal``) is checked again before anything is written.
"""

import os

from flask import abort, jsonify, request, session
from flask_babel import gettext as _

from ... import seed as seedlib
from ...security import has_permission, require_permission

_PERMISSION = "admin.seed.manage"
_MAX_DAYS = 365


def _is_int() -> bool:
    return os.environ.get("ENVIRONMENT") == "INT"


def seed_controls_visible() -> bool:
    """Show the seed / clear buttons on the admin overview?"""
    return _is_int() and has_permission(_PERMISSION)


def _int_only() -> None:
    if not _is_int():
        abort(404)


@require_permission(_PERMISSION)
def api_admin_seed_status():
    """Tracked runs plus whether seeding may run here (and if not, why)."""
    _int_only()
    reason = seedlib.seed_refusal()
    try:
        runs = seedlib.list_runs()
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 503
    return jsonify(
        {
            "success": True,
            "allowed": reason is None,
            "reason": reason,
            "seeders": [
                {"name": s.name, "table": s.table, "doc": s.doc} for s in seedlib.SEEDERS.values()
            ],
            "runs": runs,
            "rows": sum(int(r["rows"] or 0) for r in runs),
        }
    )


@require_permission(_PERMISSION)
def api_admin_seed_run():
    """POST {"what": "backlog-history", "days": 14} -- seed and report."""
    _int_only()
    body = request.get_json(silent=True) or {}
    what = str(body.get("what") or "backlog-history")
    try:
        days = int(body.get("days") or 14)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": _("Days must be a whole number.")}), 400
    if what not in seedlib.SEEDERS:
        return jsonify({"success": False, "message": _("Unknown seeder.")}), 400
    if not 2 <= days <= _MAX_DAYS:
        return jsonify(
            {
                "success": False,
                "message": _("Days must be between %(lo)s and %(hi)s.", lo=2, hi=_MAX_DAYS),
            }
        ), 400
    try:
        report = seedlib.run_seed(what, days, apply_it=True, seeded_by=session.get("username"))
    except seedlib.SeedRefusedError as e:
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": True, "report": report.to_dict()})


@require_permission(_PERMISSION)
def api_admin_seed_clear():
    """DELETE -- remove every tracked seeded row (optionally ``?what=`` one seeder)."""
    _int_only()
    what = request.args.get("what") or None
    if what is not None and what not in seedlib.SEEDERS:
        return jsonify({"success": False, "message": _("Unknown seeder.")}), 400
    try:
        result = seedlib.clear_seeds(seeder=what)
    except seedlib.SeedRefusedError as e:
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": True, "cleared": result})


def register_routes(app):
    app.add_url_rule(
        "/api/admin/seed",
        endpoint="api_admin_seed_status",
        view_func=api_admin_seed_status,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/seed",
        endpoint="api_admin_seed_run",
        view_func=api_admin_seed_run,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/seed",
        endpoint="api_admin_seed_clear",
        view_func=api_admin_seed_clear,
        methods=["DELETE"],
    )

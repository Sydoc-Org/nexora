"""nx_main — WSGI entry point.

PROD runs ``python -m waitress ... nx_main:app`` under IIS's
HttpPlatformHandler (see web.config), so this module stays at the repo root
and exposes the Flask application via the ``nx_lib.create_app()`` factory.

All cross-cutting setup (config, DB engines, extensions, request hooks,
error handlers, security helpers, maintenance lockout) lives in the
``nx_lib/`` package. Routes are being migrated module-by-module under
``nx_lib/views/``. What is still in this file will move there in
subsequent passes.
"""

# --- stdlib ---
import os

# --- third-party ---
# --- nx_lib package ---
from nx_lib import create_app

# Build the Flask app via the package factory. All routes live in nx_lib/views/.
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_RUN_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)

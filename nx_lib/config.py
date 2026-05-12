"""Environment-driven configuration for nexora.

Loaded once at import time. Reads ``.env`` then ``{ENVIRONMENT}.env`` so
secrets in INT.env / PROD.env override anything in the default .env file.
"""

import os

from dotenv import load_dotenv


load_dotenv()
load_dotenv(dotenv_path=f'{os.environ.get("ENVIRONMENT")}.env')

IS_PROD = os.environ.get("ENVIRONMENT") == "PROD"

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER_PRD = os.environ.get("DB_SERVER_PRD")
DB_SERVER_PRD_MOBSCAN = os.environ.get("DB_SERVER_PRD_MOBSCAN")
DB_NEXORA = os.environ.get("DB_NEXORA")
DB_STATISTICS = os.environ.get("DB_STATISTICS")
DB_STATISTICS_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].{DB_STATISTICS}"
DB_OCTO_RUNTIME = os.environ.get("DB_OCTO_RUNTIME")
DB_OCTO_RUNTIME_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].{DB_OCTO_RUNTIME}"
RUNTIME_TBL_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].[{DB_OCTO_RUNTIME}].[dbo]."
DB_GENERALI = os.environ.get("DB_GENERALI", "Generali")

GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")

OCTO_CLIENT_SECRET = os.environ.get("OCTO_CLIENT_SECRET")
OCTO_CLIENT_ID = os.environ.get("OCTO_CLIENT_ID")
OCTO_CLIENT_SECRET_MOBSCN = os.environ.get("OCTO_CLIENT_SECRET_MOBSCN")
OCTO_CLIENT_ID_MOBSCN = os.environ.get("OCTO_CLIENT_ID_MOBSCN")
OCTO_GRANT_TYPE = os.environ.get("OCTO_GRANT_TYPE")
OCTO_DOMAIN = os.environ.get("OCTO_DOMAIN")
OCTO_DOMAIN_MOBSCN = os.environ.get("OCTO_DOMAIN_MOBSCN")

BEXIO_PAT = os.environ.get("BEXIO_PAT")

CSP = {
    "default-src": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",
    "script-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.tailwindcss.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "https://fonts.googleapis.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
    "font-src": [
        "'self'",
        "https://fonts.gstatic.com",
        "https://cdnjs.cloudflare.com",
    ],
    "img-src": [
        "'self'",
        "data:",
        "blob:",
        "https://cdn.tailwindcss.com",
    ],
    "connect-src": [
        "'self'",
        "https://cdn.tailwindcss.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
}

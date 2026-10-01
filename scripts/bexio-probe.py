"""Read-only check of what the configured Bexio token can reach (#423).

    .venv\\Scripts\\python.exe scripts\\bexio-probe.py [INT|STAGING|PROD]

Loads BEXIO_PAT from env/<ENV>.env the way the app does and makes a handful
of GET requests -- the ones the Finance invoice panel needs, plus the company
profile so you can see which Bexio account the token belongs to. It never
prints the token and never writes to Bexio. Exit code 0 when everything the
panel needs answers, 1 otherwise.

A read-only probe cannot tell whether the token could also *write* (create
invoices); that needs a look at the token's scopes in Bexio itself.
"""

import importlib.util
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
API = "https://api.bexio.com"

# (path, what the panel uses it for, needed by the panel?)
CHECKS = (
    ("/2.0/company_profile", "company profile (which Bexio account)", False),
    ("/2.0/kb_invoice?limit=1", "invoices: list and search", True),
    ("/2.0/contact?limit=1", "contacts: client names", True),
    ("/3.0/currencies", "currencies: CHF/EUR codes", False),
)


def load_config(env_name):
    os.environ["ENVIRONMENT"] = env_name
    spec = importlib.util.spec_from_file_location(
        "_nexora_config_for_probe", str(REPO_ROOT / "nx_lib" / "config.py")
    )
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


def main(argv):
    env_name = (argv[1] if len(argv) > 1 else "INT").upper()
    token = load_config(env_name).BEXIO_PAT
    if not token:
        print(f"[{env_name}] BEXIO_PAT is not set in env/{env_name}.env -- the panel is off.")
        return 1
    print(f"[{env_name}] BEXIO_PAT is set ({len(token)} characters). Probing, read-only:")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    ok = True
    for path, what, needed in CHECKS:
        try:
            resp = requests.get(API + path, headers=headers, timeout=15)
            status = resp.status_code
        except requests.exceptions.RequestException as e:
            status, resp = None, None
            reason = type(e).__name__
        if status == 200:
            verdict = "ok"
            if path == "/2.0/company_profile":
                body = resp.json()
                first = body[0] if isinstance(body, list) and body else body
                if isinstance(first, dict) and first.get("name"):
                    verdict = f"ok -- account: {first['name']}"
        elif status == 401:
            verdict = "401 token rejected (expired or revoked)"
        elif status == 403:
            verdict = "403 no permission (scope missing)"
        elif status is None:
            verdict = f"unreachable ({reason})"
        else:
            verdict = f"HTTP {status}"
        mark = "+" if status == 200 else ("!" if needed else "-")
        print(f"  {mark} {what:<40} {verdict}")
        if needed and status != 200:
            ok = False
    print("The invoice panel can work." if ok else "The invoice panel cannot work with this token.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

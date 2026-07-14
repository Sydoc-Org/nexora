"""Generate an external-API key: print the raw token ONCE plus the INSERT.

Dev-side only (scripts/ is excluded from the prod deploy mirror, so this
file never exists on the server). Run it, hand the token to the client over
a secure channel, then execute the printed INSERT against the target
NexoraDB (INT and/or PROD) in SSMS. The raw token is never stored
anywhere -- dbo.ApiKeys holds only its SHA-256 hex digest. The 2-line hash
below is deliberately duplicated from nx_lib/api_auth.py hash_api_key
(importing nx_lib creates DB engines at import time and requires live env
config) -- keep the two in sync.

Usage:
    python scripts/new-api-key.py --client-code default \
        --label "ACME ops dashboard" \
        --processes "sydoc.05_PDBS,compass.01_Invoice_SAP"

--processes takes full dbo.Statconfig ProcessName values (the same strings
the dashboard's dashboard.filter.process.* permission codes resolve to);
list candidates with: SELECT ProcessName FROM dbo.Statconfig.
"""

import argparse
import hashlib
import secrets


def _sq(value):
    """Escape a value for embedding in the printed T-SQL string literal."""
    return str(value).replace("'", "''")


def main():
    ap = argparse.ArgumentParser(
        description="Generate an external-API key + the dbo.ApiKeys INSERT."
    )
    ap.add_argument("--client-code", required=True, help="e.g. 'default' or 'ms02'")
    ap.add_argument("--label", required=True, help="who holds this key (audit note)")
    ap.add_argument(
        "--processes",
        required=True,
        help="comma-separated full Statconfig ProcessName values",
    )
    args = ap.parse_args()

    token = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    processes = ",".join(p.strip() for p in args.processes.split(",") if p.strip())

    print("Raw API key -- hand to the client ONCE, it is not recoverable:\n")
    print(f"    {token}\n")
    print("Run this against the target NexoraDB (SSMS, INT and/or PROD):\n")
    print("INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList, Enabled)")
    print(
        f"VALUES ('{key_hash}', '{_sq(args.client_code)}', '{_sq(args.label)}', "
        f"'{_sq(processes)}', 1);"
    )


if __name__ == "__main__":
    main()

"""Derive env/STAGING.env from env/PROD.env without anyone reading secrets.

    python scripts/make-staging-env.py          # writes env/STAGING.env (refuses to overwrite)
    python scripts/make-staging-env.py --force

Swaps the two app-owned DB names to their *_STAGING copies (#338), sets
ENVIRONMENT=STAGING and mints a fresh FLASK_SECRET_KEY so staging cookies
can never be replayed against PROD. Everything else is copied verbatim.
"""

import argparse
import re
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / "env"
SWAP = {
    "ENVIRONMENT": "STAGING",
    "DB_NEXORA": "nexora_STAGING",
    "DB_GENERALI": "Generali_STAGING",
    "FLASK_SECRET_KEY": None,  # minted below
}


def _value(key):
    return SWAP[key] if SWAP[key] is not None else secrets.token_urlsafe(48)


def derive(prod_text):
    out, seen = [], set()
    for line in prod_text.splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        key = m.group(1) if m else None
        if key in SWAP:
            seen.add(key)
            line = f"{key}={_value(key)}"
        out.append(line)
    # PROD.env may lack DB_GENERALI (config.py defaults it to Generali)
    out.extend(f"{key}={_value(key)}" for key in sorted(SWAP.keys() - seen))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    dst = ENV / "STAGING.env"
    if dst.exists() and not a.force:
        raise SystemExit(f"{dst} exists; pass --force to overwrite")
    dst.write_text(derive((ENV / "PROD.env").read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {dst}")

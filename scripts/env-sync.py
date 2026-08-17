"""Compare the gitignored env files in this checkout against PROD on SYAPP01.

Env files hold live credentials, so they are gitignored and never deployed
(`deploy.yml` excludes `*.env` from the robocopy mirror). That means adding a new
setting to the repo -- as a key in the committed `env/PROD.env.example` -- does
nothing on the server until someone edits `D:\\sydoc\\nexora\\env\\PROD.env` by
hand, and forgetting is silent. `SUPPORT_MAIL` (issue #166) is the reference
case: the outage monitor runs, probes everything, logs happily, and never mails.

So the useful check is three-way:

* **example** -- `env/PROD.env.example`, committed, therefore the authoritative
  list of keys that *should* exist. A key here but missing on the server is the
  "forgot to add it when deploying" bug.
* **local** -- `env/PROD.env` in this checkout.
* **server** -- `\\\\syapp01\\d$\\sydoc\\nexora\\env\\PROD.env`.

Run it by hand once per deploy that touched an env key -- right before or right
after. It is deliberately not automated and not a hook: it reports, you decide.

What it will and will not complain about:

* A key the example declares but the server lacks is **actionable** and sets the
  exit code. That is a shape problem, and the answer is always "add the key".
* A key set on both sides with **different values** is only ever informational.
  Dev and PROD hold different credentials and endpoints, and PROD legitimately
  lags dev until the matching deploy lands, so failing on that would cry wolf
  every run. The script shows the difference; judging it is your call.

Values are masked by default: this prints a short fingerprint per side, enough
to see that two secrets differ without pasting credentials into a terminal
(or an AI transcript). Pass --show-values when you actually need to read them.

Usage:
    python scripts/env-sync.py                    # report drift, exit 1 if any
    python scripts/env-sync.py --show-values      # same, secrets revealed
    python scripts/env-sync.py --push PROD.env    # local  -> server
    python scripts/env-sync.py --pull PROD.env    # server -> local
    python scripts/env-sync.py --push PROD.env --yes   # no prompt

Both copy directions back the destination up first. Do not skip that: the
`sqlbackuper` outage came from copying a stale dev .env over a working server
one, twice.
"""

import argparse
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV_DIR = REPO_ROOT / "env"
REMOTE_ENV_DIR = Path(r"\\syapp01\d$\sydoc\nexora\env")

# Only these live on the server. INT/STAGING/TEST are dev-side, so their absence
# there is correct, not drift.
MANAGED = ("PROD.env", "CONFLUENCE.env")


def fingerprint(value):
    """Short, stable digest of a secret -- comparable without being readable."""
    if value is None:
        return "-"
    if value == "":
        return "(empty)"
    return f"#{hashlib.sha1(value.encode('utf-8')).hexdigest()[:6]}"


def read_env(path):
    """Parse a .env into a dict, or None if it is not there."""
    if not path.exists():
        return None
    return dict(dotenv_values(path))


def _required(example, keys):
    """Split keys by whether the example ships a real default for them.

    A key the example leaves blank (`ANTHROPIC_API_KEY=`) is opt-in: absent on
    the server is the normal state, not a bug. A key with an actual value
    (`SUPPORT_MAIL=support.helpdesk@sydoc.ch`) is something the repo expects to
    be set. Without this split the one line that matters drowns in twenty that
    do not -- which is how the original omission went unnoticed in the first
    place.
    """
    ex = example or {}
    req = sorted(k for k in keys if (ex.get(k) or "").strip())
    opt = sorted(k for k in keys if not (ex.get(k) or "").strip())
    return req, opt


def diff_envs(example, local, remote):
    """Compare three key/value maps (any may be None for "file absent").

    Returns a dict of finding-name -> sorted keys. Kept pure so the interesting
    logic is testable without a live SYAPP01 share.
    """
    ex = set(example or {})
    lo = set(local or {})
    re_ = set(remote or {})

    # The "forgot it when deploying" bug: the repo declares the key, the server
    # has never heard of it.
    srv_req, srv_opt = _required(example, ex - re_) if remote is not None else ([], [])
    loc_req, loc_opt = _required(example, ex - lo) if local is not None else ([], [])

    return {
        "missing_on_server": srv_req,
        "missing_on_server_optional": srv_opt,
        "missing_locally": loc_req,
        "missing_locally_optional": loc_opt,
        # Set on both sides but not the same value.
        "value_differs": sorted(
            k for k in (lo & re_) if (local or {}).get(k) != (remote or {}).get(k)
        ),
        # On the server but not declared anywhere in the repo -- either an
        # undocumented setting or a leftover.
        "undeclared_on_server": sorted(re_ - ex) if remote is not None else [],
    }


def _fmt_key(key, local, remote, show_values):
    lv = (local or {}).get(key)
    rv = (remote or {}).get(key)
    if show_values:
        return f"local={lv!r} server={rv!r}"
    return f"local={fingerprint(lv)} server={fingerprint(rv)}"


def report(name, show_values, verbose=False):
    """Print the three-way comparison for one env file. True if drift found."""
    example = read_env(LOCAL_ENV_DIR / f"{name}.example")
    local = read_env(LOCAL_ENV_DIR / name)
    remote = read_env(REMOTE_ENV_DIR / name)

    print(f"\n=== {name} ===")
    if local is None:
        print(f"  local  : ABSENT ({LOCAL_ENV_DIR / name})")
    if remote is None:
        print(f"  server : ABSENT ({REMOTE_ENV_DIR / name})")
    if example is None:
        print(f"  note   : no committed {name}.example, cannot check for missing keys")

    f = diff_envs(example, local, remote)

    if f["missing_on_server"]:
        print(
            f"  [!] ACTION NEEDED -- {name}.example declares these but the server "
            f"has no such key ({len(f['missing_on_server'])}).\n"
            f"      Paste onto {REMOTE_ENV_DIR / name} (values are the committed "
            f"defaults; edit if PROD differs):"
        )
        for k in f["missing_on_server"]:
            # The example is committed, so its defaults are never secret.
            ex_val = str((example or {}).get(k) or "")
            shown = ex_val if len(ex_val) <= 60 else ex_val[:57] + "..."
            print(f"        {k}={shown}")
    if f["missing_on_server_optional"] and verbose:
        print(
            f"  [ ] opt-in keys (blank in {name}.example) absent on server "
            f"({len(f['missing_on_server_optional'])}):"
        )
        for k in f["missing_on_server_optional"]:
            print(f"        {k}")
    elif f["missing_on_server_optional"]:
        print(
            f"  [ ] {len(f['missing_on_server_optional'])} opt-in key(s) absent on server "
            f"(blank in the example -- normal; --verbose to list)"
        )
    if f["missing_locally"]:
        print(
            f"  [ ] {name}.example ships a value but it is not set locally "
            f"({len(f['missing_locally'])}):"
        )
        for k in f["missing_locally"]:
            print(f"        {k}")
    if f["missing_locally_optional"] and verbose:
        print(f"  [ ] opt-in keys absent locally ({len(f['missing_locally_optional'])}):")
        for k in f["missing_locally_optional"]:
            print(f"        {k}")
    if f["value_differs"]:
        print(
            f"  [~] FYI -- set on both sides with different values "
            f"({len(f['value_differs'])}). Usually correct: dev and PROD hold "
            f"different credentials and endpoints, and PROD legitimately lags\n"
            f"      dev until the matching deploy lands. Judgement call:"
        )
        for k in f["value_differs"]:
            print(f"        {k:<28} {_fmt_key(k, local, remote, show_values)}")
    if f["undeclared_on_server"]:
        print(f"  [ ] on server but not in {name}.example ({len(f['undeclared_on_server'])}):")
        for k in f["undeclared_on_server"]:
            print(f"        {k}")

    # Only a key the server has never heard of drives the exit code. A differing
    # *value* is the normal state -- dev and PROD hold different secrets, and
    # PROD deliberately lags dev until its deploy lands -- so failing on that
    # would cry wolf on every run and stop the script being worth running. The
    # shape of the file is checkable; whether a value is right is a human call.
    drift = bool(f["missing_on_server"])
    if not drift and local is not None and remote is not None:
        print("  no missing keys")
    return drift


def copy_with_backup(src, dst, assume_yes):
    """Copy src over dst, backing dst up first. Returns True if it happened."""
    if not src.exists():
        print(f"[error] source does not exist: {src}")
        return False
    if not dst.parent.exists():
        print(f"[error] destination directory unreachable: {dst.parent}")
        return False

    print(f"\nAbout to overwrite:\n  {dst}\nwith:\n  {src}")
    if dst.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = dst.with_name(f"{dst.name}.bak-{stamp}")
        shutil.copy2(dst, backup)
        print(f"backup written: {backup}")
    else:
        print("(destination does not exist yet -- nothing to back up)")

    if not assume_yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("aborted")
            return False

    shutil.copy2(src, dst)
    print(f"copied -> {dst}")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Compare (and optionally sync) env files against PROD on SYAPP01."
    )
    ap.add_argument("--show-values", action="store_true", help="print secrets, not fingerprints")
    ap.add_argument(
        "--verbose", action="store_true", help="also list opt-in keys that are blank in the example"
    )
    ap.add_argument("--push", metavar="FILE", help=f"copy local -> server ({', '.join(MANAGED)})")
    ap.add_argument("--pull", metavar="FILE", help="copy server -> local")
    ap.add_argument("--yes", action="store_true", help="do not prompt before overwriting")
    args = ap.parse_args()

    if args.push and args.pull:
        ap.error("--push and --pull are mutually exclusive")

    if not REMOTE_ENV_DIR.exists():
        print(f"[error] cannot reach {REMOTE_ENV_DIR}")
        print("        Need the SYAPP01 admin share (VPN / domain credentials).")
        return 2

    if args.push or args.pull:
        name = args.push or args.pull
        if name not in MANAGED:
            ap.error(f"{name} is not managed on the server; expected one of {MANAGED}")
        if args.push:
            ok = copy_with_backup(LOCAL_ENV_DIR / name, REMOTE_ENV_DIR / name, args.yes)
        else:
            ok = copy_with_backup(REMOTE_ENV_DIR / name, LOCAL_ENV_DIR / name, args.yes)
        if not ok:
            return 1
        report(name, args.show_values, args.verbose)
        return 0

    drift = False
    for name in MANAGED:
        drift |= report(name, args.show_values, args.verbose)

    print()
    if drift:
        print("Keys are missing on the server (see ACTION NEEDED above).")
        print("Best fix is pasting those lines into the server file by hand: pushing")
        print("the whole file also overwrites server-only values and any PROD setting")
        print("that is deliberately different from dev. If you do want the whole file:")
        print("  python scripts/env-sync.py --push PROD.env   # local  -> server")
        print("  python scripts/env-sync.py --pull PROD.env   # server -> local")
        return 1
    print("No keys missing on the server. Any [~] value differences above are")
    print("informational -- dev and PROD are expected to diverge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

* A key the example declares but the server lacks is **actionable** -- but only
  when the code has no default for it. That is the `SUPPORT_MAIL` shape, and
  the answer is "add the key". If the code *does* default the key, its absence
  changes nothing, so it is reported quietly instead (issue #313: this alarm
  once fired 11 times and was wrong 11 times, which is how you teach people to
  skim past it). Defaults are read out of the source with `ast`, not guessed
  -- see `code_defaults()`.
* A key the code defaults to something **other** than what the example ships is
  its own warning: the server is silently running on a value the repo does not
  advertise. Fix goes either direction -- set the key, or correct the example.
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
import ast
import functools
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


# Python trees to scan for env defaults. Templates and generated SQL never read
# the environment. tests/ is deliberately out: a default that only exists in a
# fixture is not a default in production.
CODE_ROOTS = ("nx_lib", "ops", "scripts")

# Sentinel for "this read site supplied no default". None cannot double as the
# marker, because `os.environ.get(k, None)` is a real (if pointless) default.
NO_DEFAULT = object()


def _literal(node):
    """The constant a node evaluates to, or NO_DEFAULT if it is not constant."""
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return NO_DEFAULT
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return NO_DEFAULT


def _is_env_read(func):
    """True for `os.environ.get(...)` / `os.getenv(...)`, whatever the alias."""
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "getenv":
        return True
    return (
        func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
    )


def _defaults_in_source(source, filename):
    """key -> one entry per read site in this file.

    Each entry is a literal, an ("alias", other_key) pair, or NO_DEFAULT.
    Anything the scan cannot read exactly becomes NO_DEFAULT, which errs
    toward calling a key actionable rather than waving it through.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return {}

    # `os.environ.get("K") or 120` -- the call passes no default but the
    # surrounding expression supplies one. Collect those first, keyed by node.
    or_defaults = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        if len(node.values) != 2:
            continue
        left, right = node.values
        if isinstance(left, ast.Call) and _is_env_read(left.func):
            fallback = _literal(right)
            if fallback is not NO_DEFAULT:
                or_defaults[id(left)] = fallback

    # Module-level `NAME = os.environ.get("OTHER", ...)`, so that a default
    # which is a bare Name can be followed: MS02_STATS_DB_PORT defaults to
    # MS02_DB_PORT, which is itself an env read.
    aliases = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        value = node.value
        if not isinstance(target, ast.Name):
            continue
        if isinstance(value, ast.Call) and _is_env_read(value.func) and value.args:
            key = _literal(value.args[0])
            if isinstance(key, str):
                aliases[target.id] = key

    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_env_read(node.func) and node.args:
            key = _literal(node.args[0])
            if not isinstance(key, str):
                continue
            if len(node.args) > 1:
                arg = node.args[1]
                if isinstance(arg, ast.Name) and arg.id in aliases:
                    default = ("alias", aliases[arg.id])
                else:
                    default = _literal(arg)
            else:
                default = or_defaults.get(id(node), NO_DEFAULT)
            found.setdefault(key, []).append(default)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            # `os.environ["K"]` raises when the key is absent, so by
            # definition it has no default.
            if node.value.attr == "environ":
                key = _literal(node.slice)
                if isinstance(key, str):
                    found.setdefault(key, []).append(NO_DEFAULT)
    return found


@functools.cache
def code_defaults(repo_root=REPO_ROOT):
    """Env key -> its code default, for keys that are defaulted *everywhere*.

    A key read in two places, one of which passes no default, is not treated as
    defaulted: that call site still gets None, so the key genuinely matters.
    Two different literal defaults for one key are handled the same way --
    ambiguous is not safe. Keys with no default never enter the result, which
    is exactly what keeps them actionable.
    """
    per_key = {}
    files = []
    for name in CODE_ROOTS:
        root = repo_root / name
        if root.is_dir():
            files += [p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]
    files += sorted(repo_root.glob("*.py"))

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for key, defaults in _defaults_in_source(source, str(path)).items():
            per_key.setdefault(key, []).extend(defaults)

    resolved = {}
    for key, defaults in per_key.items():
        if any(d is NO_DEFAULT for d in defaults):
            continue
        if len({repr(d) for d in defaults}) != 1:
            continue
        resolved[key] = defaults[0]
    return resolved


def resolve_default(key, defaults, remote, _seen=None):
    """What the code falls back to for `key`, as the string env would hold.

    An alias resolves against the server file first -- MS02_STATS_DB_PORT
    inherits whatever MS02_DB_PORT actually is there -- and only then against
    that key's own default. Pinning it to the literal instead would give the
    wrong answer the moment someone sets the base key on the server.
    """
    seen = set() if _seen is None else _seen
    if key in seen or key not in defaults:
        return None
    seen.add(key)

    default = defaults[key]
    if isinstance(default, tuple) and len(default) == 2 and default[0] == "alias":
        target = default[1]
        server_value = (remote or {}).get(target)
        if server_value is not None:
            return server_value
        return resolve_default(target, defaults, remote, seen)
    if default is None:
        return None
    return str(default)


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


def diff_envs(example, local, remote, defaults=None):
    """Compare three key/value maps (any may be None for "file absent").

    Returns a dict of finding-name -> sorted keys. Kept pure so the interesting
    logic is testable without a live SYAPP01 share -- `defaults` is passed in
    (from `code_defaults()`) rather than scanned here, so this function still
    touches no disk. Omit it and nothing is treated as defaulted, which is the
    old behaviour.
    """
    ex = set(example or {})
    lo = set(local or {})
    re_ = set(remote or {})

    # The "forgot it when deploying" bug: the repo declares the key, the server
    # has never heard of it.
    srv_req, srv_opt = _required(example, ex - re_) if remote is not None else ([], [])
    loc_req, loc_opt = _required(example, ex - lo) if local is not None else ([], [])

    # ...except when the code defaults the key, in which case its absence from
    # the server changes nothing and calling it ACTION NEEDED is a lie (#313).
    defaults = defaults or {}
    actionable, defaulted, mismatched = [], [], []
    for key in srv_req:
        if key not in defaults:
            actionable.append(key)
            continue
        fallback = resolve_default(key, defaults, remote)
        advertised = str((example or {}).get(key) or "")
        if fallback is not None and fallback.strip() == advertised.strip():
            defaulted.append(key)
        else:
            mismatched.append(key)

    return {
        "missing_on_server": actionable,
        "missing_on_server_defaulted": defaulted,
        "missing_on_server_default_differs": mismatched,
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

    defaults = code_defaults()
    f = diff_envs(example, local, remote, defaults)

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
    if f["missing_on_server_default_differs"]:
        print(
            f"  [!] {name}.example advertises a value the code does not fall back to "
            f"({len(f['missing_on_server_default_differs'])}). The key is absent on\n"
            f"      the server, so PROD runs on the code default, not on what the repo\n"
            f"      says. Fix either side -- add the key, or correct the example:"
        )
        for k in f["missing_on_server_default_differs"]:
            ex_val = str((example or {}).get(k) or "")
            actual = resolve_default(k, defaults, remote)
            print(f"        {k:<28} example={ex_val!r}  code falls back to={actual!r}")
    if f["missing_on_server_defaulted"]:
        print(
            f"  [ ] {len(f['missing_on_server_defaulted'])} key(s) absent on server but "
            f"defaulted in code to exactly what the example ships -- nothing to do"
            f"{'' if verbose else ' (--verbose to list)'}:"
        )
        if verbose:
            for k in f["missing_on_server_defaulted"]:
                actual = resolve_default(k, defaults, remote)
                print(f"        {k:<28} code default={actual!r}")
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
    # A defaulted key is deliberately *not* drift: the server behaves exactly as
    # the repo describes without it, so failing on it is the cry-wolf that made
    # this alarm worthless (#313). A key whose code default contradicts the
    # example is drift, because somebody has to reconcile the two.
    drift = bool(f["missing_on_server"] or f["missing_on_server_default_differs"])
    if not drift and local is not None and remote is not None:
        print("  no keys missing that the code does not already default")
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
        print("Keys are missing on the server that the code does not default,")
        print("or default to something the example contradicts (see above).")
        print("Best fix is pasting those lines into the server file by hand: pushing")
        print("the whole file also overwrites server-only values and any PROD setting")
        print("that is deliberately different from dev. If you do want the whole file:")
        print("  python scripts/env-sync.py --push PROD.env   # local  -> server")
        print("  python scripts/env-sync.py --pull PROD.env   # server -> local")
        return 1
    print("Nothing actionable. Any [~] value differences above are informational")
    print("-- dev and PROD are expected to diverge -- and any key listed as")
    print("defaulted in code is absent on the server on purpose: it behaves")
    print("identically either way.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

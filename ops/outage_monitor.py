"""PROD outage detector (driven by Windows Task Scheduler).

Runs *outside* the Flask process on purpose: an in-app scheduler cannot report
that the app is dead, which is exactly the case this exists to catch. Probes the
databases, the public site, the external API, the Octo runtime API and the
application log, folds
each result through ``nx_lib.outage``'s hysteresis, and mails
``SUPPORT_MAIL`` when a component opens or recovers.

Background (issue #166): migration 0042 reached PROD ahead of its code and broke
the workitems list for ~half a day. Every DB ping stayed green -- the only
evidence was an `Invalid object name` storm in var/logs/system/app.log that
nobody was watching. Hence the log-storm probe alongside the connectivity ones.

Wiring (PROD): a Task Scheduler task running every 5 minutes:

    set ENVIRONMENT=PROD
    D:\\sydoc\\tools\\py\\python.exe D:\\sydoc\\nexora\\ops\\outage_monitor.py

Flags:
    --dry-run    run every probe and print what would be mailed; sends nothing
                 and does not persist state
    --check      print the current state file and exit (no probes)
"""

import argparse
import os
import sys
from datetime import UTC, datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nx_lib import outage
from nx_lib import status as status_lib
from nx_lib.config import PATHS, VAR_DIR

# Probe timeouts. Generous enough that a merely-slow PROD does not read as down,
# tight enough that one wedged component cannot stall the whole run.
_DB_TIMEOUT_S = 5.0
_HTTP_TIMEOUT_S = 15
_OCTO_TIMEOUT_S = 15

STATE_PATH = VAR_DIR / "outage-state.json"
APP_LOG = PATHS.logs / "system" / "app.log"

# A slower fail threshold for the HTTP probe: an IIS app-pool recycle can drop a
# single request without anything actually being wrong.
# The API probes ride the same IIS app pool, so they inherit the same slack.
_FAIL_THRESHOLDS = {"http:site": 3, "api:v1": 3, "api:key": 3}
# Log storms carry their own N-errors-in-M-minutes hysteresis, so one sighting
# is already strong evidence -- waiting for a second poll only delays the mail.
_STORM_FAIL_THRESHOLD = 1


def _probe_dbs():
    """Ping every configured engine. Yields ``(component, ok, detail)``."""
    from nx_lib.db import (
        engine_generali_db,
        engine_ms02_docfields_pg,
        engine_ms02_pg,
        engine_ms02_stats_pg,
        engine_nexora_db,
        engine_octo_db,
        engine_statistics_db,
        ping_dbs_parallel,
    )

    targets = [
        (engine_nexora_db, "NexoraDB"),
        (engine_octo_db, "OctoDB"),
        (engine_statistics_db, "StatisticsDB"),
        (engine_generali_db, "GeneraliDB"),
        *([(engine_ms02_pg, "MS02 (PG)")] if engine_ms02_pg is not None else []),
        *([(engine_ms02_stats_pg, "MS02 stats (PG)")] if engine_ms02_stats_pg is not None else []),
        *(
            [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
            if engine_ms02_docfields_pg is not None
            else []
        ),
    ]
    for ping in ping_dbs_parallel(targets, timeout_s=_DB_TIMEOUT_S):
        detail = (
            f"{ping['latency_ms']} ms"
            if ping["ok"]
            else f"{ping['error']} ({ping['latency_ms']} ms)"
        )
        yield f"db:{ping['label']}", ping["ok"], detail


def _took(resp):
    """Render a response's duration as " (204 ms)" -- requests already timed it.

    The DB pings have carried their duration in the detail line from the start;
    the HTTP probes did not, which left the status page's sparklines (migration
    0071) blind to exactly the components most likely to get slow before they
    get broken.
    """
    return f" ({int(resp.elapsed.total_seconds() * 1000)} ms)"


def _probe_http(url):
    """GET the public site. Catches IIS / app-pool death that DB pings cannot."""
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT_S, allow_redirects=True)
    except requests.RequestException as e:
        return "http:site", False, f"{url}: {type(e).__name__}: {str(e)[:160]}"
    # Any 2xx/3xx means IIS served the app. A login redirect is a healthy answer.
    if resp.headers.get(outage.MAINTENANCE_HEADER):
        # Deliberate window, not a dead site (#281). ok=None freezes the
        # component rather than opening an incident; see update_component.
        retry = resp.headers.get("Retry-After")
        until = f", ends in {retry}s" if retry else ""
        return "http:site", None, f"{url}: planned maintenance{until}"
    ok = resp.status_code < 400
    return "http:site", ok, f"{url}: HTTP {resp.status_code}{_took(resp)}"


def _probe_api(site_url):
    """GET an /api/v1 route with no Authorization header. 401 is the pass.

    ``http:site`` only proves IIS served a *page*. The external API is a second
    entry point with its own auth module, and it can break on its own (a bad
    rewrite rule, an import error in api_auth) while every page still renders.
    A 401 means the request reached ``require_api_key`` and it answered -- the
    strongest signal available without holding a key.
    """
    url = f"{site_url.rstrip('/')}/api/v1/stats/today"
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT_S)
    except requests.RequestException as e:
        return "api:v1", False, f"{url}: {type(e).__name__}: {str(e)[:160]}"
    ok = resp.status_code == 401
    return "api:v1", ok, f"{url}: HTTP {resp.status_code}{_took(resp)}"


def _probe_api_key(site_url):
    """Call the /api/test/v1 twin with a real key: the full auth path, no backend.

    Where ``api:v1`` stops at "the 401 branch works", this one exercises the
    dbo.ApiKeys lookup and the key's process scope end to end. It deliberately
    targets the *test* twin (fake data, same auth) so a monitor poll never
    touches the Statistics/Octo backends every 5 minutes.

    Returns None when OUTAGE_API_KEY is unset -- same graceful skip as the Graph
    probe, so the code can land before the key exists on a server.
    """
    from nx_lib.config import OUTAGE_API_KEY

    if not OUTAGE_API_KEY:
        return None
    url = f"{site_url.rstrip('/')}/api/test/v1/stats/today"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {OUTAGE_API_KEY}"},
            timeout=_HTTP_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return "api:key", False, f"{url}: {type(e).__name__}: {str(e)[:160]}"
    ok = resp.status_code == 200 and "imported_today" in resp.text
    return "api:key", ok, f"{url}: HTTP {resp.status_code}{_took(resp)}"


def _probe_octo(domain):
    """Hit the Octo token endpoint directly.

    Deliberately *not* nx_lib.octo.get_access_token: that memoises the token in
    the Flask cache, so a monitor calling it would report a cached success while
    the vendor is down -- a probe must always touch the network.
    """
    from nx_lib.config import OCTO_CLIENT_ID, OCTO_CLIENT_SECRET, OCTO_GRANT_TYPE

    component = f"octo:{domain}"
    url = f"https://{domain}/auth/connect/token"
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": OCTO_GRANT_TYPE,
                "client_id": OCTO_CLIENT_ID,
                "client_secret": OCTO_CLIENT_SECRET,
            },
            timeout=_OCTO_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return component, False, f"{url}: {type(e).__name__}: {str(e)[:160]}"
    ok = resp.status_code == 200 and "access_token" in resp.text
    return component, ok, f"{url}: HTTP {resp.status_code}{_took(resp)}"


def _probe_graph():
    """Acquire a Graph token the way nx_lib.mail does, without sending anything.

    Same ROPC call as ``nx_lib.mail._acquire_token`` -- a probe that actually
    sent a message would spam the mailbox every 5 minutes, and a token failure
    is what kills alert mail anyway. Returns None when Graph is not configured.
    """
    from nx_lib.config import (
        GRAPH_CLIENT_ID,
        GRAPH_CLIENT_SECRET,
        GRAPH_PASSWORD,
        GRAPH_TENANT_ID,
        GRAPH_USERNAME,
    )

    if not GRAPH_TENANT_ID:
        return None
    url = f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token"
    try:
        resp = requests.post(
            url,
            data={
                "client_id": GRAPH_CLIENT_ID or "",
                "scope": "https://graph.microsoft.com/.default",
                "username": GRAPH_USERNAME or "",
                "password": GRAPH_PASSWORD or "",
                "client_secret": GRAPH_CLIENT_SECRET or "",
                "grant_type": "password",
            },
            timeout=_HTTP_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return "graph:mail", False, f"token: {type(e).__name__}: {str(e)[:160]}"
    ok = resp.ok and "access_token" in resp.text
    return "graph:mail", ok, f"token: HTTP {resp.status_code}{_took(resp)}"


def _probe_log_storms(now_local):
    """Scan the app log for a repeating ERROR signature.

    The only probe that catches logic-level breakage while every connectivity
    check stays green -- issue #166's reference case.
    """
    text = outage.tail_text(APP_LOG)
    return outage.detect_error_storms(text, now_local)


def _collect(config):
    """Run every probe. Returns ``[(key, label, ok, detail, excerpt)]``.

    ``key`` is the stable state/dedupe id; ``label`` is what a human reads in
    the mail subject. They differ only for log storms, whose key is a hash.
    """
    results = []
    for key, ok, detail in _probe_dbs():
        results.append((key, key, ok, detail, None))
    http_key, http_ok, http_detail = _probe_http(config["site_url"])
    results.append((http_key, http_key, http_ok, http_detail, None))
    apiv1_key, api_ok, api_detail = _probe_api(config["site_url"])
    results.append((apiv1_key, apiv1_key, api_ok, api_detail, None))
    probed = _probe_api_key(config["site_url"])  # None when no key is configured
    if probed:
        key, ok, detail = probed
        results.append((key, key, ok, detail, None))
    if config["octo_domain"]:
        octo_key, octo_ok, octo_detail = _probe_octo(config["octo_domain"])
        results.append((octo_key, octo_key, octo_ok, octo_detail, None))
    # Graph only. The Bexio probe went with the archived invoices page (#177) --
    # nothing in the app calls Bexio any more, so an alert on it woke someone for
    # a vendor no page depends on.
    probed = _probe_graph()  # None when Graph is not configured for this env
    if probed:
        key, ok, detail = probed
        results.append((key, key, ok, detail, None))

    storms = _probe_log_storms(config["now_local"])
    results.extend(
        (
            storm["key"],
            storm["label"],
            False,
            f"{storm['count']}x in {outage.DEFAULT_STORM_WINDOW_MIN} min: "
            f"{storm['signature'][:160]}",
            storm["sample"],
        )
        for storm in storms
    )
    # A storm key that was open and is no longer in the scan window has stopped
    # -- feed it an explicit ok so the incident can recover instead of hanging
    # open forever.
    seen = {s["key"] for s in storms}
    for key, comp in (config["state"].get("components") or {}).items():
        if key.startswith("log:") and key not in seen and comp.get("open_since"):
            results.append((key, comp.get("label") or key, True, "no further occurrences", None))
    return results


def run_once(dry_run=False):
    now = datetime.now(UTC)
    now_local = datetime.now()  # app.log asctime is naive local time
    environment = os.environ.get("ENVIRONMENT", "?")

    from nx_lib.config import OCTO_DOMAIN, OUTAGE_SITE_URL, SUPPORT_MAIL

    support_mail = SUPPORT_MAIL
    site_url = OUTAGE_SITE_URL

    state = outage.load_state(STATE_PATH)
    results = _collect(
        {
            "site_url": site_url,
            "octo_domain": OCTO_DOMAIN,
            "now_local": now_local,
            "state": state,
        }
    )

    components = dict(state.get("components") or {})
    events = []
    snapshots = []
    db_events = []
    for key, label, ok, detail, excerpt in results:
        threshold = _FAIL_THRESHOLDS.get(
            key,
            _STORM_FAIL_THRESHOLD if key.startswith("log:") else outage.DEFAULT_FAIL_THRESHOLD,
        )
        new_state, event = outage.update_component(
            components.get(key), ok, detail, now, fail_threshold=threshold
        )
        # Carry the display label in state so a recovery mail can still name a
        # storm whose log lines have already aged out of the scan window.
        new_state["label"] = label
        components[key] = new_state
        status = "ok" if ok else "FAIL"
        print(f"  {status:>4}  {label}: {detail}")
        # Log-storm keys are content hashes, so they stay out of the component
        # grid and surface as incidents only (migration 0055).
        if not key.startswith("log:"):
            snapshots.append(
                {
                    "key": key,
                    "name": label,
                    "state": status_lib.component_state(new_state),
                    "detail": detail,
                    "ok": ok,
                }
            )
        if event:
            events.append(
                {
                    "component": label,
                    "kind": event,
                    "first_seen": new_state.get("first_fail_at") or new_state.get("open_since"),
                    "detail": detail,
                    "excerpt": excerpt,
                }
            )
            db_events.append(
                {
                    "key": key,
                    "name": label,
                    "kind": event,
                    "started_at": (
                        datetime.fromisoformat(new_state["open_since"])
                        if new_state.get("open_since")
                        else now  # a recover event: only EndedAt is written
                    ),
                    "detail": detail,
                    "excerpt": excerpt,
                }
            )

    state = outage.prune_state({**state, "components": components}, now)

    if not dry_run:
        # Best-effort mirror for the admin status page (#167). Wrapped because
        # NexoraDB being down is one of the things this monitor exists to
        # report -- a write failure here must not cost the alert mail below.
        try:
            from nx_lib.db import engine_nexora_db

            status_lib.persist_run(engine_nexora_db, snapshots, db_events, now)
        except Exception as e:
            print(f"[warn] status mirror write failed: {e}")

    sent = 0
    throttled = 0
    for kind in ("open", "recover"):
        batch = [e for e in events if e["kind"] == kind]
        if not batch:
            continue
        # Budget check before rendering the mail, and before the dry-run branch,
        # so --dry-run reports what the cap would actually do.
        allowed, suppressed, state["mail"] = outage.mail_budget(state.get("mail"), now)
        subject, body = outage.render_alert(batch, environment, now, suppressed=suppressed)
        if not allowed:
            throttled += 1
            print(f"[throttled] mail cap reached -- not mailing: {subject}")
            continue
        if dry_run:
            print(f"[dry-run] would mail {support_mail or '<SUPPORT_MAIL unset>'}: {subject}")
            continue
        if not support_mail:
            print(f"[warn] SUPPORT_MAIL unset -- not mailing: {subject}")
            continue
        from nx_lib.mail import send_mail

        try:
            send_mail(support_mail, subject, body)
            sent += 1
            print(f"[mail] {subject} -> {support_mail}")
        except Exception as e:  # a mail failure must not lose the state update
            print(f"[error] alert mail failed ({subject}): {e}")

    if not dry_run:
        outage.save_state(STATE_PATH, state)
    open_now = [k for k, c in state["components"].items() if c.get("open_since")]
    pending = (state.get("mail") or {}).get("suppressed", 0)
    print(
        f"outage monitor: {len(results)} probes, {len(events)} event(s), "
        f"{sent} mail(s), {throttled} throttled, {len(open_now)} incident(s) open"
        + (f", {pending} suppressed awaiting report" if pending else "")
    )
    return len(open_now)


def main():
    ap = argparse.ArgumentParser(description="Probe PROD and mail support on breach.")
    ap.add_argument("--dry-run", action="store_true", help="probe + print; no mail, no state write")
    ap.add_argument("--check", action="store_true", help="print current state file and exit")
    args = ap.parse_args()
    if args.check:
        state = outage.load_state(STATE_PATH)
        for key, comp in sorted(state.get("components", {}).items()):
            flag = "OPEN " if comp.get("open_since") else "ok   "
            label = comp.get("label") or key
            print(f"{flag} {label}: {comp.get('last_detail')} (updated {comp.get('updated_at')})")
        return 0
    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    # Exit 0 even with incidents open: the alert is the mail, and a non-zero
    # exit would just make Task Scheduler show a permanently failing task.
    main()
    sys.exit(0)

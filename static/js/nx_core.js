/*
 * nx_core.js -- shared front-end helper surface for nexora.
 *
 * Additive only (issue: beautify-phase-0-1, Task 9). Nothing consumes this
 * yet -- later tasks migrate the many near-identical copies of these
 * helpers scattered across templates/js/** and static/js/** onto window.NX.
 * Load this script FIRST (before any other script include) so window.NX
 * and window.API_PREFIX are always available to everything that follows.
 *
 * No Jinja syntax here -- this file is served as a static asset and is
 * covered by the same lint that bans Jinja in static/js/*.js. Translated
 * strings stay in the Jinja-rendered <script nonce> shims and get read off
 * `window`; this file only deals in DOM/plain-JS primitives.
 */
(function (window, document) {
    'use strict';

    // ---- API_PREFIX --------------------------------------------------------
    // Canonical idiom used across ~40 inline script shims: PROD serves nexora
    // under "/nexora/" (PrefixMiddleware), everything else under "/". Compute
    // it once, here, first -- every later `const API_PREFIX = window.API_PREFIX
    // || (...)` copy just picks up this value, and _workitem_detail_panel_js.html
    // already reads window.API_PREFIX directly.
    var API_PREFIX = window.API_PREFIX ||
        (window.location.href.includes('nexora') ? '/nexora/' : '/');
    window.API_PREFIX = API_PREFIX;

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? (meta.getAttribute('content') || '') : '';
    }

    function resolveUrl(url) {
        if (url.charAt(0) === '/') return window.API_PREFIX + url.slice(1);
        return url;
    }

    // ---- esc: full attribute-safe HTML escaper ------------------------------
    // Matches the fullest existing flavour (& < > " ' -> entities), used
    // wherever escaped text is interpolated into both element content AND
    // attribute values (e.g. data-search="${esc(...)}"). Not just text-safe.
    function esc(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ---- el: id -> element lookup shorthand ---------------------------------
    function el(id) {
        return document.getElementById(id);
    }

    // ---- api: throwing flavour -----------------------------------------------
    // Resolves the URL through API_PREFIX, sends JSON + CSRF header, and
    // throws on a non-2xx response (message from the JSON error body, falling
    // back to statusText). Returns the raw Response -- callers parse the body
    // themselves. Matches _reporting_js.html / _reporting_sources_js.html /
    // _reporting_metrics_js.html.
    async function api(url, opts) {
        url = resolveUrl(url);
        opts = opts || {};
        var res = await fetch(url, Object.assign(
            { headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() } },
            opts
        ));
        if (!res.ok) {
            var body = {};
            try { body = await res.json(); } catch (e) { /* non-JSON error body */ }
            var err = new Error(body.error || res.statusText || ('HTTP ' + res.status));
            // Nexora error bodies carry a second line -- the driver/validator
            // message behind the generic `error` (e.g. "Invalid object name
            // 'foo'." behind "Could not run query"). Dropping it left the
            // reporting SQL sandbox with no way to say WHAT was wrong.
            err.detail = body.detail || null;
            err.status = res.status;
            throw err;
        }
        return res;
    }

    // ---- apiSafe: non-throwing {ok,status,data} flavour -----------------------
    // Never throws: a network-level failure yields {ok:false,status:0,data:null};
    // otherwise the parsed JSON body (or null if the body isn't JSON) comes back
    // alongside res.ok/res.status. Matches _reporting_scheduled_js.html and the
    // byte-identical copies in reporting_simple.js / reporting_dashboard.js.
    async function apiSafe(url, opts) {
        url = resolveUrl(url);
        opts = opts || {};
        var res;
        try {
            res = await fetch(url, Object.assign(
                { headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() } },
                opts
            ));
        } catch (e) {
            return { ok: false, status: 0, data: null };
        }
        var data = null;
        try { data = await res.json(); } catch (e) { /* non-JSON body */ }
        return { ok: res.ok, status: res.status, data: data };
    }

    // ---- toast: absorbs both showNotification(msg, type) and toast(msg, isError) ----
    // A single bottom-center pill, styled inline off global --nx-* custom
    // properties (so it renders correctly even on pages that never load
    // reporting.css). Keeps the reporting family's markup contract --
    // data-testid="reporting-toast", role="status", class names
    // reporting-toast / reporting-toast--error / is-gone -- since
    // tests/e2e/test_reporting_dashboard.py and test_reporting_simple.py key
    // off that testid; reporting.css's rules for those classes still apply
    // (redundantly, on top of the inline styles) wherever that sheet is
    // loaded. The second argument accepts either flavour found in the wild:
    // a boolean (isError) or a string ('success' | 'error').
    function toast(message, kind) {
        var isError = kind === true || kind === 'error';
        var t = document.createElement('div');
        t.className = 'reporting-toast' + (isError ? ' reporting-toast--error' : '');
        t.setAttribute('role', 'status');
        t.setAttribute('data-testid', 'reporting-toast');
        t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);' +
            'background:var(--nx-card);color:var(--nx-text);' +
            'border:1px solid ' + (isError ? 'var(--nx-danger)' : 'var(--nx-border)') + ';' +
            'border-radius:calc(var(--nx-radius-scale, 1) * 8px);' +
            'padding:10px 16px;font-size:13px;z-index:2147483000;' +
            'box-shadow:0 6px 24px rgba(0,0,0,.18);transition:opacity .3s ease;';
        t.textContent = message;
        document.body.appendChild(t);
        setTimeout(function () {
            t.classList.add('is-gone');
            t.style.opacity = '0';
        }, 2600);
        setTimeout(function () {
            if (t.parentNode) t.parentNode.removeChild(t);
        }, 3000);
        return t;
    }

    // ---- formatDate / formatDateTime: Intl.DateTimeFormat-backed -------------
    // Existing copies substring a naive "YYYY-MM-DDTHH:MM:SS[.ffffff]" string;
    // these accept the same input via `new Date(value)` and format through
    // Intl so the result is locale-shaped rather than a raw ISO slice.
    // formatDateTime's `{ seconds: true }` option keeps
    // _generali_import_status_js.html's seconds-precision display
    // (substring(0, 19) today) once that call site migrates onto this.
    function toDate(value) {
        if (value === null || value === undefined || value === '') return null;
        var d = new Date(value);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatDate(value) {
        var d = toDate(value);
        if (!d) return '—';
        return new Intl.DateTimeFormat(undefined, {
            year: 'numeric', month: '2-digit', day: '2-digit'
        }).format(d);
    }

    function formatDateTime(value, opts) {
        var d = toDate(value);
        if (!d) return '—';
        var withSeconds = !!(opts && opts.seconds);
        var parts = {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', hour12: false
        };
        if (withSeconds) parts.second = '2-digit';
        return new Intl.DateTimeFormat(undefined, parts).format(d);
    }

    // ---- formatHours -----------------------------------------------------------
    // Whole hours render bare, fractional hours render to one decimal.
    function formatHours(h) {
        if (h === null || h === undefined || h === '') return '—';
        var n = Number(h);
        if (isNaN(n)) return '—';
        return n % 1 === 0 ? n.toFixed(0) : n.toFixed(1);
    }

    window.NX = {
        esc: esc,
        el: el,
        api: api,
        apiSafe: apiSafe,
        toast: toast,
        formatDate: formatDate,
        formatDateTime: formatDateTime,
        formatHours: formatHours,
        csrfToken: csrfToken
    };
})(window, document);

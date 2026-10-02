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
    // under "/nexora/" (PrefixMiddleware), everything else under "/". Decide by
    // the first PATH segment, never by the hostname: dev-nexora.sydoc.ch contains
    // "nexora" too and serves at "/" (#338). Compute
    // it once, here, first -- every later `const API_PREFIX = window.API_PREFIX
    // || (...)` copy just picks up this value, and _workitem_detail_panel_js.html
    // already reads window.API_PREFIX directly.
    var API_PREFIX = window.API_PREFIX ||
        (window.location.pathname.split('/')[1] === 'nexora' ? '/nexora/' : '/');
    window.API_PREFIX = API_PREFIX;

    // ---- expired session: follow a fetch that was bounced to /login ----------
    // An expired or revoked session answers a page's fetch() with a 302 to
    // /login; fetch follows it silently and hands back the login page as a
    // 200 HTML response, which passes every `res.ok` guard and then fails to
    // parse -- so pages reported "could not load" instead of sending the
    // user to sign in. Wrap fetch once, here, so every caller (NX.api,
    // apiSafe, and the raw fetch() calls across templates/js/**) gets it.
    // The returned promise never settles: the page is navigating away, and
    // settling it would only flash an error toast on the way out.
    var LOGIN_PATH = API_PREFIX + 'login';
    if (window.fetch) {
        var nativeFetch = window.fetch.bind(window);
        window.fetch = function () {
            return nativeFetch.apply(null, arguments).then(function (res) {
                if (res.redirected && new URL(res.url).pathname === LOGIN_PATH &&
                        window.location.pathname !== LOGIN_PATH) {
                    window.location.assign(res.url);
                    return new Promise(function () {});
                }
                return res;
            });
        };
    }

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

    // ---- flatpickr: the same picker on a phone as on desktop -----------------
    // By default flatpickr swaps its input for a native <input type="date">
    // on a mobile user agent. On an iPhone that field ignores nexora's input
    // styling, shows no "yyyy-mm-dd" hint while empty and formats the date its
    // own way, so the Generali From/To pair looked unlike every field around
    // it. disableMobile keeps flatpickr's own input and calendar everywhere.
    // Set here, once, rather than in ~35 flatpickr() calls: pages load
    // flatpickr in <head>, before this file runs from <body>; the
    // DOMContentLoaded pass covers a page that loads it later.
    function flatpickrDefaults() {
        if (window.flatpickr && typeof window.flatpickr.setDefaults === 'function') {
            window.flatpickr.setDefaults({ disableMobile: true });
        }
    }
    flatpickrDefaults();
    document.addEventListener('DOMContentLoaded', flatpickrDefaults);

    // ---- filters folded away on a phone ----------------------------------------
    // Every list page opens with a filter block (dates, category, organisation,
    // user, status...), and on a phone that block filled the whole first screen:
    // the entries people came for started below it. On a touch phone each
    // .nx-filter now starts folded behind one "Filters" button, which says how
    // many filters are set, so nothing is hidden silently. Desktop untouched.
    var PHONE_MQ = '(max-width: 768px) and (pointer: coarse)';
    function activeFilterCount(box) {
        var n = 0;
        box.querySelectorAll('input, select').forEach(function (el) {
            if (el.type === 'hidden' || el.type === 'button' || el.type === 'submit') return;
            if (el.tagName === 'SELECT') { if (el.selectedIndex > 0) n++; }
            else if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) n++; }
            else if ((el.value || '').trim()) n++;
        });
        return n;
    }
    function foldFilters() {
        if (!window.matchMedia(PHONE_MQ).matches) return;
        var L = window.NX_I18N_CORE || {};
        document.querySelectorAll('.nx-filter').forEach(function (box) {
            if (box.dataset.nxFold) return;
            box.dataset.nxFold = '1';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nx-btn nx-btn--secondary nx-filter-toggle';
            btn.setAttribute('aria-expanded', 'false');
            btn.setAttribute('data-testid', 'nx-filter-toggle');
            function paint() {
                var open = !box.classList.contains('nx-filter--folded');
                var n = activeFilterCount(box);
                btn.setAttribute('aria-expanded', String(open));
                btn.setAttribute('aria-label', open ? (L.hideFilters || 'Hide filters') : (L.showFilters || 'Show filters'));
                btn.innerHTML = '<i class="fas fa-sliders" aria-hidden="true"></i><span>' + esc(L.filters || 'Filters') + '</span>' +
                    (n ? '<span class="nx-filter-toggle__n">' + n + '</span>' : '') +
                    '<i class="fas fa-chevron-' + (open ? 'up' : 'down') + ' nx-filter-toggle__chev" aria-hidden="true"></i>';
            }
            box.classList.add('nx-filter--folded');
            box.parentNode.insertBefore(btn, box);
            btn.addEventListener('click', function () { box.classList.toggle('nx-filter--folded'); paint(); });
            box.addEventListener('change', paint);
            box.addEventListener('input', paint);
            paint();
            // Pages fill some filters from script after load (default dates,
            // organisation lists); recount once they have had the chance.
            setTimeout(paint, 1500);
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', foldFilters);
    } else {
        foldFilters();
    }

    // ---- phone start page by role --------------------------------------------
    // Right after signing in on a touch phone, someone who reports post
    // (window.NX_PHONE_START, set in _header.html) goes straight to Reporting
    // instead of the desktop start page. Only on the first page after the
    // sign-in (the referrer is the login or 2FA page), so the dashboard link
    // in the menu still works. Desktop keeps startpage_redirect_to().
    function phoneStart() {
        var url = window.NX_PHONE_START;
        if (!url || !window.matchMedia(PHONE_MQ).matches) return;
        var ref;
        try { ref = new URL(document.referrer).pathname; } catch (e) { return; }
        if (!/\/(login|verify_2fa|init_2FA)$/.test(ref)) return;
        if (window.location.pathname === new URL(url, window.location.href).pathname) return;
        window.location.replace(url);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', phoneStart);
    } else {
        phoneStart();
    }

    // ---- installed app: reload when a new version is live ------------------
    // An iPhone home-screen app does not reload when it is opened again: it
    // shows the page it had in memory, however old. After a deploy that kept
    // the old, broken layout on screen while Safari already had the fix. So
    // when the installed app comes back to the front, ask the server which
    // build is live and reload once if it is not this page's build. Skipped
    // while something is being typed or a dialog is open, so nobody loses a
    // half-filled form. Not in a browser tab, where reload is one tap away.
    function isInstalledApp() {
        return window.navigator.standalone === true ||
            (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
    }
    function busy() {
        var a = document.activeElement;
        if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return true;
        // Only dialogs actually on screen: the command palette's panels carry
        // aria-modal even while closed.
        return Array.prototype.some.call(
            document.querySelectorAll('[aria-modal="true"], .fixed.inset-0.flex'),
            function (el) { return el.getClientRects().length > 0; });
    }
    var checkingBuild = false;
    function checkBuild() {
        var mine = window.NX_BUILD;
        if (!mine || checkingBuild || document.visibilityState !== 'visible' || !isInstalledApp()) return;
        checkingBuild = true;
        window.fetch(API_PREFIX + 'build.json', { cache: 'no-store', credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (d && d.build && d.build !== mine && !busy()) window.location.reload();
            })
            .catch(function () { /* offline or restarting: try again next time */ })
            .then(function () { checkingBuild = false; });
    }
    document.addEventListener('visibilitychange', checkBuild);
    window.addEventListener('pageshow', function (e) { if (e.persisted) checkBuild(); });

    // ---- stat-card icons: all or none per row -------------------------------
    // .nx-stat wraps its icon chip under the number when the two do not fit
    // side by side. On a phone that gave a row of KPI cards an extra line in
    // some cards and not others -- uneven boxes for a decorative icon. So if
    // ANY card in a group has to wrap its chip, hide the chips of the whole
    // group (.nx-stats--no-chips); where they all fit, they stay. Desktop cards
    // never wrap, so nothing changes there. Re-checked when a number loads
    // (the KPIs arrive by fetch, "—" first) and on resize.
    function chipWrapped(stat) {
        var chip = stat.querySelector(':scope > .nx-stat__chip');
        if (!chip) return false;
        var text = stat.firstElementChild === chip ? chip.nextElementSibling : stat.firstElementChild;
        if (!text) return false;
        return chip.getBoundingClientRect().top >= text.getBoundingClientRect().bottom - 1;
    }
    function fitStatChips() {
        var groups = [];
        document.querySelectorAll('.nx-stat').forEach(function (s) {
            if (s.parentElement && groups.indexOf(s.parentElement) < 0) groups.push(s.parentElement);
        });
        groups.forEach(function (g) {
            g.classList.remove('nx-stats--no-chips');
            var stats = Array.prototype.filter.call(g.children, function (c) { return c.classList.contains('nx-stat'); });
            if (stats.some(chipWrapped)) g.classList.add('nx-stats--no-chips');
        });
    }
    var fitQueued = false;
    function queueFit() {
        if (fitQueued) return;
        fitQueued = true;
        window.requestAnimationFrame(function () { fitQueued = false; fitStatChips(); });
    }
    function watchStats() {
        queueFit();
        // Text and child changes only -- toggling the class is an attribute
        // change, so the observer cannot feed itself.
        var mo = new MutationObserver(queueFit);
        document.querySelectorAll('.nx-stat').forEach(function (s) {
            mo.observe(s, { childList: true, characterData: true, subtree: true });
        });
        window.addEventListener('resize', queueFit);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchStats);
    } else {
        watchStats();
    }
})(window, document);

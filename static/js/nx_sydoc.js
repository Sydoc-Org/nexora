/* Shared behaviour of Sydoc's own books (Finance, BPS) -- window.NXSydoc.

   Pure helpers (fmt, isoWeek, periodHeadline, monthCells) that the Node
   harness tests reach (tests/unit/test_nx_sydoc_js.py), plus initPicker(), the
   period-picker modal controller, which touches the DOM only when a page calls
   it. Markup: templates/_sydoc.html; styles: nexora-ui.css (nx-sydoc-*). */
(function () {
    'use strict';

    // Swiss English writes "4 Aug", not "Aug 4": the page's `en` formats dates en-GB.
    const loc = lang => (!lang || lang === 'en' ? 'en-GB' : lang);

    function fmt(str, vars) {
        return String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }

    function parse(iso) {
        const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
        return new Date(Date.UTC(y, m - 1, d));
    }
    const DAY = 86400000;
    const addDays = (d, n) => new Date(d.getTime() + n * DAY);
    const lastOfMonth = d => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));

    // ISO-8601 week number: the week holding the year's first Thursday is week 1.
    function isoWeekParts(iso) {
        const d = parse(iso);
        const dow = (d.getUTCDay() + 6) % 7; // Monday = 0
        const thursday = addDays(d, 3 - dow);
        const year = thursday.getUTCFullYear();
        const jan1 = Date.UTC(year, 0, 1);
        return { week: 1 + Math.floor((thursday.getTime() - jan1) / DAY / 7), year };
    }
    const isoWeek = iso => isoWeekParts(iso).week;

    function formatter(lang, opts) {
        return new Intl.DateTimeFormat(loc(lang), Object.assign({ timeZone: 'UTC' }, opts));
    }

    /* The headline of a period, split into its big word and its grey year:
         a whole month     -> {main: 'August',    year: '2026', kind: 'month'}
         Monday..Sunday    -> {main: 'Week 39',   year: '2026', kind: 'week'}
         whole months      -> {main: 'Jun – Aug', year: '2026', kind: 'months'}
         anything else     -> {main: '4 – 19 Aug', year: '2026', kind: 'range'}
       A month so far (the 1st up to `todayIso`) reads as that month. */
    function periodHeadline(from, to, lang, weekLabel, todayIso) {
        const a = parse(from);
        const b = parse(to);
        const dash = ' – ';
        const yearOf = d => String(d.getUTCFullYear());
        const startsMonth = a.getUTCDate() === 1;
        const endsMonth = b.getTime() === lastOfMonth(b).getTime();
        const sameMonth = a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCMonth() === b.getUTCMonth();
        const sameYear = a.getUTCFullYear() === b.getUTCFullYear();
        const span = Math.round((b - a) / DAY) + 1;

        const soFar = todayIso && String(to).slice(0, 10) === String(todayIso).slice(0, 10);
        if (startsMonth && sameMonth && (endsMonth || soFar)) {
            return { main: formatter(lang, { month: 'long' }).format(a), year: yearOf(a), kind: 'month' };
        }
        if (span === 7 && a.getUTCDay() === 1) {
            const w = isoWeekParts(from);
            return { main: fmt(weekLabel || 'Week {n}', { n: w.week }), year: String(w.year), kind: 'week' };
        }
        const short = formatter(lang, { month: 'short' });
        if (startsMonth && endsMonth) {
            const head = sameYear ? short.format(a) : `${short.format(a)} ${yearOf(a)}`;
            return { main: head + dash + short.format(b), year: yearOf(b), kind: 'months' };
        }
        const dayOnly = formatter(lang, { day: 'numeric' });
        const dayMonth = formatter(lang, { day: 'numeric', month: 'short' });
        // formatRange knows each locale's shape ("4–19 Aug", "4.–19. Aug.");
        // only the dash gets the thin spacing of the design.
        if (sameYear && dayMonth.formatRange) {
            return { main: dayMonth.formatRange(a, b).replace(/\s*[–-]\s*/, dash), year: yearOf(b), kind: 'range' };
        }
        let head;
        if (sameMonth) head = dayOnly.format(a);
        else if (sameYear) head = dayMonth.format(a);
        else head = `${dayMonth.format(a)} ${yearOf(a)}`;
        return { main: head + dash + dayMonth.format(b), year: yearOf(b), kind: 'range' };
    }

    // The 12 cells of the picker's month grid for one year.
    function monthCells(year, todayIso, lang) {
        const today = parse(todayIso);
        const thisKey = today.getUTCFullYear() * 12 + today.getUTCMonth();
        const short = formatter(lang, { month: 'short' });
        const out = [];
        for (let m = 0; m < 12; m++) {
            const d = new Date(Date.UTC(year, m, 1));
            out.push({
                key: `${year}-${String(m + 1).padStart(2, '0')}`,
                name: short.format(d),
                future: year * 12 + m > thisKey,
                current: year * 12 + m === thisKey,
            });
        }
        return out;
    }

    const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

    /* The picker modal: opens from `opener`, traps Tab inside its panel, and
       closes on Esc, a click on the overlay, or [data-role="picker-close"],
       handing focus back to the opener. `onOpen` runs before it shows. */
    function initPicker(opts) {
        const root = opts.root;
        const opener = opts.opener;
        if (!root || !opener) return null;
        // .nx-main is a stacking context (z-index: 1), so an overlay inside it
        // stays under the sidebar however high its own z-index: hoist it.
        if (root.parentElement !== document.body) document.body.appendChild(root);
        const panel = root.querySelector('.nx-sydoc-picker__panel') || root;

        function onKey(e) {
            if (e.key === 'Escape') {
                e.preventDefault();
                close();
                return;
            }
            if (e.key !== 'Tab') return;
            const items = Array.from(panel.querySelectorAll(FOCUSABLE)).filter(el => el.offsetParent !== null);
            if (!items.length) return;
            const first = items[0];
            const last = items[items.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }

        function open() {
            if (opts.onOpen) opts.onOpen();
            root.hidden = false;
            opener.setAttribute('aria-expanded', 'true');
            document.addEventListener('keydown', onKey, true);
            const target = panel.querySelector('.is-selected:not([disabled])') || panel.querySelector(FOCUSABLE);
            if (target) target.focus();
        }

        function close() {
            if (root.hidden) return;
            root.hidden = true;
            opener.setAttribute('aria-expanded', 'false');
            document.removeEventListener('keydown', onKey, true);
            opener.focus();
            if (opts.onClose) opts.onClose();
        }

        opener.setAttribute('aria-expanded', 'false');
        opener.addEventListener('click', open);
        root.addEventListener('click', e => {
            if (e.target === root || e.target.closest('[data-role="picker-close"]')) close();
        });
        return { open, close };
    }

    window.NXSydoc = { fmt, isoWeek, periodHeadline, monthCells, initPicker };
})();

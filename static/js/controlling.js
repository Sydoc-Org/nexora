/* Sydoc Controlling (#433). Behaviour only -- strings and Jinja data arrive
   on window.NX_CONTROLLING; see templates/js/_controlling_js.html.

   The band is server-rendered. Below it, one request for the month
   (/api/controlling/month) fills the summary, the margin table, the client
   blocks, the task matrix and the volumes; a second one (/api/controlling/trend)
   fills the trend. A figure the page cannot compute is never a silent 0: it
   is "—" with the reason (no invoice, draft, EUR, not linked, a source down).
   Numbers are Swiss: apostrophe thousands, a true minus. Colour: gain/loss
   only for deltas and margins, Sydoc orange for the previous month and the
   selected month. Design: docs/design/design_handoff_sydoc_controlling. */
(function () {
    'use strict';

    const CFG = window.NX_CONTROLLING;
    const S = CFG.strings;
    const Sy = window.NXSydoc;
    const esc = window.NX.esc;
    const fmt = Sy.fmt;
    const lang = document.documentElement.lang || undefined;
    const API = window.API_PREFIX;
    const MINUS = '−';

    // ---- numbers ------------------------------------------------------------
    function group(intStr) {
        return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
    }
    function num(v, d) {
        if (v == null || Number.isNaN(Number(v))) return '—';
        d = d == null ? 2 : d;
        const n = Number(v);
        const neg = n < 0 && Math.abs(n) >= Math.pow(10, -d) / 2;
        const [a, b] = Math.abs(n).toFixed(d).split('.');
        return (neg ? MINUS : '') + group(a) + (b ? '.' + b : '');
    }
    function sgn(v, d) {
        if (v == null) return '—';
        d = d == null ? 2 : d;
        return (Number(v) >= Math.pow(10, -d) / 2 ? '+' : '') + num(v, d);
    }
    // A rate as the band writes it: 85, 72.50.
    const rateNum = v => (v == null ? '—' : Number.isInteger(Number(v)) ? group(String(Number(v))) : num(v));
    function pct(v, d) {
        if (v == null) return '—';
        return (v < 0 ? MINUS : '') + Math.abs(v * 100).toFixed(d == null ? 1 : d) + '%';
    }
    // Finance's neutral delta: the arrow says the direction, the colour says nothing.
    function finDelta(v, p) {
        if (v == null || p == null) return '—';
        if (Math.abs(v - p) < 1e-9) return S.unchanged;
        if (!p) return '▲ ' + S.isNew;
        const r = Math.round(((v - p) / Math.abs(p)) * 100);
        if (r === 0) return v > p ? '▲ +0%' : '▼ ' + MINUS + '0%';
        return (r > 0 ? '▲ +' : '▼ ' + MINUS) + Math.abs(r) + '%';
    }
    const dIcon = d => (d > 0 ? 'fas fa-arrow-trend-up' : d < 0 ? 'fas fa-arrow-trend-down' : 'fas fa-minus');
    // A signed CHF change with its trend icon; "—" alone when there is nothing to compare.
    function dHtml(d) {
        if (d == null) return '<span class="nx-ctl-d is-flat">—</span>';
        return `<span class="nx-ctl-d ${dClass(d, true)}"><i class="${dIcon(d)}" aria-hidden="true"></i>${esc(sgn(d))}</span>`;
    }
    // Good/bad colour of a change: up is good for money in, bad for hours and cost.
    const dClass = (d, upGood) => (!d ? 'is-flat' : (d > 0) === upGood ? 'is-gain' : 'is-loss');

    function cmpHtml(value, prev, width) {
        value = Math.max(0, Number(value) || 0);
        prev = Math.max(0, Number(prev) || 0);
        const max = Math.max(value, prev);
        const w = width ? ` style="width:${width}px"` : '';
        if (!max) return `<span class="nx-fin-cmp"${w} aria-hidden="true"></span>`;
        return `<span class="nx-fin-cmp"${w} aria-hidden="true"><span class="nx-fin-cmp__fill" style="width:${((value / max) * 100).toFixed(1)}%"></span>` +
            `<span class="nx-fin-cmp__prev" style="left:calc(${((prev / max) * 100).toFixed(1)}% - 1px)"></span></span>`;
    }

    const chip = (tone, label, opts) => {
        opts = opts || {};
        const cls = 'nx-label nx-label--' + tone + (opts.dot === false ? ' nx-label--nodot' : '');
        const icon = opts.icon ? `<i class="${opts.icon}" aria-hidden="true"></i>` : '';
        const ring = opts.ring ? '<span class="nx-ctl-ring nx-ctl-ring--inline" aria-hidden="true"></span>' : '';
        return `<span class="${cls}">${icon}${ring}${esc(label)}</span>`;
    };
    const ring = () => `<span class="nx-ctl-ring" title="${esc(S.incompleteTitle)}" aria-label="${esc(S.incompleteTitle)}"></span>`;
    const moved = () => `<i class="fas fa-code-compare nx-ctl-moved" title="${esc(S.movedTitle)}" aria-label="${esc(S.movedTitle)}"></i>`;
    const has = (cell, flag) => !!cell && (cell.flags || []).includes(flag);

    // ---- band: print, rates, picker -----------------------------------------
    const printBtn = document.getElementById('ctl-print');
    if (printBtn) {
        printBtn.addEventListener('click', () => {
            document.querySelectorAll('.nx-ctl-client').forEach(b => setOpen(b, true));
            window.print();
        });
    }

    (function picker() {
        const root = document.getElementById('ctl-picker');
        if (!root) return;
        const byKey = {};
        (CFG.months || []).forEach(m => { byKey[m.value] = m; });
        const years = (CFG.months || []).map(m => Number(m.value.slice(0, 4)));
        const minYear = Math.min(...years);
        const maxYear = Math.max(...years);
        let viewYear = Number(CFG.month.slice(0, 4));
        const grid = root.querySelector('[data-role="months"]');
        const STATUS = {
            closed: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--closed"><i class="fas fa-lock" aria-hidden="true"></i>${esc(S.closedShort)}</span>`,
            open: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--open"><span class="nx-sydoc-dot"></span>${esc(S.openShort)}</span>`,
            running: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--running"><span class="nx-sydoc-dot"></span>${esc(S.running)}</span>`,
        };
        function render() {
            root.querySelector('[data-role="year"]').textContent = String(viewYear);
            root.querySelector('[data-role="year-prev"]').disabled = viewYear <= minYear;
            root.querySelector('[data-role="year-next"]').disabled = viewYear >= maxYear;
            grid.innerHTML = Sy.monthCells(viewYear, CFG.today, lang).map(c => {
                const m = byKey[c.key];
                const selected = c.key === CFG.month;
                const status = m ? STATUS[m.state]() : '<span class="nx-sydoc-picker__cell-status"></span>';
                return `<button type="button" class="nx-sydoc-picker__cell${selected ? ' is-selected' : ''}" data-month="${c.key}"` +
                    `${m ? ` aria-label="${esc(m.label)}"` : ' disabled'}${selected ? ' aria-current="true"' : ''}>` +
                    `<span class="nx-sydoc-picker__cell-name">${esc(c.name)}</span>${status}</button>`;
            }).join('');
        }
        grid.addEventListener('click', e => {
            const cell = e.target.closest('[data-month]');
            if (cell && !cell.disabled) go(cell.dataset.month);
        });
        root.querySelector('[data-role="year-prev"]').addEventListener('click', () => { viewYear -= 1; render(); });
        root.querySelector('[data-role="year-next"]').addEventListener('click', () => { viewYear += 1; render(); });
        Sy.initPicker({
            root,
            opener: document.querySelector('[data-testid="controlling-period-button"]'),
            onOpen: () => { viewYear = Number(CFG.month.slice(0, 4)); render(); },
        });
    })();

    function go(month) {
        const url = new URL(window.location.href);
        url.searchParams.set('month', month);
        url.hash = '';
        window.location.assign(url.toString());
    }

    // ---- shared bits ----------------------------------------------------------
    function errorBox(message, detail, retry) {
        return `<div class="nx-fin-error" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>` +
            `<span class="nx-ctl-error__msg">${esc(message)}</span>` +
            (retry ? `<button type="button" class="nx-btn nx-btn--secondary nx-btn--sm" data-retry="${retry}">${esc(S.retry)}</button>` : '') +
            (detail ? `<span class="nx-fin-error__detail">${esc(detail)}</span>` : '') + '</div>';
    }
    document.addEventListener('click', e => {
        const r = e.target.closest('[data-retry]');
        if (!r) return;
        if (r.dataset.retry === 'month') loadMonth(true);
        if (r.dataset.retry === 'trend') loadTrend(true);
    });

    const STREAMS = CFG.streams;
    const byStream = {};
    STREAMS.forEach(s => { byStream[s.key] = s; });
    let M = null; // the month payload

    // ---- 2. summary ------------------------------------------------------------
    function money(v) {
        const [a, b] = num(Math.abs(v)).split('.');
        return { main: (v < 0 ? MINUS : '') + a, suf: '.' + b };
    }
    function kpi(o) {
        const value = o.main == null
            ? '<span class="nx-ctl-summary__main is-none">—</span>'
            : `${o.pre ? `<span class="nx-ctl-summary__pre">${esc(o.pre)}</span>` : ''}` +
              `<span class="nx-ctl-summary__main ${o.cls || ''}">${esc(o.main)}<span class="nx-ctl-summary__suf">${esc(o.suf || '')}</span></span>` +
              `${o.after ? `<span class="nx-ctl-summary__after ${o.cls || ''}">${esc(o.after)}</span>` : ''}`;
        const delta = o.dT
            ? `<p class="nx-ctl-summary__delta"><span class="nx-ctl-d ${o.dCls || 'is-flat'}">${o.dIcon ? `<i class="${o.dIcon}" aria-hidden="true"></i>` : ''}${esc(o.dT)}</span><span>${esc(o.dSub || '')}</span></p>`
            : '';
        return `<div class="nx-ctl-summary__cell" data-testid="controlling-kpi-${o.id}">` +
            `<p class="nx-ctl-eyebrow">${esc(o.label)}</p><p class="nx-ctl-summary__value">${value}</p>${delta}` +
            `${o.cap ? `<p class="nx-ctl-summary__cap">${esc(o.cap)}</p>` : ''}</div>`;
    }
    function rel(v, p, upGood, f) {
        if (v == null || p == null) return { dT: '—', dSub: fmt(S.nothingToCompare, { month: CFG.prevShort }), dIcon: '' };
        const d = v - p;
        if (!p && d) return { dT: '▲ ' + S.isNew, dSub: fmt(S.vsPrev, { month: CFG.prevShort, value: f(p) }), dIcon: '' };
        const r = p ? d / Math.abs(p) : 0;
        return {
            dT: (d > 0 ? '+' : d < 0 ? MINUS : '±') + Math.abs(r * 100).toFixed(1) + '%',
            dSub: fmt(S.vsPrev, { month: CFG.prevShort, value: f(p) }),
            // A running month is compared so far with a whole one: no good/bad colour.
            dCls: M && M.state === 'running' ? 'is-flat' : dClass(d, upGood),
            dIcon: dIcon(d),
        };
    }
    function renderSummary(empty) {
        const el = document.getElementById('ctl-summary');
        if (empty) {
            const cap = fmt(S.nothingBooked, { month: CFG.monthLabel });
            el.querySelector('[data-role="body"]').innerHTML = [
                ['hours', S.totalHours], ['cost', S.cost], ['invoiced', S.invoicedExcl], ['margin', S.margin], ['documents', S.documents],
            ].map(([id, label]) => kpi({ id, label, main: null, cap })).join('');
            el.removeAttribute('aria-busy');
            return;
        }
        const T = M.totals.cur;
        const P = M.totals.prev;
        const running = M.state === 'running';
        const cells = [];
        if (T.hours == null) {
            cells.push(kpi({ id: 'hours', label: S.totalHours, main: null, dT: S.bpsUnavailable, dCls: 'is-loss', dIcon: 'fas fa-triangle-exclamation' }));
            cells.push(kpi({ id: 'cost', label: S.cost, main: null, dT: S.bpsUnavailable, dCls: 'is-loss', dIcon: 'fas fa-triangle-exclamation' }));
        } else {
            const [ha, hb] = num(T.hours, 1).split('.');
            cells.push(kpi({ id: 'hours', label: S.totalHours, main: ha, suf: '.' + hb, after: 'h', ...rel(T.hours, P && P.hours, false, v => num(v, 1) + ' h') }));
            const overrides = M.streams.filter(s => has(s.cur, 'override')).length;
            if (T.cost == null) {
                cells.push(kpi({ id: 'cost', label: S.cost, main: null, cap: S.costUnknown }));
            }
            const c = money(T.cost || 0);
            if (T.cost != null) cells.push(kpi({ id: 'cost', label: S.cost, pre: 'CHF', main: c.main, suf: c.suf, ...rel(T.cost, P && P.cost, false, v => num(v, 0)),
                cap: overrides ? fmt(overrides === 1 ? S.oneOverride : S.nOverrides, { n: overrides }) : '' }));
        }
        if (running) {
            cells.push(kpi({ id: 'invoiced', label: S.invoicedExcl, main: null, cap: fmt(S.datedIn, { month: CFG.invoiceMonth }) }));
            cells.push(kpi({ id: 'margin', label: S.margin, main: null, cap: fmt(S.datedIn, { month: CFG.invoiceMonth }) }));
        } else if (M.bexioError) {
            cells.push(kpi({ id: 'invoiced', label: S.invoicedExcl, main: null, dT: S.bexioUnavailable, dCls: 'is-loss', dIcon: 'fas fa-triangle-exclamation' }));
            cells.push(kpi({ id: 'margin', label: S.margin, main: null, dT: S.bexioUnavailable, dCls: 'is-loss', dIcon: 'fas fa-triangle-exclamation' }));
        } else {
            const count = { missing: 0, draft: 0, foreign: 0, unlinked: 0 };
            M.streams.forEach(s => { if (s.cur.state in count) count[s.cur.state] += 1; });
            const out = [];
            if (count.missing) out.push(fmt(S.capMissing, { n: count.missing }));
            if (count.draft) out.push(fmt(S.capDraft, { n: count.draft }));
            if (count.foreign) out.push(fmt(S.capForeign, { n: count.foreign }));
            if (count.unlinked) out.push(fmt(S.capUnlinked, { n: count.unlinked }));
            if (M.unassigned.length) out.push(fmt(S.capUnassigned, { n: M.unassigned.length }));
            const im = money(T.invoiced || 0);
            cells.push(kpi({ id: 'invoiced', label: S.invoicedExcl, pre: 'CHF', main: im.main, suf: im.suf,
                ...rel(T.invoiced, P && P.invoiced, true, v => num(v, 0)), cap: out.length ? fmt(S.notCounted, { list: out.join(', ') }) : '' }));
            if (T.margin == null) {
                cells.push(kpi({ id: 'margin', label: S.margin, main: null, cap: fmt(S.ofStreams, { n: 0, total: T.streams }) }));
            } else {
                const mm = money(T.margin);
                const d = P && P.margin != null ? T.margin - P.margin : null;
                cells.push(kpi({ id: 'margin', label: S.margin, pre: 'CHF', main: (T.margin > 0 ? '+' : '') + mm.main, suf: mm.suf,
                    after: pct(T.marginPct), cls: T.margin < 0 ? 'is-loss' : '',
                    dT: d == null ? '—' : sgn(d, 0), dIcon: d == null ? '' : dIcon(d), dCls: d == null || running ? 'is-flat' : dClass(d, true),
                    dSub: d == null ? '' : fmt(S.vsPrev, { month: CFG.prevShort, value: sgn(P.margin, 0) }),
                    cap: fmt(S.ofStreams, { n: T.streamsWithMargin, total: T.streams }) }));
            }
        }
        if (T.documents == null) {
            cells.push(kpi({ id: 'documents', label: S.documents, main: null }));
        } else {
            cells.push(kpi({ id: 'documents', label: S.documents, main: num(T.documents, 0), ...rel(T.documents, P && P.documents, true, v => num(v, 0)) }));
        }
        el.querySelector('[data-role="body"]').innerHTML = cells.join('');
        el.removeAttribute('aria-busy');
    }

    // ---- 3. margin by client -----------------------------------------------------
    const INV_STATUS = {
        paid: ['green', 'paid'], open: ['blue', 'open'], partial: ['amber', 'partial'], draft: ['gray', 'draft'],
        cancelled: ['gray', 'cancelled'], unpaid: ['red', 'unpaid'], other: ['gray', 'other'],
    };
    const contactSub = (s, c) => {
        const names = c.contacts && c.contacts.length ? c.contacts.join(', ') : '';
        const tail = s.title || '';
        return [names, tail].filter(Boolean).join(' · ') || s.bps;
    };
    // The flag that replaces the margin cells, or null when the stream has a margin.
    function flagOf(c) {
        if (M.state === 'running' && !c.frozen) return { chip: chip('gray', S.notInvoicedYet, { dot: false }), text: fmt(S.datedIn, { month: CFG.invoiceMonth }) };
        if (c.state === 'error') return { chip: chip('red', S.bexioUnavailable), text: S.needsBexio };
        if (c.state === 'missing') return { chip: chip('amber', S.noInvoice), text: fmt(S.nothingDated, { month: CFG.invoiceMonth }) };
        if (c.state === 'unlinked') return { chip: chip('gray', S.notLinked, { dot: false }), text: S.noProjectMapped };
        if (c.state === 'foreign') return { chip: chip('blue', (c.foreign[0] || {}).currency || S.foreign), text: S.notConverted };
        if (c.state === 'draft') {
            const t = c.draft != null && c.cost != null ? fmt(S.ifIssued, { value: sgn(c.draft - c.cost) }) : '';
            return { chip: chip('gray', S.draft), text: t };
        }
        if (c.hours == null) return { chip: chip('red', S.bpsUnavailable), text: S.needsHours };
        if (c.margin == null && has(c, 'no_rate')) return { chip: chip('amber', S.noRate), text: S.setRate };
        if (c.margin == null && has(c, 'cost_unknown')) return { chip: chip('blue', S.foreign), text: S.costForeign };
        if (c.margin == null) return { chip: chip('gray', S.unknown), text: '' };
        return null;
    }
    function invCells(c) {
        if (c.state === 'foreign' && c.foreign.length) {
            const f = c.foreign[0];
            return { inv: `${f.currency} ${num(f.excl)}`, incl: `${f.currency} ${num(f.total)}`, muted: true };
        }
        if (c.state === 'draft' && c.draft != null) return { inv: num(c.draft), incl: num(c.draftIncl), muted: true };
        if (c.invoiced == null) return { inv: '—', incl: '—', muted: false };
        return { inv: num(c.invoiced), incl: num(c.invoicedIncl), muted: false };
    }
    function renderClients() {
        const root = document.getElementById('ctl-margin');
        document.getElementById('ctl-clients-count').textContent = String(M.streams.length);
        document.getElementById('ctl-clients-meta').textContent =
            fmt(S.heroMeta, { month: CFG.invoiceMonth }) + (CFG.rateLabel ? ' · ' + CFG.rateLabel : '');
        const maxAbs = Math.max(1, ...M.streams.map(s => Math.abs(s.cur.margin || 0)));
        const head = `<div class="nx-ctl-margin__row nx-ctl-margin__head">
            <span>${esc(S.stream)}</span><span>${esc(S.hours)}</span><span>${esc(S.cost)}</span>
            <span>${esc(S.invoicedExcl)}</span><span>${esc(S.inclVat)}</span><span>${esc(S.marginChf)}</span>
            <span>${esc(S.margin + " %")}</span><span>${esc(fmt(S.vsShort, { month: CFG.prevShort }))}</span><span></span></div>`;
        const rows = M.streams.map(s => {
            const c = s.cur;
            const f = flagOf(c);
            const ic = invCells(c);
            const rateNote = has(c, 'override') && c.rate != null ? `<span class="nx-ctl-margin__note">${esc(fmt(S.atRate, { rate: rateNum(c.rate) }))}</span>` : '';
            let tail;
            if (f) {
                tail = `<span class="nx-ctl-margin__flag"><span class="nx-ctl-margin__flagtext">${esc(f.text)}</span>${f.chip}</span>`;
            } else {
                const w = (Math.abs(c.margin) / maxAbs) * 50;
                const bar = c.margin >= 0
                    ? `left:50%;width:${w.toFixed(1)}%`
                    : `left:${(50 - w).toFixed(1)}%;width:${w.toFixed(1)}%`;
                const loss = c.margin < 0 ? ' is-loss' : '';
                const prevM = s.prev ? s.prev.margin : null;
                const d = s.delta && s.delta.margin != null ? s.delta.margin : null;
                tail = `<span class="nx-ctl-margin__m"><span class="nx-ctl-mbar" aria-hidden="true"><span class="nx-ctl-mbar__zero"></span>` +
                    `<span class="nx-ctl-mbar__fill${loss}" style="${bar}"></span></span><span class="nx-ctl-num nx-ctl-margin__mv${loss}">${esc(sgn(c.margin))}</span></span>` +
                    `<span class="nx-ctl-num nx-ctl-margin__pct${loss}">${esc(pct(c.marginPct))}</span>` +
                    `<span class="nx-ctl-margin__vs">${dHtml(d)}` +
                    `<span class="nx-ctl-margin__vsub">${prevM == null ? '' : esc(CFG.prevShort + ' ' + sgn(prevM))}</span></span>`;
            }
            return `<a class="nx-ctl-margin__row nx-ctl-margin__body" href="#ctl-c-${esc(s.key)}" data-open="${esc(s.key)}" data-testid="controlling-row-${esc(s.key)}">
                <span class="nx-ctl-margin__name"><span>${esc(s.label)}</span><span class="nx-ctl-margin__sub">${esc(contactSub(s, c))}</span></span>
                <span class="nx-ctl-num nx-ctl-margin__hours">${has(c, 'incomplete') ? ring() : ''}${esc(c.hours == null ? '—' : num(c.hours))}</span>
                <span class="nx-ctl-num nx-ctl-margin__cost">${esc(c.cost == null ? '—' : num(c.cost))}${rateNote}</span>
                <span class="nx-ctl-num nx-ctl-margin__inv${ic.muted ? ' is-muted' : ''}">${has(c, 'moved') ? moved() : ''}${esc(ic.inv)}</span>
                <span class="nx-ctl-num nx-ctl-margin__incl${ic.muted ? ' is-muted' : ''}">${esc(ic.incl)}</span>
                ${tail}
                <i class="fas fa-chevron-down nx-ctl-margin__chev" aria-hidden="true"></i>
              </a>`;
        }).join('');
        const T = M.totals.cur;
        const P = M.totals.prev;
        const d = T.margin != null && P && P.margin != null ? T.margin - P.margin : null;
        const tl = T.margin != null && T.margin < 0 ? ' is-loss' : '';
        const total = `<div class="nx-ctl-margin__row nx-ctl-margin__total">
            <span class="nx-ctl-margin__name"><span>${esc(S.total)}</span><span class="nx-ctl-margin__sub">${esc(fmt(S.inTheMargin, { n: T.streamsWithMargin, total: T.streams }))}</span></span>
            <span class="nx-ctl-num">${esc(T.hours == null ? '—' : num(T.hours))}</span>
            <span class="nx-ctl-num">${esc(T.cost == null ? '—' : num(T.cost))}</span>
            <span class="nx-ctl-num">${esc(T.invoiced == null ? '—' : num(T.invoiced))}</span>
            <span class="nx-ctl-num nx-ctl-margin__incl">${esc(T.invoicedIncl == null ? '—' : num(T.invoicedIncl))}</span>
            <span class="nx-ctl-num nx-ctl-margin__tm${tl}">${esc(T.margin == null ? '—' : sgn(T.margin))}</span>
            <span class="nx-ctl-num nx-ctl-margin__pct${tl}">${esc(pct(T.marginPct))}</span>
            <span class="nx-ctl-margin__vs">${dHtml(d)}` +
            `<span class="nx-ctl-margin__vsub">${P && P.margin != null ? esc(CFG.prevShort + ' ' + sgn(P.margin)) : ''}</span></span>
            <span></span></div>`;
        const unassigned = M.unassigned.map(u => {
            const proj = u.projectName ? fmt(S.projectNotMapped, { project: u.projectName }) : S.noProject;
            return `<div class="nx-ctl-margin__row nx-ctl-unassigned" data-testid="controlling-unassigned">
                <span class="nx-ctl-unassigned__what"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>${chip('amber', S.unassigned)}
                  <span class="nx-ctl-unassigned__text" title="${esc(u.nr + ' · ' + u.title)}"><span class="nx-ctl-num nx-ctl-strong">${esc(u.nr)}</span> · ${esc(proj)}</span></span>
                <span class="nx-ctl-num">${esc(u.currency && u.currency !== 'CHF' ? u.currency + ' ' + num(u.excl) : num(u.excl))}</span>
                <span class="nx-ctl-num nx-ctl-margin__incl">${esc(num(u.total))}</span>
                <span class="nx-ctl-unassigned__note">${esc(S.notInTotals)}</span>
              </div>`;
        }).join('');
        const anyInc = M.streams.some(s => has(s.cur, 'incomplete'));
        const anyMoved = M.streams.some(s => has(s.cur, 'moved'));
        const legend = `<div class="nx-ctl-legend">
            ${anyInc ? `<span><span class="nx-ctl-ring" aria-hidden="true"></span>${esc(S.incompleteTitle)}</span>` : ''}
            ${anyMoved ? `<span><i class="fas fa-code-compare nx-ctl-moved" aria-hidden="true"></i>${esc(S.movedLegend)}</span>` : ''}
            <span>${esc(S.costLegend)}</span></div>`;
        const err = M.bexioError ? errorBox(fmt(S.bexioDown, { reason: M.bexioError }), null, 'month') : '';
        const hoursErr = M.hoursError && !M.closed ? errorBox(fmt(S.bpsDown, { reason: M.hoursError }), null, 'month') : '';
        root.innerHTML = `${err}${hoursErr}<div class="nx-ctl-scroll"><div class="nx-ctl-margin">${head}${rows}${total}${unassigned}</div></div>${legend}`;
        root.removeAttribute('aria-busy');
    }

    // ---- 4. client blocks -------------------------------------------------------
    let oneOpen = true;
    function setOpen(section, open) {
        const btn = section.querySelector('.nx-ctl-client__head');
        const detail = section.querySelector('.nx-ctl-client__detail');
        if (!btn || !detail) return;
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        detail.hidden = !open;
        section.classList.toggle('is-open', open);
    }
    function syncAllLabel() {
        const all = Array.from(document.querySelectorAll('.nx-ctl-client'));
        const allOpen = all.length && all.every(b => b.classList.contains('is-open'));
        document.getElementById('ctl-toggle-all').textContent = allOpen ? S.collapseAll : S.expandAll;
    }
    function openBlock(key, scroll) {
        const sec = document.getElementById('ctl-c-' + key);
        if (!sec) return;
        if (oneOpen) document.querySelectorAll('.nx-ctl-client.is-open').forEach(b => { if (b !== sec) setOpen(b, false); });
        setOpen(sec, true);
        syncAllLabel();
        if (scroll) sec.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    }
    document.getElementById('ctl-blocks').addEventListener('click', e => {
        const btn = e.target.closest('.nx-ctl-client__head');
        if (!btn) return;
        const sec = btn.closest('.nx-ctl-client');
        if (sec.classList.contains('is-open')) { setOpen(sec, false); syncAllLabel(); } else { openBlock(sec.dataset.key, false); }
    });
    document.getElementById('ctl-margin').addEventListener('click', e => {
        const row = e.target.closest('[data-open]');
        if (!row) return;
        e.preventDefault();
        history.replaceState(null, '', '#ctl-c-' + row.dataset.open);
        openBlock(row.dataset.open, true);
    });
    document.getElementById('ctl-toggle-all').addEventListener('click', () => {
        const all = Array.from(document.querySelectorAll('.nx-ctl-client'));
        const open = !all.every(b => b.classList.contains('is-open'));
        if (open) oneOpen = false;
        all.forEach(b => setOpen(b, open));
        if (!open) oneOpen = true;
        syncAllLabel();
    });

    function divider(label, note) {
        return `<div class="nx-fin-divider"><span class="nx-eyebrow">${esc(label)}</span>` +
            `${note ? `<span class="nx-fin-divider__note">${esc(note)}</span>` : ''}<span class="nx-fin-divider__rule" aria-hidden="true"></span></div>`;
    }

    function tasksHtml(s) {
        const c = s.cur;
        const p = s.prev || { tasks: {} };
        if (c.hours == null) return errorBox(S.bpsStreamDown);
        // Biggest first (JSON object keys arrive sorted by name), then last month's leftovers.
        const names = Object.keys(c.tasks).sort((x, y) => c.tasks[y] - c.tasks[x] || x.localeCompare(y));
        Object.keys(p.tasks || {}).sort((x, y) => p.tasks[y] - p.tasks[x]).forEach(t => { if (!names.includes(t)) names.push(t); });
        if (!names.length && !(c.externalCosts || []).length) return `<p class="nx-fin-empty">${esc(fmt(S.noHoursIn, { month: CFG.monthLabel }))}</p>`;
        const rate = c.rate;
        const rows = names.map(t => {
            const h = c.tasks[t] || 0;
            const ph = (p.tasks || {})[t] || 0;
            return `<div class="nx-ctl-tasks__row"><span class="nx-ctl-tasks__name">${esc(t)}</span>
                <span class="nx-ctl-num nx-ctl-strong">${esc(num(h))}</span>
                <span class="nx-ctl-num">${esc(rate == null ? '—' : num(h * rate))}</span>
                <span class="nx-ctl-num nx-ctl-quiet">${esc(ph ? num(ph) : '·')}</span>
                <span class="nx-ctl-tasks__chg">${cmpHtml(h, ph, 56)}<span class="nx-fin-delta">${esc(finDelta(h, ph))}</span></span></div>`;
        }).join('');
        const ext = (c.externalCosts || []).map(x => `<div class="nx-ctl-tasks__row nx-ctl-tasks__ext"><span class="nx-ctl-tasks__name">${esc(S.externalCost)} · ${esc(x.label)}${x.source === 'bexio' ? ' <span class="nx-ctl-quiet">(Bexio)</span>' : ''}</span>
                <span></span><span class="nx-ctl-num">${esc(x.amount == null ? '—' : num(x.amount))}</span><span></span><span></span></div>`).join('');
        return `<div class="nx-ctl-scroll"><div class="nx-ctl-tasks">
            <div class="nx-ctl-tasks__row nx-ctl-tasks__head"><span>${esc(S.taetigkeit)}</span><span>${esc(S.hours)}</span><span>CHF</span>
              <span>${esc(fmt(S.prevHours, { month: CFG.prevShort }))}</span><span>${esc(S.change)}</span></div>
            ${rows}${ext}
            <div class="nx-ctl-tasks__row nx-ctl-tasks__total"><span>${esc(S.totalAufwendungen)}</span>
              <span class="nx-ctl-num">${esc(num(c.hours))}</span><span class="nx-ctl-num">${esc(c.cost == null ? '—' : num(c.cost))}</span>
              <span class="nx-ctl-num nx-ctl-quiet">${esc(p.hours == null ? '·' : num(p.hours))}</span>
              <span class="nx-fin-delta">${esc(finDelta(c.hours, p.hours))}</span></div>
          </div></div>`;
    }

    function linesHtml(inv) {
        const pdf = `${API}api/finance/bexio/invoice/${encodeURIComponent(inv.id)}/pdf`;
        const st = INV_STATUS[inv.status] || INV_STATUS.other;
        const cur = inv.currency || 'CHF';
        const pre = cur !== 'CHF' ? cur + ' ' : '';
        const lines = (inv.positions || []).filter(l => l.kind === 'line').map(l => `
            <div class="nx-ctl-lines__row"><span class="nx-ctl-lines__text">${esc(l.text)}</span>
              <span class="nx-ctl-num">${esc(Number.isInteger(l.amount) ? group(String(l.amount)) : num(l.amount))}</span>
              <span class="nx-ctl-num">${esc(num(l.unitPrice))}</span>
              <span class="nx-ctl-num nx-ctl-strong">${esc(num(l.total))}</span></div>`).join('');
        const vat = (inv.total || 0) - (inv.excl || 0);
        return `<div class="nx-ctl-inv${inv.status === 'draft' ? ' is-draft' : ''}">
            <div class="nx-ctl-inv__head"><span class="nx-ctl-num nx-ctl-strong">${esc(inv.nr)}</span>
              <span class="nx-ctl-inv__title">${esc(inv.title)}</span><span class="nx-ctl-quiet">${esc(dateLabel(inv.date))}</span>
              ${chip(st[0], S.status[st[1]] || inv.status)}<span class="nx-ctl-flex"></span>
              <a class="nx-btn nx-btn--ghost nx-btn--sm" href="${esc(pdf)}" target="_blank" rel="noopener"><i class="fas fa-file-pdf" aria-hidden="true"></i> ${esc(S.pdf)}</a></div>
            ${lines ? `<div class="nx-ctl-scroll"><div class="nx-ctl-lines">
              <div class="nx-ctl-lines__row nx-ctl-lines__headrow"><span>${esc(S.text)}</span><span>${esc(S.quantity)}</span><span>${esc(S.unitPrice)}</span><span>${esc(fmt(S.totalCur, { cur }))}</span></div>
              ${lines}</div></div>` : `<p class="nx-ctl-quiet nx-ctl-inv__nolines">${esc(S.linesUnavailable)}</p>`}
            <div class="nx-ctl-inv__foot">
              <span class="nx-ctl-strong">${esc(S.totalExcl)}</span><span class="nx-ctl-num nx-ctl-bold">${esc(pre + num(inv.excl))}</span>
              <span class="nx-ctl-quiet">${esc(S.vat)}${inv.excl ? ' ' + esc((Math.round((vat / inv.excl) * 1000) / 10).toFixed(1)) + '%' : ''}</span><span class="nx-ctl-num nx-ctl-quiet">${esc(pre + num(vat))}</span>
              <span class="nx-ctl-quiet">${esc(S.totalIncl)}</span><span class="nx-ctl-num nx-ctl-quiet">${esc(pre + num(inv.total))}</span></div>
          </div>`;
    }
    const dateFmt = iso => { if (!iso) return ''; const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };
    const dateLabel = dateFmt;

    function debitorHtml(s) {
        const c = s.cur;
        if (c.state === 'error') return errorBox(S.bexioLinesDown);
        const msgs = {
            missing: [chip('amber', S.noInvoice), fmt(S.noInvoiceTo, { stream: s.label, month: CFG.invoiceMonth })],
            unlinked: [chip('gray', S.notLinked, { dot: false }), fmt(S.noProjectFor, { stream: s.label })],
        };
        if (M.state === 'running' && !(c.invoices || []).length) {
            return `<div class="nx-ctl-msg">${chip('gray', S.notInvoicedYet, { dot: false })}<span>${esc(fmt(S.stillRunning, { month: CFG.monthName, invoices: CFG.invoiceMonth }))}</span></div>`;
        }
        if (msgs[c.state] && !(c.invoices || []).length) {
            return `<div class="nx-ctl-msg">${msgs[c.state][0]}<span>${esc(msgs[c.state][1])}</span></div>`;
        }
        let drift = '';
        if (has(c, 'moved') && c.live) {
            const at = c.invoiced;
            const now = c.live.invoiced;
            drift = `<details class="nx-fin-drift"><summary><i class="fas fa-code-compare" aria-hidden="true"></i> ${esc(S.driftTitle)}</summary>
              <table class="nx-table"><thead><tr><th>${esc(S.figure)}</th><th class="nx-num">${esc(S.atClose)}</th><th class="nx-num">${esc(S.liveNow)}</th><th class="nx-num">${esc(S.difference)}</th></tr></thead>
              <tbody><tr><td>${esc(S.invoicedExcl)}</td><td class="nx-num">${esc(num(at))}</td><td class="nx-num">${esc(num(now))}</td>
              <td class="nx-num">${esc(at != null && now != null ? sgn(now - at) : '—')}</td></tr></tbody></table>
              <p class="nx-fin-drift__note">${esc(S.driftNote)}</p></details>`;
        }
        return (c.invoices || []).map(linesHtml).join('') + drift;
    }

    function diffHtml(s) {
        const c = s.cur;
        let body;
        if (c.margin != null) {
            const loss = c.margin < 0 ? ' is-loss' : '';
            const d = s.delta && s.delta.margin != null ? s.delta.margin : null;
            body = `<span class="nx-ctl-num nx-ctl-diff__value${loss}">${esc(sgn(c.margin))}</span>
                <span class="nx-ctl-num nx-ctl-diff__pct${loss}">${esc(pct(c.marginPct))}</span>
                <span class="nx-ctl-diff__delta">${dHtml(d)}
                <span class="nx-ctl-quiet">${s.prev && s.prev.margin != null ? esc(CFG.prevShort + ' ' + sgn(s.prev.margin)) : ''}</span></span>`;
        } else {
            let msg = '';
            if (M.state === 'running' && !c.frozen) msg = fmt(S.diffRunning, { month: CFG.monthName });
            else if (c.state === 'error') msg = S.needsBexioDot;
            else if (c.hours == null) msg = S.needsHoursDot;
            else if (c.state === 'missing') msg = fmt(S.diffMissing, { cost: num(c.cost) });
            else if (c.state === 'draft') msg = fmt(S.diffDraft, { value: c.draft != null && c.cost != null ? sgn(c.draft - c.cost) : '—' });
            else if (c.state === 'foreign') msg = fmt(S.diffForeign, { amount: c.foreign.map(f => f.currency + ' ' + num(f.excl)).join(', ') });
            else if (c.state === 'unlinked') msg = S.diffUnlinked;
            else if (has(c, 'no_rate')) msg = S.diffNoRate;
            else if (has(c, 'cost_unknown')) msg = S.diffCostForeign;
            body = `<span class="nx-ctl-diff__msg">${esc(msg)}</span>`;
        }
        const formula = c.margin != null ? `${num(c.invoiced)} ${MINUS} ${num(c.cost)}` : '';
        return `<div class="nx-ctl-diff"><span class="nx-ctl-diff__label">${esc(S.differenz)}</span>
            <span class="nx-ctl-num nx-ctl-quiet nx-ctl-diff__formula">${esc(formula)}</span><span class="nx-ctl-flex"></span>${body}</div>`;
    }

    function unitsHtml(s) {
        const c = s.cur;
        const p = s.prev || {};
        const unit = byStream[s.key].unit;
        const k = c.kpis || {};
        const pk = p.kpis || {};
        const rows = [
            [fmt(S.secondsPer, { unit: unitOne(unit) }), k.secondsPerDocument, pk.secondsPerDocument, 1],
            [fmt(S.perHour, { unit: cap(unit) }), k.documentsPerHour, pk.documentsPerHour, 1],
            [fmt(S.chfPer, { unit: unitOne(unit) }), k.chfPerDocument, pk.chfPerDocument, 2],
        ].map(([label, v, pv, d]) => `<div class="nx-fin-line"><span class="nx-fin-line__label">${esc(label)}</span>
            <span class="nx-fin-line__value">${esc(v == null ? '—' : num(v, d))}</span>
            <span class="nx-fin-line__prev">${esc(pv == null ? '—' : num(pv, d))}</span>
            <span class="nx-fin-line__change">${cmpHtml(v, pv)}<span class="nx-fin-delta">${esc(finDelta(v, pv))}</span></span></div>`).join('');
        return `<div class="nx-ctl-scroll"><div class="nx-ctl-units"><div class="nx-fin-lines__head"><span>${esc(S.figure)}</span><span>${esc(CFG.monthName)}</span><span>${esc(CFG.prevMonthName)}</span><span>${esc(S.change)}</span></div>${rows}</div></div>`;
    }
    const cap = w => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w);
    const unitOne = u => (S.unitOne && S.unitOne[u]) || u;

    function statePills(c) {
        const pills = [];
        if (M.state === 'closed' || c.frozen) pills.push(chip('indigo', S.closedShort, { dot: false, icon: 'fas fa-lock' }));
        else if (M.state === 'running') pills.push(chip('amber', S.running));
        else pills.push(chip('green', S.liveShort));
        if (has(c, 'moved')) pills.push(chip('amber', S.movedShort));
        if (has(c, 'incomplete')) pills.push(chip('amber', S.bpsIncomplete, { dot: false, ring: true }));
        return pills.join('');
    }
    function headChips(c) {
        const out = [];
        if (has(c, 'incomplete')) out.push(chip('amber', S.bpsIncomplete, { dot: false, ring: true }));
        if (has(c, 'moved')) out.push(chip('amber', S.movedShort));
        if (has(c, 'no_hours')) out.push(chip('amber', S.noHoursChip));
        const f = flagOf(c);
        if (f) out.push(f.chip);
        return out.join('');
    }

    function blockHtml(s) {
        const c = s.cur;
        const d = s.delta && s.delta.margin != null ? s.delta.margin : null;
        const f = flagOf(c);
        const loss = c.margin != null && c.margin < 0 ? ' is-loss' : '';
        const marginT = c.margin != null ? `${esc(sgn(c.margin))}<span class="nx-ctl-client__pct${loss}">${esc(pct(c.marginPct))}</span>` : '—';
        const note = [];
        if (c.incomplete) note.push(c.incomplete);
        if (c.state === 'foreign') note.push(S.noteForeign);
        if (s.key === 'zhaw') note.push(S.noteXpert);
        if (has(c, 'no_hours')) note.push(S.noteNoHours);
        const contacts = c.contacts && c.contacts.length ? c.contacts.join(', ') : S.noContactYet;
        const rate = c.rate == null ? '—' : fmt(S.chfPerHour, { rate: rateNum(c.rate) }) + (has(c, 'override') ? ' · ' + S.override : '');
        const docs = c.documents == null ? '—' : `${num(c.documents, 0)} ${s.unit}`;
        return `<section class="nx-ctl-client" id="ctl-c-${esc(s.key)}" data-key="${esc(s.key)}" data-testid="controlling-client-${esc(s.key)}">
            <button type="button" class="nx-ctl-client__head" aria-expanded="false" aria-controls="ctl-cd-${esc(s.key)}">
              <span class="nx-ctl-client__id"><span class="nx-ctl-client__name">${esc(s.client)}</span>${s.title ? `<span class="nx-ctl-client__title">${esc(s.title)}</span>` : ''}</span>
              <span class="nx-ctl-client__sum">
                <span class="nx-ctl-client__chips">${headChips(c)}</span>
                <span class="nx-ctl-client__cell nx-ctl-client__cell--h"><span class="nx-ctl-eyebrow">${esc(S.hours)}</span><span class="nx-ctl-num nx-ctl-strong">${esc(c.hours == null ? '—' : num(c.hours))}</span></span>
                <span class="nx-ctl-client__cell nx-ctl-client__cell--m"><span class="nx-ctl-eyebrow">${esc(S.marginChf)}</span><span class="nx-ctl-num nx-ctl-strong${loss}">${c.margin != null ? marginT : '—' + (f ? ` <span class="nx-ctl-client__flagword">${esc(stripTags(f.chip))}</span>` : '')}</span></span>
                <span class="nx-ctl-client__cell nx-ctl-client__cell--d"><span class="nx-ctl-eyebrow">${esc(fmt(S.vsShort, { month: CFG.prevShort }))}</span>
                  ${dHtml(d)}</span>
                <i class="fas fa-chevron-down nx-ctl-client__chev" aria-hidden="true"></i>
              </span>
            </button>
            <div class="nx-ctl-client__detail" id="ctl-cd-${esc(s.key)}" hidden>
              <div class="nx-ctl-client__idcol">
                <p class="nx-ctl-meta">${esc('BPS · ' + s.bps)}</p>
                <p class="nx-ctl-meta">${esc('Bexio · ' + contacts)}</p>
                <div class="nx-fin-id__state">${statePills(c)}</div>
                <div class="nx-ctl-facts"><span class="nx-ctl-eyebrow">${esc(S.rate)}</span><span class="nx-ctl-eyebrow">${esc(S.volume)}</span>
                  <span class="nx-ctl-facts__v">${esc(rate)}</span><span class="nx-ctl-facts__v">${esc(docs)}</span></div>
                ${note.length ? `<p class="nx-fin-id__note">${esc(note.join(' '))}</p>` : ''}
              </div>
              <div class="nx-ctl-client__statement">
                ${divider(S.aufwendungen, c.rate == null ? S.noRate : fmt(S.hoursTimesRate, { rate: rateNum(c.rate) }))}
                ${tasksHtml(s)}
                ${divider(S.debitor, fmt(S.invoicesDated, { month: CFG.invoiceMonth }))}
                ${debitorHtml(s)}
                ${diffHtml(s)}
                ${divider(S.unitFigures, c.documents == null ? '' : fmt(S.docsIn, { n: num(c.documents, 0), unit: s.unit, month: CFG.monthName }))}
                ${unitsHtml(s)}
              </div>
            </div>
          </section>`;
    }
    const stripTags = html => { const t = document.createElement('div'); t.innerHTML = html; return t.textContent; };

    function renderBlocks() {
        const root = document.getElementById('ctl-blocks');
        const openKeys = new Set(Array.from(root.querySelectorAll('.nx-ctl-client.is-open')).map(b => b.dataset.key));
        root.innerHTML = M.streams.map(blockHtml).join('');
        document.getElementById('ctl-blocks-head').hidden = false;
        openKeys.forEach(k => { const b = document.getElementById('ctl-c-' + k); if (b) setOpen(b, true); });
        syncAllLabel();
        const hash = window.location.hash.replace('#ctl-c-', '');
        if (hash && byStream[hash] && !openKeys.size) openBlock(hash, true);
    }

    // ---- 5. hours by task -------------------------------------------------------
    function renderMatrix() {
        const root = document.getElementById('ctl-matrix');
        root.removeAttribute('aria-busy');
        const m = M.tasks;
        const T = M.totals.cur;
        if (!m) {
            document.getElementById('ctl-tasks-count').textContent = '';
            root.innerHTML = errorBox(fmt(S.bpsDown, { reason: M.hoursError || '' }), null, 'month');
            return;
        }
        document.getElementById('ctl-tasks-count').textContent = fmt(S.nTasks, { n: m.tasks.length });
        document.getElementById('ctl-tasks-meta').textContent = T.fteCapacity
            ? fmt(S.fteMeta, { cap: num(T.fteCapacity, 1), days: T.workingDays })
            : S.allClients;
        if (!m.tasks.length) {
            root.innerHTML = `<p class="nx-fin-empty">${esc(fmt(S.noHoursIn, { month: CFG.monthLabel }))}</p>`;
            return;
        }
        const max = Math.max(...m.cells.flat().map(v => v || 0)) || 1;
        const n = m.streams.length;
        const grid = `grid-template-columns:150px repeat(${n},minmax(72px,1fr)) 84px`;
        const head = `<div class="nx-ctl-matrix__row nx-ctl-matrix__head" style="${grid}"><span class="nx-ctl-matrix__sticky">${esc(S.taetigkeit)}</span>` +
            m.streams.map(k => `<span title="${esc(byStream[k].label)}">${esc(byStream[k].nav)}</span>`).join('') +
            `<span class="nx-ctl-matrix__tot">${esc(S.total)}</span></div>`;
        const rows = m.tasks.map((t, i) => `<div class="nx-ctl-matrix__row" style="${grid}"><span class="nx-ctl-matrix__sticky nx-ctl-matrix__task">${esc(t)}</span>` +
            m.cells[i].map((v, j) => {
                const title = `${byStream[m.streams[j]].label} · ${t} · ${v ? num(v) : 0} h`;
                if (!v) return `<span class="nx-ctl-matrix__cell is-zero" title="${esc(title)}">·</span>`;
                const a = 0.06 + 0.5 * Math.sqrt(v / max);
                return `<span class="nx-ctl-matrix__cell" style="background:rgba(227,99,63,${a.toFixed(3)})" title="${esc(title)}">${esc(num(v, 1))}</span>`;
            }).join('') + `<span class="nx-ctl-matrix__tot nx-ctl-num">${esc(num(m.taskTotals[i], 1))}</span></div>`).join('');
        const total = `<div class="nx-ctl-matrix__row nx-ctl-matrix__total" style="${grid}"><span class="nx-ctl-matrix__sticky">${esc(S.total)}</span>` +
            m.streamTotals.map(v => `<span class="nx-ctl-num">${esc(num(v, 1))}</span>`).join('') +
            `<span class="nx-ctl-matrix__tot nx-ctl-num">${esc(num(m.total, 1))}</span></div>`;
        const fte = T.fteCapacity
            ? `<div class="nx-ctl-matrix__row nx-ctl-matrix__fte" style="${grid}"><span class="nx-ctl-matrix__sticky">${esc(S.fte)}</span>` +
              m.streamTotals.map(v => `<span class="nx-ctl-num">${esc(num((v || 0) / T.fteCapacity, 2))}</span>`).join('') +
              `<span class="nx-ctl-matrix__tot nx-ctl-num">${esc(num(T.fte, 2))}</span></div>`
            : '';
        root.innerHTML = `<div class="nx-ctl-scroll nx-ctl-matrix-scroll"><div class="nx-ctl-matrix" style="min-width:${150 + n * 86 + 84}px">${head}${rows}${total}${fte}</div></div>
            <div class="nx-ctl-legend"><span class="nx-ctl-swatches" aria-hidden="true"><span style="background:rgba(227,99,63,.08)"></span><span style="background:rgba(227,99,63,.22)"></span><span style="background:rgba(227,99,63,.38)"></span><span style="background:rgba(227,99,63,.56)"></span></span>
            <span>${esc(S.heatLegend)}</span></div>`;
    }

    // ---- 6. volumes -----------------------------------------------------------
    function renderVolumes() {
        const root = document.getElementById('ctl-vol');
        root.removeAttribute('aria-busy');
        const T = M.totals.cur;
        const P = M.totals.prev || {};
        document.getElementById('ctl-volumes-count').textContent = T.documents == null ? '' : num(T.documents, 0);
        document.getElementById('ctl-volumes-meta').textContent = S.fromFinance;
        const vals = M.streams.map(s => s.cur.documents || 0);
        if (!vals.some(Boolean)) {
            root.innerHTML = `<p class="nx-fin-empty">${esc(fmt(S.noDocsIn, { month: CFG.monthLabel }))}</p>`;
            return;
        }
        const max = Math.max(...vals) || 1;
        const sum = vals.reduce((a, b) => a + b, 0) || 1;
        const failed = new Set(M.documentsFailed || []);
        const rows = M.streams.map(s => {
            const v = s.cur.documents;
            const p = s.prev ? s.prev.documents : null;
            const w = v ? (v / max) * 100 : 0;
            return `<div class="nx-ctl-vol__row"><span class="nx-ctl-vol__name">${esc(s.label)}</span>
                <span class="nx-ctl-vol__share"><span class="nx-ctl-vol__track"><span style="width:${w.toFixed(1)}%"></span></span><span class="nx-ctl-num nx-ctl-quiet">${esc(v ? pct(v / sum, 0) : '')}</span></span>
                <span class="nx-ctl-num nx-ctl-strong" title="${esc(failed.has(s.key) && v != null ? S.docsFrozen : '')}">${esc(v == null ? '—' : num(v, 0))}</span>
                <span class="nx-ctl-quiet">${esc(s.unit)}</span>
                <span class="nx-ctl-num nx-ctl-quiet">${esc(p == null ? '—' : num(p, 0))}</span>
                <span class="nx-fin-delta">${esc(finDelta(v, p))}</span></div>`;
        }).join('');
        root.innerHTML = `<div class="nx-ctl-scroll"><div class="nx-ctl-vol">
            <div class="nx-ctl-vol__row nx-ctl-vol__head"><span>${esc(S.stream)}</span><span>${esc(S.share)}</span><span>${esc(CFG.monthName)}</span><span>${esc(S.unit)}</span><span>${esc(CFG.prevMonthName)}</span><span>${esc(S.change)}</span></div>
            ${rows}
            <div class="nx-ctl-vol__row nx-ctl-vol__total"><span>${esc(S.total)}</span><span class="nx-ctl-quiet nx-ctl-vol__note">${esc(S.unitsDiffer)}</span>
              <span class="nx-ctl-num">${esc(num(T.documents, 0))}</span><span></span><span class="nx-ctl-num nx-ctl-quiet">${esc(P.documents == null ? '—' : num(P.documents, 0))}</span>
              <span class="nx-fin-delta">${esc(finDelta(T.documents, P.documents))}</span></div>
          </div></div>`;
    }

    // ---- month load ---------------------------------------------------------------
    async function loadMonth(fresh) {
        const res = await window.NX.apiSafe(`/api/controlling/month?month=${encodeURIComponent(CFG.month)}${fresh ? '&fresh=1' : ''}`);
        if (!res.ok || !res.data || res.data.error) {
            const msg = (res.data && res.data.error) || S.loadFailed;
            const detail = res.data && res.data.detail;
            ['ctl-margin', 'ctl-matrix', 'ctl-vol'].forEach(id => {
                const el = document.getElementById(id);
                el.innerHTML = errorBox(msg, detail, 'month');
                el.removeAttribute('aria-busy');
            });
            document.querySelector('#ctl-summary [data-role="body"]').innerHTML = errorBox(msg, detail, 'month');
            return;
        }
        M = res.data;
        const empty = !M.hoursError && M.totals.cur.hours === 0 &&
            M.streams.every(s => !(s.cur.invoices || []).length) && !M.unassigned.length;
        renderSummary(empty);
        if (empty) {
            const line = `<div class="nx-ctl-empty"><i class="fas fa-inbox" aria-hidden="true"></i><span>${esc(fmt(S.emptyMonth, { month: CFG.monthLabel, invoices: CFG.invoiceMonth }))}</span></div>`;
            document.getElementById('ctl-margin').innerHTML = line;
            document.getElementById('ctl-margin').removeAttribute('aria-busy');
            document.getElementById('ctl-blocks').innerHTML = '';
        } else {
            renderClients();
            renderBlocks();
        }
        renderMatrix();
        renderVolumes();
        if (Rates) Rates.refreshCosts();
    }

    // ---- 7. trend ----------------------------------------------------------------
    let TR = null;
    let hover = null;
    const monthIndex = () => (TR ? TR.months.indexOf(CFG.month) : -1);
    const shortMonth = new Intl.DateTimeFormat(lang && lang !== 'en' ? lang : 'en-GB', { month: 'short', timeZone: 'UTC' });
    const narrow = new Intl.DateTimeFormat(lang && lang !== 'en' ? lang : 'en-GB', { month: 'narrow', timeZone: 'UTC' });
    const mDate = key => new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1, 1));
    const short = key => `${shortMonth.format(mDate(key))} ${key.slice(2, 4)}`;
    const isIncomplete = i => TR.streams.some(s => (s.points[i].flags || []).includes('incomplete'));

    function renderTrend() {
        const root = document.getElementById('ctl-trend-body');
        root.removeAttribute('aria-busy');
        const n = TR.months.length;
        document.getElementById('ctl-trend-count').textContent = String(n);
        document.getElementById('ctl-trend-meta').textContent = fmt(S.trendMeta, { from: short(TR.months[0]), to: short(TR.months[n - 1]) });
        const sel = monthIndex();
        const margins = TR.totals.map(t => t.margin);
        const absMax = Math.max(1, ...margins.map(v => Math.abs(v || 0)));
        const pos = Math.max(0, ...margins.map(v => v || 0));
        const neg = Math.max(0, ...margins.map(v => -(v || 0)));
        const span = pos + neg || 1;
        const zero = (neg / span) * 100;
        const hMax = Math.max(1, ...TR.totals.map(t => t.hours || 0));
        const dMax = Math.max(1, ...TR.totals.map(t => t.documents || 0));
        const colCls = i => (i === hover ? ' is-hover' : i === sel ? ' is-sel' : '');
        const bars = TR.totals.map((t, i) => {
            const running = TR.states[i] === 'running';
            if (running || t.margin == null) {
                return `<span class="nx-ctl-trend__col${colCls(i)}" data-i="${i}">${running ? `<span class="nx-ctl-trend__pending" style="bottom:${zero.toFixed(1)}%" title="${esc(S.runningNotInvoiced)}"></span>` : ''}</span>`;
            }
            const h = (Math.abs(t.margin) / span) * 100;
            const bottom = t.margin < 0 ? zero - h : zero;
            const cls = i === sel ? ' is-sel' : t.margin < 0 ? ' is-loss' : '';
            return `<span class="nx-ctl-trend__col${colCls(i)}" data-i="${i}"><span class="nx-ctl-trend__bar${cls}" style="bottom:${bottom.toFixed(1)}%;height:${Math.max(h, 0.5).toFixed(1)}%"></span></span>`;
        }).join('');
        const strip = key => TR.totals.map((t, i) => {
            const v = t[key] || 0;
            const max = key === 'hours' ? hMax : dMax;
            return `<span class="nx-ctl-trend__scol${colCls(i)}" data-i="${i}"><span class="${i === sel ? 'is-sel' : ''}" style="height:${((v / max) * 100).toFixed(1)}%"></span></span>`;
        }).join('');
        const axis = TR.months.map((k, i) => `<span class="nx-ctl-trend__tick${i === sel ? ' is-sel' : ''}"><span>${esc(narrow.format(mDate(k)))}</span>` +
            `<span class="nx-ctl-trend__inc">${isIncomplete(i) ? `<span class="nx-ctl-ring" title="${esc(S.priveraIncomplete)}"></span>` : ''}</span>` +
            `<span class="nx-ctl-trend__year">${k.slice(5) === '01' ? esc(k.slice(0, 4)) : ''}</span></span>`).join('');
        const tiles = TR.streams.map(s => tileHtml(s, sel)).join('');
        root.innerHTML = `<div class="nx-ctl-trend" data-role="trend">
            <div class="nx-ctl-trend__title"><span>${esc(S.totalMargin)}</span><span class="nx-ctl-quiet">${esc(S.totalMarginNote)}</span></div>
            <div class="nx-ctl-trend__chart">
              <div class="nx-ctl-trend__line"><span class="nx-ctl-trend__lbl">${esc(S.margin)}</span>
                <div class="nx-ctl-trend__plot" data-role="plot"><span class="nx-ctl-trend__zero" style="bottom:${zero.toFixed(1)}%"></span>${bars}${tipHtml()}</div></div>
              <div class="nx-ctl-trend__line nx-ctl-trend__line--strip"><span class="nx-ctl-trend__lbl">${esc(S.hours)}</span><div class="nx-ctl-trend__strip">${strip('hours')}</div></div>
              <div class="nx-ctl-trend__line nx-ctl-trend__line--strip2"><span class="nx-ctl-trend__lbl">${esc(S.documents)}</span><div class="nx-ctl-trend__strip">${strip('documents')}</div></div>
              <div class="nx-ctl-trend__line nx-ctl-trend__line--axis"><span class="nx-ctl-trend__lbl"></span><div class="nx-ctl-trend__axis">${axis}</div></div>
            </div>
            ${divider(S.marginPerStream, S.tilesNote)}
            <div class="nx-ctl-tiles">${tiles}</div>
          </div>`;
        void absMax;
    }

    function tipHtml() {
        if (hover == null) return '';
        const i = hover;
        const t = TR.totals[i];
        const n = TR.months.length;
        const state = TR.states[i];
        const stateLabel = state === 'closed' ? S.closedShort : state === 'running' ? S.running : S.openShort;
        const rows = [
            [S.margin, t.margin == null ? '—' : `${sgn(t.margin, 0)} (${pct(t.marginPct)})`, t.margin != null && t.margin < 0 ? 'is-loss' : ''],
            [S.invoicedShort, t.invoiced == null ? '—' : num(t.invoiced, 0), ''],
            [S.cost, t.cost == null ? '—' : num(t.cost, 0), ''],
            [S.hours, t.hours == null ? '—' : num(t.hours, 1), ''],
            [S.documents, t.documents == null ? '—' : num(t.documents, 0), ''],
        ].map(r => `<div class="nx-ctl-tip__row"><span>${esc(r[0])}</span><span class="nx-ctl-num ${r[2]}">${esc(r[1])}</span></div>`).join('');
        const notes = [];
        if (isIncomplete(i)) notes.push(S.priveraIncomplete);
        const out = t.streams - t.streamsWithMargin;
        if (state !== 'running' && out) notes.push(fmt(out === 1 ? S.notInMarginOne : S.notInMargin, { n: out }));
        const left = ((i + 0.5) / n) * 100;
        const flip = i > n * 0.62;
        return `<div class="nx-ctl-tip" style="left:${left.toFixed(2)}%;transform:${flip ? 'translateX(calc(-100% - 14px))' : 'translateX(14px)'}" aria-hidden="true">
            <p class="nx-ctl-tip__title">${esc(TR.labels[i])} · ${esc(stateLabel)}</p>${rows}
            ${notes.length ? `<p class="nx-ctl-tip__note">${esc(notes.join(' · '))}</p>` : ''}</div>`;
    }

    function tileHtml(s, sel) {
        const cur = hover != null ? hover : sel >= 0 ? sel : s.points.length - 1;
        const p = s.points[cur] || {};
        const vals = s.points.map(x => x.margin).filter(v => v != null);
        const pos = Math.max(0, ...vals);
        const neg = Math.max(0, ...vals.map(v => -v));
        const span = pos + neg || 1;
        const zero = (neg / span) * 100;
        const unlinked = s.points.every(x => x.state === 'unlinked');
        const short_ = { missing: S.noInvoiceShort, draft: S.draftShort, foreign: S.foreign, unlinked: S.notLinked, error: S.bexioUnavailable };
        const valT = p.margin != null ? sgn(p.margin, 0) : TR.states[cur] === 'running' ? S.running.toLowerCase() : (short_[p.state] || '—');
        const bars = s.points.map((x, i) => {
            const v = x.margin;
            const inc = (x.flags || []).includes('incomplete');
            const colCls = i === hover ? ' is-hover' : i === sel ? ' is-sel' : '';
            if (v == null) {
                const dot = x.state !== 'unlinked' && TR.states[i] !== 'running' ? `<span class="nx-ctl-tile__dot" style="bottom:${zero.toFixed(1)}%"></span>` : '';
                return `<span class="nx-ctl-tile__col${colCls}" data-i="${i}">${dot}</span>`;
            }
            const h = (Math.abs(v) / span) * 100;
            const bottom = v < 0 ? zero - h : zero;
            const cls = inc ? ' is-inc' : v < 0 ? ' is-loss' : '';
            return `<span class="nx-ctl-tile__col${colCls}" data-i="${i}"><span class="nx-ctl-tile__bar${cls}" style="bottom:${bottom.toFixed(1)}%;height:${Math.max(h, 1).toFixed(1)}%"></span></span>`;
        }).join('');
        const abs = Math.max(pos, neg);
        const scale = vals.length ? fmt(S.maxScale, { v: abs >= 1000 ? (abs / 1000).toFixed(1) + 'k' : String(Math.round(abs)) }) : '';
        return `<div class="nx-ctl-tile" data-testid="controlling-tile-${esc(s.key)}">
            <div class="nx-ctl-tile__head"><span class="nx-ctl-tile__name">${esc(s.label)}</span><span class="nx-ctl-flex"></span>
              <span class="nx-ctl-quiet nx-ctl-tile__month">${esc(short(TR.months[cur]))}</span>
              <span class="nx-ctl-num nx-ctl-tile__val${p.margin != null && p.margin < 0 ? ' is-loss' : p.margin == null ? ' is-quiet' : ''}">${esc(valT)}</span></div>
            <div class="nx-ctl-tile__chart"><span class="nx-ctl-tile__zero" style="bottom:${zero.toFixed(1)}%"></span>${bars}
              ${unlinked ? `<span class="nx-ctl-tile__over">${esc(S.tileUnlinked)}</span>` : ''}</div>
            <div class="nx-ctl-tile__foot"><span>${esc(short(TR.months[0]))}</span><span>${esc(scale)}</span><span>${esc(short(TR.months[TR.months.length - 1]))}</span></div>
          </div>`;
    }

    const trendRoot = document.getElementById('ctl-trend-body');
    trendRoot.addEventListener('mouseover', e => {
        const col = e.target.closest('[data-i]');
        if (!col || !TR) return;
        const i = Number(col.dataset.i);
        if (i !== hover) { hover = i; renderTrend(); }
    });
    trendRoot.addEventListener('mouseleave', () => { if (hover != null) { hover = null; renderTrend(); } });
    trendRoot.addEventListener('click', e => {
        const col = e.target.closest('[data-i]');
        if (!col || !TR) return;
        const key = TR.months[Number(col.dataset.i)];
        if (key && key !== CFG.month) go(key);
    });

    async function loadTrend(fresh) {
        const root = document.getElementById('ctl-trend-body');
        const res = await window.NX.apiSafe(`/api/controlling/trend${fresh ? '?fresh=1' : ''}`);
        if (!res.ok || !res.data || res.data.error) {
            root.innerHTML = errorBox((res.data && res.data.error) || S.loadFailed, res.data && res.data.detail, 'trend');
            root.removeAttribute('aria-busy');
            return;
        }
        TR = res.data;
        renderTrend();
    }

    // ---- 8. rates drawer ----------------------------------------------------------
    const Rates = (function () {
        const root = document.getElementById('ctl-rates');
        const opener = document.getElementById('ctl-rates-open');
        if (!root || !opener) return null;
        if (root.parentElement !== document.body) document.body.appendChild(root);
        const body = root.querySelector('[data-role="body"]');
        let rates = [];
        let form = null; // {scope: 'default'|'override'|'cost', id, stream, value, from, to, label, error}
        const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled])';

        const monthLabel = iso => (iso ? short(iso) : S.open);
        function rowHtml(r, override) {
            const by = [r.changedBy, r.changedLabel].filter(Boolean).join(' · ');
            const to = r.to ? `<span>${esc(monthLabel(r.to))}</span>` : `<span class="nx-ctl-rates__open">${esc(S.open)}</span>`;
            if (override) {
                return `<div class="nx-ctl-rates__row nx-ctl-rates__row--o"><span class="nx-ctl-rates__who"><span class="nx-ctl-strong">${esc((byStream[r.stream] || {}).label || r.stream)}</span><span class="nx-ctl-quiet">${esc(by)}</span></span>
                    <span class="nx-ctl-num nx-ctl-rates__rate">${esc(num(r.value))}</span><span>${esc(monthLabel(r.from))}</span>${to}
                    <button type="button" class="nx-ctl-iconbtn" data-edit="${r.id}" aria-label="${esc(S.edit)}"><i class="fas fa-pen" aria-hidden="true"></i></button></div>`;
            }
            return `<div class="nx-ctl-rates__row"><span class="nx-ctl-num nx-ctl-rates__rate">${esc(num(r.value))}</span><span>${esc(monthLabel(r.from))}</span>${to}
                <span class="nx-ctl-quiet nx-ctl-rates__by">${esc(by)}</span>
                <button type="button" class="nx-ctl-iconbtn" data-edit="${r.id}" aria-label="${esc(S.edit)}"><i class="fas fa-pen" aria-hidden="true"></i></button></div>`;
        }
        function formHtml(scope) {
            if (!form || form.scope !== scope) return '';
            const err = form.error ? `<p class="nx-ctl-rates__err" role="alert">${esc(form.error)}</p>` : '';
            const del = form.id ? `<button type="button" class="nx-btn nx-btn--ghost nx-btn--sm nx-ctl-rates__del" data-act="delete">${esc(S.delete)}</button>` : '';
            if (scope === 'cost') {
                const opts = STREAMS.map(s => `<option value="${esc(s.key)}"${form.stream === s.key ? ' selected' : ''}>${esc(s.label)}</option>`).join('');
                return `<div class="nx-ctl-rates__form"><select data-f="stream" aria-label="${esc(S.stream)}">${opts}</select>
                    <input data-f="label" value="${esc(form.label || '')}" placeholder="${esc(S.costLabel)}" aria-label="${esc(S.costLabel)}">
                    <input data-f="value" value="${esc(form.value || '')}" inputmode="decimal" class="nx-ctl-rates__num" placeholder="CHF" aria-label="CHF">
                    <span class="nx-ctl-rates__acts"><button type="button" class="nx-btn nx-btn--ghost nx-btn--sm" data-act="cancel">${esc(S.cancel)}</button>
                    <button type="button" class="nx-ctl-save" data-act="save">${esc(S.save)}</button></span>${err}</div>`;
            }
            const opts = STREAMS.map(s => `<option value="${esc(s.key)}"${form.stream === s.key ? ' selected' : ''}>${esc(s.label)}</option>`).join('');
            return `<div class="nx-ctl-rates__form">${scope === 'override' ? `<select data-f="stream" aria-label="${esc(S.stream)}">${opts}</select>` : ''}
                <input data-f="value" value="${esc(form.value || '')}" inputmode="decimal" class="nx-ctl-rates__num" aria-label="${esc(S.rate)}">
                <input data-f="from" type="month" value="${esc(form.from || '')}" aria-label="${esc(S.validFrom)}">
                <input data-f="to" type="month" value="${esc(form.to || '')}" aria-label="${esc(S.validTo)}">
                <span class="nx-ctl-rates__acts">${del}<button type="button" class="nx-btn nx-btn--ghost nx-btn--sm" data-act="cancel">${esc(S.cancel)}</button>
                <button type="button" class="nx-ctl-save" data-act="save">${esc(S.save)}</button></span>${err}</div>`;
        }
        function section(label, scope, addLabel, cols, rowsHtml) {
            return `<div class="nx-ctl-rates__sec"><span class="nx-ctl-eyebrow">${esc(label)}</span><span class="nx-ctl-rates__rule"></span>
                <button type="button" class="nx-ctl-rates__add" data-add="${scope}"><i class="fas fa-plus" aria-hidden="true"></i>${esc(addLabel)}</button></div>
                ${cols}${formHtml(scope)}${rowsHtml}`;
        }
        function costsRows() {
            if (!M) return '';
            const items = [];
            M.streams.forEach(s => (s.cur.externalCosts || []).forEach(c => items.push([s, c])));
            if (!items.length) return `<p class="nx-ctl-quiet nx-ctl-rates__none">${esc(fmt(S.noCosts, { month: CFG.monthLabel }))}</p>`;
            return items.map(([s, c]) => `<div class="nx-ctl-rates__row nx-ctl-rates__row--c"><span class="nx-ctl-rates__who"><span class="nx-ctl-strong">${esc(c.label)}</span><span class="nx-ctl-quiet">${esc(s.label)}${c.source === 'bexio' ? ' · Bexio' : ''}</span></span>
                <span class="nx-ctl-num nx-ctl-rates__rate">${esc(c.amount == null ? '—' : num(c.amount))}</span>
                ${c.source === 'manual' ? `<button type="button" class="nx-ctl-iconbtn" data-delcost="${c.id}" aria-label="${esc(S.delete)}"><i class="fas fa-trash" aria-hidden="true"></i></button>` : '<span></span>'}</div>`).join('');
        }
        function render() {
            const hourly = rates.filter(r => r.kind === 'hourly');
            const def = hourly.filter(r => !r.stream).sort((a, b) => (a.from < b.from ? 1 : -1));
            const ovr = hourly.filter(r => r.stream).sort((a, b) => (a.from < b.from ? 1 : -1));
            const fte = rates.filter(r => r.kind === 'fte_day_hours' && !r.stream).sort((a, b) => (a.from < b.from ? 1 : -1));
            const dCols = `<div class="nx-ctl-rates__row nx-ctl-rates__cols"><span class="nx-ctl-rates__rate">CHF/h</span><span>${esc(S.from)}</span><span>${esc(S.to)}</span><span>${esc(S.changed)}</span><span></span></div>`;
            const oCols = `<div class="nx-ctl-rates__row nx-ctl-rates__row--o nx-ctl-rates__cols"><span>${esc(S.stream)}</span><span class="nx-ctl-rates__rate">CHF/h</span><span>${esc(S.from)}</span><span>${esc(S.to)}</span><span></span></div>`;
            const fCols = `<div class="nx-ctl-rates__row nx-ctl-rates__cols"><span class="nx-ctl-rates__rate">h/${esc(S.dayShort)}</span><span>${esc(S.from)}</span><span>${esc(S.to)}</span><span>${esc(S.changed)}</span><span></span></div>`;
            body.innerHTML =
                section(S.defaultRate, 'default', S.addRate, dCols, def.map(r => rowHtml(r, false)).join('')) +
                section(S.overrides, 'override', S.addOverride, oCols, ovr.length ? ovr.map(r => rowHtml(r, true)).join('') : `<p class="nx-ctl-quiet nx-ctl-rates__none">${esc(S.noOverrides)}</p>`) +
                section(S.fteHours, 'fte', S.addRate, fCols, fte.map(r => rowHtml(r, false)).join('')) +
                section(fmt(S.externalCosts, { month: CFG.monthLabel }), 'cost', S.addCost, '', costsRows()) +
                `<p class="nx-ctl-rates__foot"><i class="fas fa-circle-info" aria-hidden="true"></i><span>${esc(S.ratesFoot)}</span></p>`;
        }
        async function load() {
            const res = await window.NX.apiSafe(`/api/controlling/rates`);
            if (!res.ok || !res.data || res.data.error) {
                body.innerHTML = errorBox((res.data && res.data.error) || S.loadFailed);
                return;
            }
            rates = res.data.rates;
            render();
        }
        function readForm() {
            body.querySelectorAll('[data-f]').forEach(i => { form[i.dataset.f] = i.value; });
        }
        async function save() {
            readForm();
            let res;
            if (form.scope === 'cost') {
                res = await window.NX.apiSafe(`/api/controlling/costs`, { method: 'POST', body: JSON.stringify({ month: CFG.month, stream: form.stream, label: form.label, amount: String(form.value).replace(',', '.') }) });
            } else {
                const kind = form.scope === 'fte' ? 'fte_day_hours' : 'hourly';
                const payload = { kind, stream: form.scope === 'override' ? form.stream : null, value: String(form.value).replace(',', '.'), from: form.from, to: form.to || null };
                const url = form.id ? `/api/controlling/rates/${form.id}` : `/api/controlling/rates`;
                res = await window.NX.apiSafe(url, { method: form.id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
            }
            if (!res.ok) {
                form.error = (res.data && res.data.error) || S.saveFailed;
                render();
                return;
            }
            form = null;
            await load();
            loadMonth(false);
            loadTrend(false);
        }
        async function remove() {
            const res = await window.NX.apiSafe(`/api/controlling/rates/${form.id}`, { method: 'DELETE' });
            if (!res.ok) { form.error = (res.data && res.data.error) || S.saveFailed; render(); return; }
            form = null;
            await load();
            loadMonth(false);
            loadTrend(false);
        }
        body.addEventListener('click', async e => {
            const add = e.target.closest('[data-add]');
            const edit = e.target.closest('[data-edit]');
            const act = e.target.closest('[data-act]');
            const delcost = e.target.closest('[data-delcost]');
            if (add) {
                form = { scope: add.dataset.add, stream: STREAMS[0].key, value: '', from: CFG.month, to: '' };
                render();
                const first = body.querySelector('.nx-ctl-rates__form input, .nx-ctl-rates__form select');
                if (first) first.focus();
            } else if (edit) {
                const r = rates.find(x => x.id === Number(edit.dataset.edit));
                form = { scope: r.kind === 'fte_day_hours' ? 'fte' : r.stream ? 'override' : 'default', id: r.id, stream: r.stream, value: String(r.value), from: r.from, to: r.to || '' };
                render();
                const first = body.querySelector('.nx-ctl-rates__form input, .nx-ctl-rates__form select');
                if (first) first.focus();
            } else if (act) {
                if (act.dataset.act === 'cancel') { form = null; render(); root.querySelector('[data-role="rates-close"]').focus(); }
                if (act.dataset.act === 'save') save();
                if (act.dataset.act === 'delete') remove();
            } else if (delcost) {
                const res = await window.NX.apiSafe(`/api/controlling/costs/${delcost.dataset.delcost}`, { method: 'DELETE' });
                if (res.ok) { loadMonth(false); loadTrend(false); }
            }
        });
        function onKey(e) {
            if (e.key === 'Escape') { e.preventDefault(); close(); return; }
            if (e.key !== 'Tab') return;
            const items = Array.from(root.querySelectorAll(FOCUSABLE)).filter(x => x.offsetParent !== null);
            if (!items.length) return;
            // A re-render may have removed the focused button: bring focus back in.
            if (!root.contains(document.activeElement)) { e.preventDefault(); items[0].focus(); return; }
            if (e.shiftKey && document.activeElement === items[0]) { e.preventDefault(); items[items.length - 1].focus(); }
            else if (!e.shiftKey && document.activeElement === items[items.length - 1]) { e.preventDefault(); items[0].focus(); }
        }
        function open() {
            root.hidden = false;
            opener.setAttribute('aria-expanded', 'true');
            document.addEventListener('keydown', onKey, true);
            load();
            const c = root.querySelector('[data-role="rates-close"]');
            if (c) c.focus();
        }
        function close() {
            if (root.hidden) return;
            root.hidden = true;
            form = null;
            opener.setAttribute('aria-expanded', 'false');
            document.removeEventListener('keydown', onKey, true);
            opener.focus();
        }
        opener.setAttribute('aria-expanded', 'false');
        opener.addEventListener('click', open);
        root.addEventListener('click', e => {
            if (e.target === root || e.target.closest('[data-role="rates-close"]')) close();
        });
        return { refreshCosts: () => { if (!root.hidden && !form) render(); } };
    })();

    loadMonth(false);
    loadTrend(false);
})();

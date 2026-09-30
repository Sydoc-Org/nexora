/* Sydoc Finance (#408). Behaviour only -- strings and Jinja data arrive on
   window.NX_FINANCE; see templates/js/_finance_js.html.

   The page is a shell of section elements the server rendered. Every one
   loads itself from /api/finance/section/<key>?month=YYYY-MM, in parallel,
   so a source that is down shows its error in place while the rest render.
   Numbers are formatted in the page's locale; identity (which client, which
   measure) is always text, never colour, and the only colour on a figure is
   the accent bar that carries a share -- one hue, magnitude only. */
(function () {
    'use strict';

    const CFG = window.NX_FINANCE;
    const S = CFG.strings;
    const esc = window.NX.esc;
    const lang = document.documentElement.lang || undefined;
    const COLLAPSE_AFTER = 12;

    const numberFmt = new Intl.NumberFormat(lang);
    const decimalFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const pctFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 1 });
    const deltaFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 0, signDisplay: 'always' });

    // The shim's strings carry {name} placeholders (gettext's own %(name)s
    // cannot survive Jinja's _(), which always runs `rv % variables`).
    function fmt(str, vars) {
        return String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }

    // Counts are integers; hours (BPS) carry a fraction and read best to one place.
    function num(v) {
        const n = Number(v) || 0;
        return Number.isInteger(n) ? numberFmt.format(n) : decimalFmt.format(n);
    }

    // ---- month picker: a change is a navigation, the month lives in the URL ----
    const select = document.getElementById('fin-month');
    if (select) {
        select.addEventListener('change', function () {
            const url = new URL(window.location.href);
            url.searchParams.set('month', select.value);
            window.location.assign(url.toString());
        });
    }
    const printBtn = document.getElementById('fin-print');
    if (printBtn) printBtn.addEventListener('click', function () { window.print(); });

    // "All hours" links open the BPS page on this month's dates.
    (function () {
        const [y, m] = CFG.month.split('-').map(Number);
        const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
        const from = `${CFG.month}-01`;
        const to = `${CFG.month}-${String(last).padStart(2, '0')}`;
        document.querySelectorAll('[data-role="month-link"]').forEach(a => {
            const url = new URL(a.getAttribute('href'), window.location.href);
            url.searchParams.set('from', from);
            url.searchParams.set('to', to);
            a.setAttribute('href', url.pathname + url.search);
        });
    })();

    // ---- rendering ----------------------------------------------------------
    function deltaHtml(value, prev) {
        value = Number(value) || 0;
        prev = Number(prev) || 0;
        if (value === prev) {
            return `<p class="nx-kpi__delta">${esc(S.unchanged)} <span>${esc(S.vsPrev)}</span></p>`;
        }
        if (prev === 0) {
            return `<p class="nx-kpi__delta nx-kpi__delta--up">${esc(S.isNew)} <span>${esc(S.vsPrev)}</span></p>`;
        }
        const ratio = (value - prev) / prev;
        const dir = ratio > 0 ? 'up' : 'down';
        return `<p class="nx-kpi__delta nx-kpi__delta--${dir}">${esc(deltaFmt.format(ratio))} <span>${esc(S.vsPrev)}</span></p>`;
    }

    function figuresHtml(figures) {
        return '<div class="nx-kpi-strip nx-fin-kpis">' + figures.map(f => `
            <div class="nx-kpi" data-testid="finance-figure-${esc(f.code)}">
              <p class="nx-kpi__label">${esc(f.label)}</p>
              <div class="nx-kpi__body">
                <div>
                  <p class="nx-kpi__value" data-value="${esc(f.value)}">${esc(num(f.value))}</p>
                  ${deltaHtml(f.value, f.prev)}
                </div>
              </div>
            </div>`).join('') + '</div>';
    }

    function shareHtml(value, total) {
        const share = total > 0 ? value / total : 0;
        const width = Math.max(0, Math.min(100, share * 100));
        return `<span class="nx-fin-share"><span class="nx-fin-share__bar" aria-hidden="true"><span class="nx-fin-share__fill" style="width:${width.toFixed(1)}%"></span></span><span class="nx-fin-share__pct">${esc(pctFmt.format(share))}</span></span>`;
    }

    function breakdownHtml(br, sectionKey) {
        const cols = br.columns;
        const lead = br.totals[0] || 0;
        const head = `<th>${esc(br.label)}</th>` +
            cols.map(c => `<th class="nx-num text-right">${esc(c.label)}</th>`).join('') +
            `<th class="nx-num text-right">${esc(S.share)}</th>`;
        const body = br.rows.map((r, i) => {
            const more = i >= COLLAPSE_AFTER ? ' is-more' : '';
            const blank = r.key === null ? ' is-blank' : '';
            return `<tr class="${more}${blank}">` +
                `<td>${r.key === null ? esc(S.blank) : esc(r.key)}</td>` +
                r.values.map(v => `<td class="nx-num">${esc(num(v))}</td>`).join('') +
                `<td class="nx-num">${shareHtml(r.values[0], lead)}</td></tr>`;
        }).join('');
        const foot = `<tr><td>${esc(S.total)}</td>` +
            br.totals.map(v => `<td class="nx-num">${esc(num(v))}</td>`).join('') +
            `<td class="nx-num">${br.rows.length ? shareHtml(lead, lead) : ''}</td></tr>`;
        const more = br.rows.length > COLLAPSE_AFTER
            ? `<button type="button" class="nx-fin-more" data-more="${br.rows.length}">${esc(fmt(S.showAll, { n: num(br.rows.length) }))}</button>`
            : '';
        return `
          <div class="nx-fin-table" data-testid="finance-breakdown-${esc(sectionKey)}-${esc(br.dim)}">
            <div class="nx-fin-table__head">
              <span class="nx-eyebrow">${esc(fmt(S.per, { dim: br.label }))}</span>
              <span class="nx-fin-table__count">${esc(fmt(S.rows, { n: num(br.rows.length) }))}</span>
            </div>
            <table class="nx-table" aria-label="${esc(fmt(S.per, { dim: br.label }))}">
              <thead><tr>${head}</tr></thead>
              <tbody>${body}</tbody>
              <tfoot>${foot}</tfoot>
            </table>
            ${more}
          </div>`;
    }

    // A matrix: one measure, rows down and a second dimension along, with
    // totals both ways -- the layout of the workbook's billed sheet, wide
    // enough to need its own row and a horizontal scroll on narrow screens.
    function matrixHtml(br, sectionKey) {
        const label = fmt(S.byAcross, { dim: br.label, across: br.across_label });
        const keyText = k => (k === null ? esc(S.blank) : esc(k));
        const head = `<th scope="col" class="nx-fin-matrix__corner">${esc(br.label)}</th>` +
            br.col_keys.map(c => `<th scope="col" class="nx-num">${keyText(c)}</th>`).join('') +
            `<th scope="col" class="nx-num nx-fin-matrix__total">${esc(S.total)}</th>`;
        const body = br.row_keys.map((r, i) =>
            `<tr${r === null ? ' class="is-blank"' : ''}><th scope="row">${keyText(r)}</th>` +
            br.cells[i].map(v => `<td class="nx-num${v ? '' : ' is-zero'}">${v ? esc(num(v)) : '·'}</td>`).join('') +
            `<td class="nx-num nx-fin-matrix__total">${esc(num(br.row_totals[i]))}</td></tr>`
        ).join('');
        const foot = `<tr><th scope="row">${esc(S.total)}</th>` +
            br.col_totals.map(v => `<td class="nx-num">${esc(num(v))}</td>`).join('') +
            `<td class="nx-num nx-fin-matrix__total">${esc(num(br.total))}</td></tr>`;
        return `
          <div class="nx-fin-table nx-fin-table--wide" data-testid="finance-matrix-${esc(sectionKey)}-${esc(br.dim)}">
            <div class="nx-fin-table__head">
              <span class="nx-eyebrow">${esc(label)}</span>
              <span class="nx-fin-table__count">${esc(br.measure.label)}</span>
            </div>
            <div class="nx-fin-matrix" tabindex="0" role="region" aria-label="${esc(label)}">
              <table class="nx-table">
                <thead><tr>${head}</tr></thead>
                <tbody>${body}</tbody>
                <tfoot>${foot}</tfoot>
              </table>
            </div>
          </div>`;
    }

    function dateText(iso) {
        return iso ? window.NX.formatDate(iso) : '';
    }

    // Billable bookings (BPS): one table per customer with a subtotal, every
    // booking a line with its comment -- the invoice lists them singly.
    function bookingsHtml(bk, sectionKey) {
        const cols = bk.columns;
        const idx = {};
        cols.forEach((c, i) => { idx[c.field] = i; });
        const shown = cols.filter(c => c.field !== bk.group_by);
        const parts = [figuresHtml(bk.figures)];
        if (!bk.groups.length) {
            parts.push(`<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(fmt(S.empty, { month: CFG.monthLabel }))}</p>`);
            return parts.join('');
        }
        if (bk.by_task && bk.by_task.length) {
            // Hours per task as the same vertical breakdown table every other
            // section uses (label, hours, bookings, share, total row).
            const taskCol = cols.find(c => c.field === 'Aufgabe');
            const hoursCol = cols.find(c => c.numeric);
            const perTask = {
                dim: 'Aufgabe',
                label: taskCol ? taskCol.label : '',
                columns: [
                    { code: 'hours', label: hoursCol ? hoursCol.label : '' },
                    { code: 'count', label: S.bookingsCol },
                ],
                rows: bk.by_task.map(t => ({ key: t.key, values: [t.hours, t.count] })),
                totals: [
                    bk.by_task.reduce((a, t) => a + t.hours, 0),
                    bk.by_task.reduce((a, t) => a + t.count, 0),
                ],
            };
            parts.push('<div class="nx-fin-tables">' + breakdownHtml(perTask, sectionKey) + '</div>');
        }
        parts.push('<div class="nx-fin-bookings">');
        bk.groups.forEach(g => {
            const head = shown.map(c => `<th scope="col"${c.numeric ? ' class="nx-num"' : ''}>${esc(c.label)}</th>`).join('');
            const body = g.rows.map((r, i) => {
                const more = i >= COLLAPSE_AFTER ? ' class="is-more"' : '';
                return `<tr${more}>` + shown.map(c => {
                    const v = r[idx[c.field]];
                    if (c.numeric) return `<td class="nx-num">${esc(num(v))}</td>`;
                    if (c.field === 'Datum') return `<td class="nx-fin-bk__date">${esc(dateText(v))}</td>`;
                    if (c.field === 'Beschreibung') return `<td class="nx-fin-bk__comment">${esc(v || '')}</td>`;
                    return `<td>${esc(v === null ? '' : v)}</td>`;
                }).join('') + '</tr>';
            }).join('');
            const hoursCol = shown.findIndex(c => c.numeric);
            const foot = '<tr>' + shown.map((c, i) => {
                if (i === 0) return `<td>${esc(S.total)}</td>`;
                if (i === hoursCol) return `<td class="nx-num">${esc(num(g.hours))}</td>`;
                return '<td></td>';
            }).join('') + '</tr>';
            const more = g.rows.length > COLLAPSE_AFTER
                ? `<button type="button" class="nx-fin-more" data-more="${g.rows.length}">${esc(fmt(S.showAll, { n: num(g.rows.length) }))}</button>`
                : '';
            parts.push(`
              <div class="nx-fin-table nx-fin-table--wide" data-testid="finance-bookings-${esc(sectionKey)}">
                <div class="nx-fin-table__head">
                  <span class="nx-fin-bk__customer">${esc(g.key === null ? S.blank : g.key)}</span>
                  <span class="nx-fin-table__count">${esc(fmt(S.hoursUnit, { n: num(g.hours) }))} · ${esc(fmt(S.bookings, { n: num(g.count) }))}</span>
                </div>
                <div class="nx-fin-matrix" tabindex="0" role="region" aria-label="${esc(g.key || S.blank)}">
                  <table class="nx-table nx-fin-bk">
                    <thead><tr>${head}</tr></thead>
                    <tbody>${body}</tbody>
                    <tfoot>${foot}</tfoot>
                  </table>
                </div>
                ${more}
              </div>`);
        });
        parts.push('</div>');
        if (bk.truncated) {
            parts.push(`<p class="nx-fin-note"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><span>${esc(S.truncated)}</span></p>`);
        }
        return parts.join('');
    }

    // Where a closed month's live data has moved since the close.
    function driftHtml(diff) {
        if (!diff || !diff.length) return '';
        const rows = diff.map(d => {
            const delta = (Number(d.live) || 0) - (Number(d.closed) || 0);
            const sign = delta > 0 ? '+' : '';
            return `<tr><td>${esc(d.label)}</td><td class="nx-num">${esc(num(d.closed))}</td>` +
                `<td class="nx-num">${esc(num(d.live))}</td><td class="nx-num">${esc(sign + num(delta))}</td></tr>`;
        }).join('');
        return `
          <details class="nx-fin-drift" data-testid="finance-drift">
            <summary><i class="fas fa-code-compare" aria-hidden="true"></i> ${esc(fmt(S.driftTitle, { n: diff.length }))}</summary>
            <table class="nx-table">
              <thead><tr><th></th><th class="nx-num">${esc(S.atClose)}</th><th class="nx-num">${esc(S.liveNow)}</th><th class="nx-num">${esc(S.difference)}</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
            <p class="nx-fin-drift__note">${esc(S.driftNote)}</p>
          </details>`;
    }

    function sectionHtml(p) {
        const parts = [];
        p.blocks.forEach(block => {
            const anything = block.figures.some(f => Number(f.value) > 0) ||
                block.breakdowns.some(b => (b.kind === 'matrix' ? b.row_keys : b.rows).length > 0);
            parts.push('<div class="nx-fin-block">');
            if (p.blocks.length > 1) {
                parts.push(`<p class="nx-eyebrow nx-fin-block__basis">${esc(block.basis)}</p>`);
            }
            parts.push(figuresHtml(block.figures));
            if (!anything) {
                parts.push(`<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(fmt(S.empty, { month: CFG.monthLabel }))}</p>`);
            } else if (block.breakdowns.length) {
                parts.push('<div class="nx-fin-tables">' +
                    block.breakdowns.map(b => (b.kind === 'matrix' ? matrixHtml(b, p.key) : breakdownHtml(b, p.key))).join('') +
                    '</div>');
            }
            parts.push('</div>');
        });
        if (p.bookings) {
            parts.push('<div class="nx-fin-block">' + bookingsHtml(p.bookings, p.key) + '</div>');
        }
        if (p.closed) parts.push(driftHtml(p.live_diff));
        if (p.note) {
            parts.push(`<p class="nx-fin-note"><i class="fas fa-circle-info" aria-hidden="true"></i><span>${esc(p.note)}</span></p>`);
        }
        return parts.join('');
    }

    function errorHtml(p) {
        const detail = p.detail ? `<span class="nx-fin-error__detail">${esc(p.detail)}</span>` : '';
        return `
          <div class="nx-fin-error" role="alert">
            <i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
            <span>${esc(p.error || S.loadFailed)}</span>
            <button type="button" class="nx-btn nx-btn--secondary nx-btn--sm" data-retry="1">${esc(S.retry)}</button>
            ${detail}
          </div>`;
    }

    function metaText(p) {
        const bases = (p.blocks || []).map(b => b.basis).concat(p.bookings ? [p.bookings.basis] : []);
        const basis = bases.filter((v, i, a) => a.indexOf(v) === i);
        const label = p.source && p.source.label ? p.source.label : p.source.code;
        return [label].concat(basis).join(' · ');
    }

    // ---- loading ------------------------------------------------------------
    const status = { total: CFG.sections.length, done: 0, failed: 0 };

    function updateStatus() {
        const el = document.getElementById('fin-status');
        const text = document.getElementById('fin-status-text');
        if (!el || !text) return;
        el.classList.remove('is-done', 'is-failed');
        if (status.done < status.total) {
            text.textContent = fmt(S.loaded, { done: status.done, total: status.total });
            return;
        }
        if (status.failed) {
            el.classList.add('is-failed');
            text.textContent = fmt(S.someFailed, { failed: status.failed, total: status.total });
        } else {
            el.classList.add('is-done');
            text.textContent = fmt(S.allLoaded, { total: status.total });
        }
    }

    function render(section, payload) {
        const body = section.querySelector('[data-role="body"]');
        const meta = section.querySelector('[data-role="meta"]');
        const state = section.querySelector('[data-role="state"]');
        section.setAttribute('aria-busy', 'false');
        if (payload.error) {
            section.dataset.state = 'error';
            meta.textContent = payload.source && payload.source.label ? payload.source.label : payload.source.code;
            state.innerHTML = '';
            body.innerHTML = errorHtml(payload);
            return;
        }
        section.dataset.state = 'ok';
        meta.textContent = metaText(payload);
        if (payload.closed) {
            const moved = payload.live_diff && payload.live_diff.length;
            state.innerHTML = `<span class="nx-label nx-label--indigo nx-label--nodot"><i class="fas fa-lock" aria-hidden="true"></i> ${esc(S.closed)}</span>` +
                (moved ? ` <span class="nx-label nx-label--amber">${esc(S.drifted)}</span>` : '') +
                (payload.live_diff === null ? ` <span class="nx-label nx-label--gray">${esc(S.liveUnknown)}</span>` : '');
        } else {
            state.innerHTML = `<span class="nx-label nx-label--green">${esc(S.live)}</span>`;
        }
        body.innerHTML = sectionHtml(payload);
    }

    async function load(section) {
        const key = section.dataset.key;
        section.setAttribute('aria-busy', 'true');
        const res = await window.NX.apiSafe('/api/finance/section/' + encodeURIComponent(key) +
            '?month=' + encodeURIComponent(CFG.month));
        const payload = res.ok && res.data ? res.data : { error: S.loadFailed, source: { code: key } };
        render(section, payload);
        return !payload.error;
    }

    async function loadAll() {
        const sections = Array.from(document.querySelectorAll('.nx-fin-section[data-key]'));
        status.done = 0;
        status.failed = 0;
        updateStatus();
        await Promise.all(sections.map(async section => {
            let ok = false;
            try { ok = await load(section); } catch (e) { ok = false; console.error(e); render(section, { error: S.loadFailed, source: { code: section.dataset.key } }); }
            status.done += 1;
            if (!ok) status.failed += 1;
            updateStatus();
        }));
    }

    // Delegated: retry a failed section, expand a collapsed table.
    document.addEventListener('click', function (e) {
        const retry = e.target.closest('[data-retry]');
        if (retry) {
            const section = retry.closest('.nx-fin-section');
            status.done -= 1;
            status.failed -= 1;
            updateStatus();
            load(section).then(ok => {
                status.done += 1;
                if (!ok) status.failed += 1;
                updateStatus();
            });
            return;
        }
        const more = e.target.closest('.nx-fin-more');
        if (more) {
            const table = more.closest('.nx-fin-table');
            if (!table) return;
            const expanded = table.classList.toggle('is-expanded');
            more.textContent = expanded ? S.showFewer : fmt(S.showAll, { n: num(more.dataset.more) });
        }
    });

    // ---- month close / reopen: an in-page confirm, then a POST and a reload ----
    const toggle = document.getElementById('fin-close-toggle');
    const panel = document.getElementById('fin-confirm');
    if (toggle && panel) {
        const go = document.getElementById('fin-confirm-go');
        const cancel = document.getElementById('fin-confirm-cancel');
        const err = document.getElementById('fin-confirm-error');
        const action = toggle.dataset.action;
        function openPanel(open) {
            panel.hidden = !open;
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (open) go.focus(); else toggle.focus();
        }
        toggle.addEventListener('click', () => openPanel(panel.hidden));
        cancel.addEventListener('click', () => openPanel(false));
        panel.addEventListener('keydown', e => { if (e.key === 'Escape') openPanel(false); });
        go.addEventListener('click', async () => {
            const label = go.textContent;
            go.disabled = true;
            cancel.disabled = true;
            go.textContent = S.working;
            err.hidden = true;
            const res = await window.NX.apiSafe(`/api/finance/${action}?month=${encodeURIComponent(CFG.month)}`, { method: 'POST' });
            if (res.ok) {
                window.location.reload();
                return;
            }
            err.textContent = (res.data && res.data.error) || (action === 'close' ? S.closeFailed : S.reopenFailed);
            err.hidden = false;
            go.disabled = false;
            cancel.disabled = false;
            go.textContent = label;
        });
    }

    loadAll();
})();

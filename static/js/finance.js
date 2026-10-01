/* Sydoc Finance (#408, redesign #427). Behaviour only -- strings and Jinja
   data arrive on window.NX_FINANCE; see templates/js/_finance_js.html.

   The page is a shell of ledger rows the server rendered. Every one loads
   itself from /api/finance/section/<key>?month=YYYY-MM, in parallel, so a
   source that is down shows its error in place while the rest render.
   Numbers are formatted in the page's locale; identity (which client, which
   measure) is always text, never colour. A figure is a statement line: this
   month, the month before, and a comparison bar in neutral ink -- the only
   colour is Sydoc orange marking the previous month and carrying a share. */
(function () {
    'use strict';

    const CFG = window.NX_FINANCE;
    const S = CFG.strings;
    const Sy = window.NXSydoc;
    const esc = window.NX.esc;
    const lang = document.documentElement.lang || undefined;
    const COLLAPSE_AFTER = 12;
    const BOOKINGS_SHOWN = 4;

    const numberFmt = new Intl.NumberFormat(lang);
    const decimalFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const hoursFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const pctFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 1 });
    const deltaFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 0, signDisplay: 'always' });
    // Swiss English writes "3 Aug", like the band's dates (nx_sydoc.js).
    const dateLoc = !lang || lang === 'en' ? 'en-GB' : lang;
    const dayFmt = new Intl.DateTimeFormat(dateLoc, { day: 'numeric', month: 'short', timeZone: 'UTC' });
    const weekdayFmt = new Intl.DateTimeFormat(dateLoc, { weekday: 'short', timeZone: 'UTC' });

    const fmt = Sy.fmt;

    // Counts are integers; hours (BPS) carry a fraction and read best to one place.
    function num(v) {
        const n = Number(v) || 0;
        return Number.isInteger(n) ? numberFmt.format(n) : decimalFmt.format(n);
    }

    const printBtn = document.getElementById('fin-print');
    if (printBtn) printBtn.addEventListener('click', function () { window.print(); });

    // "All hours in Sydoc BPS" opens the BPS page on this month's dates.
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

    // ---- month picker: a pick is a navigation, the month lives in the URL ----
    (function () {
        const picker = document.getElementById('fin-picker');
        if (!picker) return;
        const byKey = {};
        (CFG.months || []).forEach(m => { byKey[m.value] = m; });
        const years = (CFG.months || []).map(m => Number(m.value.slice(0, 4)));
        const minYear = Math.min(...years);
        const maxYear = Math.max(...years);
        let viewYear = Number(CFG.month.slice(0, 4));
        const grid = picker.querySelector('[data-role="months"]');

        const STATUS = {
            closed: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--closed"><i class="fas fa-lock" aria-hidden="true"></i>${esc(S.closedShort)}</span>`,
            open: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--open"><span class="nx-sydoc-dot"></span>${esc(S.openShort)}</span>`,
            running: () => `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--running"><span class="nx-sydoc-dot"></span>${esc(S.running)}</span>`,
        };

        function render() {
            picker.querySelector('[data-role="year"]').textContent = String(viewYear);
            picker.querySelector('[data-role="year-prev"]').disabled = viewYear <= minYear;
            picker.querySelector('[data-role="year-next"]').disabled = viewYear >= maxYear;
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
            if (!cell || cell.disabled) return;
            const url = new URL(window.location.href);
            url.searchParams.set('month', cell.dataset.month);
            window.location.assign(url.toString());
        });
        picker.querySelector('[data-role="year-prev"]').addEventListener('click', () => { viewYear -= 1; render(); });
        picker.querySelector('[data-role="year-next"]').addEventListener('click', () => { viewYear += 1; render(); });
        Sy.initPicker({
            root: picker,
            opener: document.querySelector('[data-testid="finance-period-button"]'),
            onOpen: () => { viewYear = Number(CFG.month.slice(0, 4)); render(); },
        });
    })();

    // ---- rendering ----------------------------------------------------------
    // Neutral ink: the arrow says the direction, the colour says nothing.
    function deltaHtml(value, prev) {
        value = Number(value) || 0;
        prev = Number(prev) || 0;
        // The msgids are lower case ("unchanged", "new"); CSS capitalises the word.
        const word = w => `<span class="nx-fin-delta__word">${esc(w)}</span>`;
        if (value === prev) return `<span class="nx-fin-delta">${word(S.unchanged)}</span>`;
        if (prev === 0) return `<span class="nx-fin-delta">▲ ${word(S.isNew)}</span>`;
        const ratio = (value - prev) / prev;
        return `<span class="nx-fin-delta">${ratio > 0 ? '▲' : '▼'} ${esc(deltaFmt.format(ratio))}</span>`;
    }

    // This month as a fill, last month as an orange tick on the same scale.
    function cmpHtml(value, prev) {
        value = Math.max(0, Number(value) || 0);
        prev = Math.max(0, Number(prev) || 0);
        const max = Math.max(value, prev);
        if (!max) return '<span class="nx-fin-cmp" aria-hidden="true"></span>';
        const fill = (value / max) * 100;
        const mark = (prev / max) * 100;
        return `<span class="nx-fin-cmp" aria-hidden="true"><span class="nx-fin-cmp__fill" style="width:${fill.toFixed(1)}%"></span>` +
            `<span class="nx-fin-cmp__prev" style="left:calc(${mark.toFixed(1)}% - 1px)"></span></span>`;
    }

    function linesHtml(figures) {
        const head = `<div class="nx-fin-lines__head">
              <span>${esc(S.figure)}</span><span>${esc(S.monthName)}</span>
              <span>${esc(S.prevMonthName)}</span><span>${esc(S.change)}</span>
            </div>`;
        return head + figures.map(f => `
            <div class="nx-fin-line" data-testid="finance-figure-${esc(f.code)}">
              <span class="nx-fin-line__label">${esc(f.label)}</span>
              <span class="nx-fin-line__value" data-value="${esc(f.value)}">${esc(num(f.value))}</span>
              <span class="nx-fin-line__prev">${esc(num(f.prev))}</span>
              <span class="nx-fin-line__change">${cmpHtml(f.value, f.prev)}${deltaHtml(f.value, f.prev)}</span>
            </div>`).join('');
    }

    function shareHtml(value, total) {
        const share = total > 0 ? value / total : 0;
        const width = Math.max(0, Math.min(100, share * 100));
        return `<span class="nx-fin-share"><span class="nx-fin-share__bar" aria-hidden="true"><span class="nx-fin-share__fill" style="width:${width.toFixed(1)}%"></span></span><span class="nx-fin-share__pct">${esc(pctFmt.format(share))}</span></span>`;
    }

    // A vertical breakdown: key, its measures, the share of the first one.
    // `br.href(row, i)` turns the key into a link; `br.muted` greys a column.
    function breakdownHtml(br, sectionKey) {
        const cols = br.columns;
        const lead = br.totals[0] || 0;
        const muted = i => (br.muted && br.muted.includes(i) ? ' nx-fin-muted' : '');
        const head = `<th>${esc(br.label)}</th>` +
            cols.map(c => `<th class="nx-num text-right">${esc(c.label)}</th>`).join('') +
            `<th class="nx-num text-right">${esc(S.share)}</th>`;
        const body = br.rows.map((r, i) => {
            const more = i >= COLLAPSE_AFTER ? ' is-more' : '';
            const blank = r.key === null ? ' is-blank' : '';
            const keyText = r.key === null ? esc(S.blank) : esc(r.key);
            const key = br.href ? `<a href="${esc(br.href(r, i))}">${keyText}</a>` : keyText;
            return `<tr class="${more}${blank}">` +
                `<td>${key}</td>` +
                r.values.map((v, j) => `<td class="nx-num${muted(j)}">${esc(num(v))}</td>`).join('') +
                `<td class="nx-num">${shareHtml(r.values[0], lead)}</td></tr>`;
        }).join('');
        const foot = `<tr><td>${esc(S.total)}</td>` +
            br.totals.map((v, j) => `<td class="nx-num${muted(j)}">${esc(num(v))}</td>`).join('') +
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

    function emptyHtml() {
        return `<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(fmt(S.empty, { month: CFG.monthLabel }))}</p>`;
    }

    function utcDate(iso) {
        const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
        return new Date(Date.UTC(y, m - 1, d));
    }

    // One customer's bookings as a timeline: a day per stop on the rail, each
    // booking its comment, what it was booked on, and its hours. The first
    // few show; the rest open with "Show all n".
    function timelineHtml(g, i, idx, hoursField, sectionKey) {
        const field = (r, f) => (f in idx ? r[idx[f]] : null);
        const days = [];
        g.rows.forEach(r => {
            const day = String(field(r, 'Datum') || '').slice(0, 10);
            const last = days[days.length - 1];
            if (last && last.day === day) last.rows.push(r); else days.push({ day, rows: [r] });
        });
        let n = 0;
        const body = days.map(d => {
            const firstIndex = n;
            const items = d.rows.map(r => {
                const more = n++ >= BOOKINGS_SHOWN ? ' is-more' : '';
                const comment = field(r, 'Beschreibung');
                const line = ['Aufgabe', 'Projektpaket', 'Benutzer'].map(f => field(r, f)).filter(Boolean).join(' · ');
                return `<div class="nx-fin-tl__item${more}">
                    <div>
                      <p class="nx-fin-tl__comment${comment ? '' : ' is-empty'}">${esc(comment || S.noComment)}</p>
                      <p class="nx-fin-tl__line">${esc(line)}</p>
                    </div>
                    <span class="nx-fin-tl__hours">${esc(fmt(S.hoursUnit, { n: hoursFmt.format(Number(field(r, hoursField)) || 0) }))}</span>
                  </div>`;
            }).join('');
            const date = d.day ? utcDate(d.day) : null;
            return `<div class="nx-fin-tl__day${firstIndex >= BOOKINGS_SHOWN ? ' is-more' : ''}">
                <div class="nx-fin-tl__date">${date ? `<span>${esc(dayFmt.format(date))}</span><span class="nx-fin-tl__wd">${esc(weekdayFmt.format(date))}</span>` : ''}</div>
                <div class="nx-fin-tl__rail" aria-hidden="true"><span></span></div>
                <div class="nx-fin-tl__items">${items}</div>
              </div>`;
        }).join('');
        const more = g.rows.length > BOOKINGS_SHOWN
            ? `<div class="nx-fin-tl__foot"><button type="button" class="nx-fin-more" data-more="${g.rows.length}" data-label="all-n">${esc(fmt(S.showAllN, { n: num(g.rows.length) }))}</button></div>`
            : '';
        return `
          <div class="nx-fin-tl" id="fin-bk-${i}" data-testid="finance-bookings-${esc(sectionKey)}">
            <div class="nx-fin-tl__head">
              <span class="nx-fin-tl__name">${esc(g.key === null ? S.blank : g.key)}</span>
              <span class="nx-fin-tl__count">${esc(fmt(S.bookings, { n: num(g.count) }))}</span>
              <span class="nx-fin-tl__spacer"></span>
              <span class="nx-fin-tl__total">${esc(fmt(S.hoursUnit, { n: num(g.hours) }))}</span>
            </div>
            ${body}
            ${more}
          </div>`;
    }

    // Billable bookings (BPS): the figures, hours per task and per customer,
    // then every booking per customer as on the invoice.
    function bookingsHtml(bk, sectionKey) {
        const cols = bk.columns;
        const idx = {};
        cols.forEach((c, i) => { idx[c.field] = i; });
        const hoursCol = cols.find(c => c.numeric);
        const parts = [linesHtml(bk.figures)];
        if (!bk.groups.length) {
            parts.push(emptyHtml());
            return parts.join('');
        }
        const valueCols = [
            { code: 'hours', label: hoursCol ? hoursCol.label : '' },
            { code: 'count', label: S.bookingsCol },
        ];
        const tables = [];
        if (bk.by_task && bk.by_task.length) {
            const taskCol = cols.find(c => c.field === 'Aufgabe');
            tables.push(breakdownHtml({
                dim: 'Aufgabe',
                label: taskCol ? taskCol.label : '',
                columns: valueCols,
                muted: [1],
                rows: bk.by_task.map(t => ({ key: t.key, values: [t.hours, t.count] })),
                totals: [
                    bk.by_task.reduce((a, t) => a + t.hours, 0),
                    bk.by_task.reduce((a, t) => a + t.count, 0),
                ],
            }, sectionKey));
        }
        const customerCol = cols.find(c => c.field === bk.group_by);
        tables.push(breakdownHtml({
            dim: bk.group_by,
            label: customerCol ? customerCol.label : '',
            columns: valueCols,
            muted: [1],
            href: (r, i) => `#fin-bk-${i}`,
            rows: bk.groups.map(g => ({ key: g.key, values: [g.hours, g.count] })),
            totals: [
                bk.groups.reduce((a, g) => a + g.hours, 0),
                bk.groups.reduce((a, g) => a + g.count, 0),
            ],
        }, sectionKey));
        parts.push('<div class="nx-fin-tables">' + tables.join('') + '</div>');
        parts.push(`<div class="nx-fin-divider"><span class="nx-eyebrow">${esc(S.billableBookings)}</span>` +
            `<span class="nx-fin-divider__note">${esc(S.oneListPer)}</span><span class="nx-fin-divider__rule"></span></div>`);
        parts.push('<div class="nx-fin-tls">' +
            bk.groups.map((g, i) => timelineHtml(g, i, idx, hoursCol ? hoursCol.field : '', sectionKey)).join('') +
            '</div>');
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
            parts.push(linesHtml(block.figures));
            if (!anything) {
                parts.push(emptyHtml());
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
        const dot = el.querySelector('[data-role="dot"]');
        el.classList.remove('is-done', 'is-failed');
        let kind = 'running';
        if (status.done < status.total) {
            text.textContent = fmt(S.loaded, { done: status.done, total: status.total });
        } else if (status.failed) {
            el.classList.add('is-failed');
            kind = 'failed';
            text.textContent = fmt(S.someFailed, { failed: status.failed, total: status.total });
        } else {
            el.classList.add('is-done');
            kind = 'live';
            text.textContent = fmt(S.allLoaded, { total: status.total });
        }
        if (dot) dot.className = `nx-sydoc-dot nx-sydoc-dot--${kind}`;
    }

    function render(section, payload) {
        const body = section.querySelector('[data-role="body"]');
        const meta = section.querySelector('[data-role="meta"]');
        const state = section.querySelector('[data-role="state"]');
        const note = section.querySelector('[data-role="note"]');
        section.setAttribute('aria-busy', 'false');
        if (payload.note && note) {
            note.textContent = payload.note;
            note.hidden = false;
        }
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

    // Delegated: retry a failed section, expand a collapsed table or timeline.
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
            const list = more.closest('.nx-fin-table, .nx-fin-tl');
            if (!list) return;
            const expanded = list.classList.toggle('is-expanded');
            const all = more.dataset.label === 'all-n' ? S.showAllN : S.showAll;
            more.textContent = expanded ? S.showFewer : fmt(all, { n: num(more.dataset.more) });
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

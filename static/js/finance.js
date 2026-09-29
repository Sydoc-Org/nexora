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

    function sectionHtml(p) {
        const parts = [];
        p.blocks.forEach(block => {
            const anything = block.figures.some(f => Number(f.value) > 0) ||
                block.breakdowns.some(b => b.rows.length > 0);
            parts.push('<div class="nx-fin-block">');
            if (p.blocks.length > 1) {
                parts.push(`<p class="nx-eyebrow nx-fin-block__basis">${esc(block.basis)}</p>`);
            }
            parts.push(figuresHtml(block.figures));
            if (!anything) {
                parts.push(`<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(fmt(S.empty, { month: CFG.monthLabel }))}</p>`);
            } else if (block.breakdowns.length) {
                parts.push('<div class="nx-fin-tables">' +
                    block.breakdowns.map(b => breakdownHtml(b, p.key)).join('') + '</div>');
            }
            parts.push('</div>');
        });
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
        const basis = (p.blocks || []).map(b => b.basis).filter((v, i, a) => a.indexOf(v) === i);
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
        state.innerHTML = `<span class="nx-label nx-label--green">${esc(S.live)}</span>`;
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
            try { ok = await load(section); } catch (e) { ok = false; render(section, { error: S.loadFailed, source: { code: section.dataset.key } }); }
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
            const expanded = table.classList.toggle('is-expanded');
            more.textContent = expanded ? S.showFewer : fmt(S.showAll, { n: num(more.dataset.more) });
        }
    });

    loadAll();
})();

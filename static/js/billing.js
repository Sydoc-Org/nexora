/* Sydoc Billing (#436). Behaviour only -- strings and data arrive on
   window.NX_BILLING (templates/js/_billing_js.html).

   Three reads, all read-only and independent, so one failing leaves the
   others on the page:
     /api/billing/month         the invoices dated in this month, per client,
                                with their lines; invoices to unlinked contacts
     /api/billing/figures/<key> the Finance figures of the billed month, one
                                call per section (bps = billed hours per client)
     /api/billing/outstanding   everything still owed, whatever its month
   A client row renders once its invoices and all its figures are in; the
   ticks need both sides. */
(function () {
    'use strict';

    const CFG = window.NX_BILLING;
    const S = CFG.strings;
    const Sy = window.NXSydoc;
    const esc = window.NX.esc;
    const fmt = Sy.fmt;
    const lang = document.documentElement.lang || undefined;
    const BILLING_API = '/api/billing/';  // NX.apiSafe adds API_PREFIX itself

    const moneyFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const qtyFmt = new Intl.NumberFormat(lang, { maximumFractionDigits: 3 });
    const hoursFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const intFmt = new Intl.NumberFormat(lang);
    const STATUS_TONE = {
        draft: 'gray', open: 'blue', paid: 'green', partial: 'amber',
        cancelled: 'gray', unpaid: 'red', other: 'gray',
    };
    // Units Bexio's lines carry for hours; anything else named is a count.
    const HOUR_UNITS = new Set(['h', 'std', 'std.', 'stunde', 'stunden', 'hour', 'hours', 'heure', 'heures', 'ora', 'ore']);
    const BPS = 'bps';

    const state = { month: null, figures: {}, figuresDone: false };
    const rows = {};
    document.querySelectorAll('.nx-bill-client[data-client]').forEach(el => { rows[el.dataset.client] = el; });
    const clients = CFG.clients || [];

    // ---- formatting ---------------------------------------------------------
    function money(value, currency) {
        const text = moneyFmt.format(Number(value) || 0);
        return currency ? `${currency} ${text}` : text;
    }
    // dd.mm.yyyy in every language (the Swiss form, as in the design), not
    // the browser's locale: an English browser would write 09/01/2026.
    function dateText(iso) {
        const [y, m, d] = String(iso || '').slice(0, 10).split('-');
        return y && m && d ? `${d}.${m}.${y}` : '';
    }
    // "1 invoice" / "2 invoices": the shim carries both forms.
    const plurals = new Intl.PluralRules(lang);
    const plural = (n, one, other, vars) => fmt(plurals.select(Number(n)) === 'one' ? one : other, vars);
    const isHours = unit => HOUR_UNITS.has(String(unit || '').trim().toLowerCase());
    const figureValue = f => (f.unit === 'h' ? fmt(S.hoursUnit, { n: hoursFmt.format(Number(f.value) || 0) }) : intFmt.format(Number(f.value) || 0));
    const quantity = p => (isHours(p.unit) ? hoursFmt.format(p.amount) : qtyFmt.format(p.amount)) + (p.unit ? ` ${p.unit}` : '');
    const statusWord = st => S.status[st] || st;
    const tickIcon = title => `<i class="fas fa-check nx-bill-tick" aria-hidden="true"></i><span class="nx-fin-sr">${esc(title)}</span>`;

    function statusHtml(st) {
        return `<span class="nx-label nx-label--${STATUS_TONE[st] || 'gray'}">${esc(statusWord(st))}</span>`;
    }

    function chf(totals, field) {
        const t = (totals || []).find(x => x.currency === 'CHF');
        return t ? t[field] : 0;
    }

    function errorHtml(message, detail, retry) {
        return `<div class="nx-fin-error" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
            <span>${esc(message || S.loadFailed)}</span>
            ${retry ? `<button type="button" class="nx-btn nx-btn--secondary nx-btn--sm" data-retry="${esc(retry)}">${esc(S.retry)}</button>` : ''}
            ${detail ? `<span class="nx-fin-error__detail">${esc(detail)}</span>` : ''}</div>`;
    }

    function pdfUrl(id) { return window.API_PREFIX + 'api/billing/invoice/' + id + '/pdf'; }

    // ---- band ---------------------------------------------------------------
    function setStatus(kind, text) {
        const el = document.getElementById('bill-status');
        if (!el) return;
        el.classList.toggle('is-failed', kind === 'failed');
        el.querySelector('[data-role="dot"]').className = `nx-sydoc-dot nx-sydoc-dot--${kind}`;
        el.querySelector('[data-role="text"]').textContent = text;
    }

    function totalsHtml(data) {
        const counted = (data.totals || []).reduce((a, t) => a + t.count, 0);
        // Like the picker (bexio.month_states): a client without a Bexio link
        // cannot be checked, so it is in neither count.
        const checked = data.clients.filter(c => c.state !== 'unlinked');
        const linked = checked.length;
        const invoiced = checked.filter(c => c.state === 'invoiced').length;
        const item = (key, value, small, testid) => `
            <div data-testid="billing-total-${esc(testid)}"><span class="nx-bill-totals__k">${esc(key)}</span>
              <span class="nx-bill-totals__v">${esc(value)}${small ? `<small>${esc(small)}</small>` : ''}</span></div>`;
        const foreign = (data.totals || []).filter(t => t.currency && t.currency !== 'CHF');
        const sub = [];
        if (data.drafts || data.cancelled) sub.push(fmt(S.draftsCancelled, { n: intFmt.format(data.drafts || 0), m: intFmt.format(data.cancelled || 0) }));
        return `
          <div data-testid="billing-total-invoiced"><span class="nx-bill-totals__k">${esc(S.invoiced)}</span>
            <span class="nx-bill-totals__big">${esc(moneyFmt.format(chf(data.totals, 'total')))}<small>CHF</small></span></div>
          <div class="nx-bill-totals__grid">
            ${item(S.excl, moneyFmt.format(chf(data.totals, 'excl')), 'CHF', 'excl')}
            ${item(S.invoices, intFmt.format(counted), sub.join(''), 'count')}
            ${item(S.clientsInvoiced, fmt(S.nOfTotal, { n: invoiced, total: linked }),
                    linked - invoiced ? fmt(S.withoutInvoice, { n: linked - invoiced }) : '', 'clients')}
            ${foreign.map(t => item(S.otherCurrencies, moneyFmt.format(t.total), fmt(S.notInTotals, { currency: t.currency }), 'foreign-' + t.currency)).join('')}
          </div>`;
    }

    function renderBand(data) {
        const box = document.getElementById('bill-totals');
        const ok = Boolean(data && !data.error && data.configured);
        box.setAttribute('aria-busy', 'false');
        box.innerHTML = ok ? totalsHtml(data) : '';
        // Without invoices the strip would be an empty dark gap.
        box.hidden = !ok;
        document.querySelector('.nx-bill-band__rule').hidden = !ok;
        const missing = new Set((data && data.clients || []).filter(c => c.state === 'missing' || c.state === 'draft').map(c => c.key));
        document.querySelectorAll('[data-jump]').forEach(a => {
            const old = a.querySelector('.nx-bill-jump-dot');
            if (old) old.remove();
            if (missing.has(a.dataset.jump)) {
                a.insertAdjacentHTML('beforeend', `<span class="nx-sydoc-dot nx-sydoc-dot--running nx-bill-jump-dot" title="${esc(S.notInvoicedDot)}"></span>`);
            }
        });
    }

    // ---- the Finance figures of a client -----------------------------------
    /* [{title, error, figures: [{label, value, unit}]}]: one titled group per
       section and one for the billed hours when the client has several
       (Privera), else one untitled list the figures run across. */
    function figureGroups(c) {
        const bps = state.figures[BPS] || {};
        const hours = (bps.hours && bps.hours[c.client]) || [];
        const sections = c.sections.map(key => state.figures[key] || { error: S.loadFailed, figures: [] });
        const titled = c.sections.length > 1 || hours.length > 1;
        const copy = f => Object.assign({}, f);
        if (!titled) {
            const s = sections[0];
            const groups = [{
                title: null,
                error: s.error || null,
                figures: (s.figures || []).map(copy).concat(hours.map(h => Object.assign(copy(h), { label: S.billedHours }))),
            }];
            // The hours failing says so on its own, next to the figures that did load.
            if (bps.error) groups.push({ title: S.billedHours, error: bps.error, figures: [] });
            return groups;
        }
        const groups = sections.map((s, i) => ({
            title: s.title || (c.titles || {})[c.sections[i]] || c.client,
            error: s.error || null,
            figures: (s.figures || []).map(copy),
        }));
        if (hours.length || bps.error) groups.push({ title: S.billedHours, error: bps.error || null, figures: hours.map(copy) });
        return groups;
    }

    const same = (a, b) => Math.abs((Number(a) || 0) - (Number(b) || 0)) < 1e-9;

    /* The ticks: a line's quantity that equals one of the client's figures
       exactly, hours against hours and counts against counts (a line without
       a unit may match either). A heuristic -- there is no line-to-figure
       mapping -- and labelled as one. Cancelled invoices and drafts are not matched. */
    function matchTicks(invoices, groups) {
        const figures = groups.flatMap(g => g.figures);
        const lines = new Map();
        invoices.forEach(inv => {
            // Only an invoice that counts bills anything (bexio.counts()).
            if (inv.status === 'cancelled' || inv.status === 'draft') return;
            (inv.positions || []).forEach(p => {
                if (p.kind !== 'line' || !p.amount) return;
                const kind = isHours(p.unit) ? 'h' : (p.unit ? 'n' : null);
                const hit = figures.find(f => same(f.value, p.amount) &&
                    (kind === null || (kind === 'h') === (f.unit === 'h')));
                if (!hit) return;
                lines.set(p, hit);
                if (!hit.billedAs) hit.billedAs = (p.text || '').split('\n')[0];
            });
        });
        return lines;
    }

    function figuresHtml(c, groups) {
        const row = f => {
            const tick = f.billedAs ? tickIcon(fmt(S.billedAs, { text: f.billedAs })) : '';
            return `<div class="nx-bill-fig"${f.billedAs ? ` title="${esc(fmt(S.billedAs, { text: f.billedAs }))}"` : ''}>
                <span class="nx-bill-fig__label">${esc(f.label)}</span>
                <span class="nx-bill-fig__value">${esc(figureValue(f))}</span>
                <span class="nx-bill-fig__tick">${tick}</span></div>`;
        };
        const body = groups.length === 1 && !groups[0].title
            ? (groups[0].error ? `<div class="nx-bill-figs__group">${errorHtml(groups[0].error, null, 'figures')}</div>`
                : groups[0].figures.map(f => `<div class="nx-bill-figs__group">${row(f)}</div>`).join(''))
            : groups.map(g => `<div class="nx-bill-figs__group">
                ${g.title ? `<p class="nx-bill-figs__title">${esc(g.title)}</p>` : ''}
                ${g.error ? errorHtml(g.error, null, 'figures') : g.figures.map(row).join('')}</div>`).join('');
        const link = CFG.financeUrl
            ? `<a class="nx-bill-figs__link" href="${esc(CFG.financeUrl + '#fin-' + c.sections[0])}">${esc(S.breakdowns)} <i class="fas fa-arrow-right" aria-hidden="true"></i></a>`
            : '';
        return `<div class="nx-bill-figs__head">
              <span class="nx-eyebrow">${esc(fmt(S.financeHead, { month: CFG.billed.name }))}</span>
              <span class="nx-bill-figs__spacer"></span>${link}</div>
            <div class="nx-bill-figs__body">${body}</div>`;
    }

    // ---- one invoice --------------------------------------------------------
    function linesHtml(inv, ticks) {
        const positions = inv.positions || [];
        if (!positions.length) return `<p class="nx-fin-empty">${esc(S.noLines)}</p>`;
        const withDiscount = positions.some(p => p.kind === 'line' && p.discount);
        const cols = withDiscount ? 5 : 4;
        const rowsHtml = positions.map(p => {
            const text = esc(p.text || '').replace(/\n/g, '<br>');
            const opt = p.optional ? ` <span class="nx-label nx-label--gray nx-label--nodot">${esc(S.optional)}</span>` : '';
            if (p.kind === 'line') {
                const hit = ticks.get(p);
                const title = hit ? fmt(S.equals, { label: hit.label }) : '';
                return `<tr><td class="nx-fin-bexio__text">${text}${opt}</td>
                    <td class="nx-num"${hit ? ` title="${esc(title)}"` : ''}>${hit ? tickIcon(title) : ''}${esc(quantity(p))}</td>
                    <td class="nx-num nx-bill-lines__price">${esc(money(p.unitPrice, ''))}</td>
                    ${withDiscount ? `<td class="nx-num">${p.discount ? esc(qtyFmt.format(p.discount) + ' %') : ''}</td>` : ''}
                    <td class="nx-num">${esc(money(p.total, ''))}</td></tr>`;
            }
            if (p.kind === 'subtotal' || p.kind === 'discount') {
                const label = text || esc(p.kind === 'subtotal' ? S.subtotal : S.discount);
                return `<tr class="nx-fin-bexio__sub"><td colspan="${cols - 1}">${label}</td><td class="nx-num">${esc(money(p.total, ''))}</td></tr>`;
            }
            return `<tr class="nx-fin-bexio__textline"><td colspan="${cols}" class="nx-fin-bexio__text">${text}</td></tr>`;
        }).join('');
        const vatLabel = inv.vatRate != null ? fmt(S.vatRate, { rate: qtyFmt.format(inv.vatRate) + ' %' }) : S.vat;
        return `<table class="nx-bill-lines">
            <thead><tr><th>${esc(S.text)}</th><th class="nx-num">${esc(S.quantity)}</th>
              <th class="nx-num">${esc(S.unitPrice)}</th>${withDiscount ? `<th class="nx-num">${esc(S.discount)}</th>` : ''}
              <th class="nx-num">${esc(S.totalCol)} ${esc(inv.currency || '')}</th></tr></thead>
            <tbody>${rowsHtml}</tbody>
            <tfoot>
              <tr class="nx-bill-lines__sum"><td colspan="${cols - 1}">${esc(S.excl)}</td><td class="nx-num">${esc(money(inv.excl, ''))}</td></tr>
              <tr class="nx-bill-lines__sum"><td colspan="${cols - 1}">${esc(vatLabel)}</td><td class="nx-num">${esc(money(inv.vat, ''))}</td></tr>
              <tr class="nx-bill-lines__total"><td colspan="${cols - 1}">${esc(S.totalCol)}</td><td class="nx-num">${esc(money(inv.total, ''))}</td></tr>
            </tfoot></table>`;
    }

    function invoiceHtml(inv, c, ticks) {
        const cancelled = inv.status === 'cancelled';
        const collapsed = cancelled;
        const meta = [fmt(S.dated, { date: dateText(inv.date) })];
        if (inv.due && !cancelled && inv.status !== 'draft') meta.push(fmt(S.due, { date: dateText(inv.due) }));
        if (inv.status === 'partial') meta.push(fmt(S.partPaid, { paid: money(inv.paid, inv.currency), open: moneyFmt.format(inv.open) }));
        if (c.contacts.length > 1) {
            const to = c.contacts.find(k => k.id === inv.contactId);
            if (to) meta.push(fmt(S.to, { contact: to.name }));
        }
        let note = '';
        if (cancelled) note = `<span>${esc(S.cancelledNote)}</span>`;
        else if (inv.status === 'draft') note = `<span>${esc(S.draftNote)}</span>`;
        else if (inv.currency && inv.currency !== 'CHF') note = `<span class="nx-bill-inv__foreign">${esc(fmt(S.foreignNote, { currency: inv.currency }))}</span>`;
        let lines;
        if (inv.positions === null || inv.positions === undefined) lines = errorHtml(inv.positionsError || S.linesFailed);
        else lines = linesHtml(inv, ticks);
        const toggle = collapsed
            ? `<button type="button" class="nx-btn nx-btn--ghost nx-btn--sm" data-lines-toggle="${inv.id}" aria-expanded="false"
                 data-testid="billing-lines-${inv.id}"><i class="fas fa-list" aria-hidden="true"></i> <span>${esc(S.lines)}</span></button>`
            : '';
        return `<article class="nx-bill-inv${cancelled ? ' is-cancelled' : ''}" data-invoice="${inv.id}" data-testid="billing-invoice-${inv.id}">
            <header class="nx-bill-inv__head">
              <span class="nx-bill-inv__nr">${esc(inv.nr)}</span>
              <span class="nx-bill-inv__title">${esc(inv.title)}</span>
              <span class="nx-bill-inv__spacer"></span>
              ${statusHtml(inv.status)}
              <span class="nx-bill-inv__total">${esc(money(inv.total, inv.currency))}</span>
            </header>
            <div class="nx-bill-inv__lines" data-lines-for="${inv.id}"${collapsed ? ' hidden' : ''}>${lines}</div>
            <footer class="nx-bill-inv__meta">
              <span>${esc(meta.join(' · '))}</span>${note}
              <span class="nx-bill-inv__spacer"></span>
              <span class="nx-bill-inv__actions">${toggle}
                <a class="nx-btn nx-btn--ghost nx-btn--sm" href="${esc(pdfUrl(inv.id))}" target="_blank" rel="noopener"
                   data-testid="billing-pdf-${inv.id}"><i class="fas fa-file-pdf" aria-hidden="true"></i> ${esc(S.pdf)}</a>
                <a class="nx-btn nx-btn--ghost nx-btn--sm" href="${esc(inv.bexioUrl)}" target="_blank" rel="noopener">
                  <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i> ${esc(S.openInBexio)}</a>
              </span>
            </footer>
          </article>`;
    }

    function missingHtml(c) {
        const contact = c.contacts.map(k => k.name).join(' · ');
        let last = '';
        if (c.last) {
            last = `<p class="nx-bill-missing__last">${fmt(esc(S.latest), {
                nr: `<span class="nx-bill-missing__nr">${esc(c.last.nr)}</span>`,
                date: esc(dateText(c.last.date)),
                status: esc(statusWord(c.last.status).toLowerCase()),
            })} <a href="#bill-open">${esc(S.seeOpen)}</a></p>`;
        }
        return `<div><p class="nx-bill-missing"><i class="fas fa-inbox" aria-hidden="true"></i>
            ${esc(fmt(S.noInvoice, { contact, month: CFG.monthLabel }))}</p>${last}</div>`;
    }

    function stateHtml(c) {
        if (c.state === 'invoiced') return `<span class="nx-label nx-label--green">${esc(S.stateInvoiced)}</span>`;
        if (c.state === 'draft') return `<span class="nx-label nx-label--gray">${esc(S.draftOnly)}</span>`;
        if (c.state === 'missing') return `<span class="nx-label nx-label--amber">${esc(fmt(S.missing, { month: CFG.monthLabel }))}</span>`;
        return `<span class="nx-label nx-label--gray nx-label--nodot">${esc(S.unlinked)}</span>`;
    }

    // ---- a client row -------------------------------------------------------
    function renderClient(desc) {
        const el = rows[desc.client];
        if (!el || !state.figuresDone || !state.month) return;
        const data = state.month;
        const invoicesBox = el.querySelector('[data-role="invoices"]');
        const figuresBox = el.querySelector('[data-role="figures"]');
        const groups = figureGroups(desc);
        const c = data.configured && !data.error ? (data.clients || []).find(x => x.client === desc.client) : null;
        const ticks = c ? matchTicks(c.invoices, groups) : new Map();
        el.setAttribute('aria-busy', 'false');
        el.querySelector('[data-role="contacts"]').textContent = c ? c.contacts.map(k => k.name).join(' · ') : '';
        el.querySelector('[data-role="state"]').innerHTML = c ? stateHtml(c) : '';
        el.dataset.state = c ? c.state : 'unknown';
        if (!c) invoicesBox.innerHTML = '';
        else {
            // A missing client may still have a cancelled invoice: show both.
            invoicesBox.innerHTML = (c.state === 'missing' ? missingHtml(c) : '') +
                c.invoices.map(inv => invoiceHtml(inv, c, ticks)).join('');
        }
        figuresBox.hidden = false;
        figuresBox.innerHTML = figuresHtml(desc, groups);
    }

    function renderClients() { clients.forEach(renderClient); }

    // ---- other contacts -----------------------------------------------------
    function renderOthers(data) {
        const el = document.getElementById('bill-other');
        const body = el.querySelector('[data-role="body"]');
        const meta = el.querySelector('[data-role="meta"]');
        const count = document.querySelector('[data-role="other-count"]');
        el.setAttribute('aria-busy', 'false');
        if (!data.configured || data.error) {
            meta.textContent = '';
            body.innerHTML = '';
            if (count) count.textContent = '';
            return;
        }
        const others = data.others || [];
        if (count) count.textContent = intFmt.format(others.length);
        meta.textContent = plural(others.length, S.othersMeta1, S.othersMeta, { n: intFmt.format(others.length), month: CFG.monthLabel });
        if (!others.length) {
            body.innerHTML = `<p class="nx-fin-empty">${esc(fmt(S.noOthers, { month: CFG.monthLabel }))}</p>`;
            return;
        }
        const rowsHtml = others.map(inv => `<tr class="nx-fin-bexio__inv${inv.status === 'cancelled' ? ' is-cancelled' : ''}">
            <td class="nx-fin-bexio__client">${esc(inv.contact)}</td>
            <td><span class="nx-fin-bexio__nr">${esc(inv.nr)}</span> <span class="nx-fin-bexio__title">${esc(inv.title)}</span></td>
            <td class="nx-fin-bexio__date">${esc(dateText(inv.date))}</td>
            <td>${statusHtml(inv.status)}</td>
            <td class="nx-num">${esc(money(inv.excl, inv.currency))}</td>
            <td class="nx-num">${esc(money(inv.total, inv.currency))}</td>
            <td class="nx-fin-bexio__act"><a class="nx-btn nx-btn--ghost nx-btn--sm" href="${esc(pdfUrl(inv.id))}" target="_blank" rel="noopener">
              <i class="fas fa-file-pdf" aria-hidden="true"></i> ${esc(S.pdf)}</a></td></tr>`).join('');
        body.innerHTML = `<div class="nx-fin-table nx-fin-table--wide" data-testid="billing-other-table">
            <div class="nx-fin-matrix" tabindex="0" role="region" aria-label="${esc(S.contact)}">
              <table class="nx-table nx-fin-bexio__table">
                <thead><tr><th>${esc(S.contact)}</th><th>${esc(S.invoice)}</th><th>${esc(S.date)}</th><th>${esc(S.statusCol)}</th>
                  <th class="nx-num">${esc(S.excl)}</th><th class="nx-num">${esc(S.totalCol)}</th><th><span class="nx-fin-sr">${esc(S.actions)}</span></th></tr></thead>
                <tbody>${rowsHtml}</tbody>
                <tfoot><tr><td>${esc(S.totalCol)}</td><td colspan="3"></td>
                  <td class="nx-num">${esc(money(chf(data.othersTotals, 'excl'), 'CHF'))}</td>
                  <td class="nx-num">${esc(money(chf(data.othersTotals, 'total'), 'CHF'))}</td><td></td></tr></tfoot>
              </table></div></div>`;
    }

    // ---- open and unpaid ----------------------------------------------------
    function renderOutstanding(data) {
        const el = document.getElementById('bill-open');
        const body = el.querySelector('[data-role="body"]');
        const stateBox = el.querySelector('[data-role="state"]');
        const count = document.querySelector('[data-role="open-count"]');
        el.querySelector('[data-role="meta"]').textContent = fmt(S.asOf, { date: dateText(CFG.today) });
        el.setAttribute('aria-busy', 'false');
        if (!data.configured) {
            body.innerHTML = `<p class="nx-fin-note"><i class="fas fa-plug-circle-xmark" aria-hidden="true"></i><span>${esc(S.notConfigured)}</span></p>`;
            return;
        }
        if (data.error) {
            stateBox.innerHTML = '';
            body.innerHTML = errorHtml(data.error, data.detail, 'outstanding');
            return;
        }
        const invoices = data.invoices || [];
        if (count) count.textContent = intFmt.format(invoices.length);
        stateBox.innerHTML = data.overdue
            ? `<span class="nx-label nx-label--red">${esc(fmt(S.nOverdue, { n: intFmt.format(data.overdue) }))}</span>` : '';
        if (!invoices.length) {
            body.innerHTML = `<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(S.nothingOpen)}</p>`;
            return;
        }
        const totals = data.totals || [];
        const chfRow = totals.find(t => t.currency === 'CHF') || { open: 0, count: 0, overdue: 0, overdueCount: 0 };
        const tile = (label, value, sub, extra, testid) => `
            <div class="nx-kpi" data-testid="billing-open-${esc(testid)}">
              <p class="nx-kpi__label">${esc(label)}</p>
              <div class="nx-kpi__body"><div>
                <p class="nx-kpi__value nx-fin-bexio__value${extra}">${esc(value)}</p>
                <p class="nx-kpi__delta">${esc(sub)}</p>
              </div></div></div>`;
        const kpis = '<div class="nx-kpi-strip nx-fin-kpis">' +
            tile(S.outstanding, money(chfRow.open, 'CHF'), plural(chfRow.count, S.nInvoices1, S.nInvoices, { n: intFmt.format(chfRow.count) }), '', 'total') +
            tile(S.overdue, money(chfRow.overdue, 'CHF'), plural(chfRow.overdueCount, S.nInvoices1, S.nInvoices, { n: intFmt.format(chfRow.overdueCount) }), ' nx-bill-loss', 'overdue') +
            totals.filter(t => t.currency !== 'CHF').map(t => tile(fmt(S.inCurrency, { currency: t.currency || '?' }), money(t.open, t.currency),
                plural(t.count, S.nInvoicesOverdue1, S.nInvoicesOverdue, { n: intFmt.format(t.count), m: intFmt.format(t.overdueCount) }), '', 'cur-' + t.currency)).join('') +
            '</div>';
        const rowsHtml = invoices.map(inv => {
            const who = inv.linked
                ? `<span class="nx-fin-bexio__client">${esc(inv.client)}</span><span class="nx-bill-open__sub">${esc(inv.contact)}</span>`
                : `<span class="nx-bill-open__contact">${esc(inv.contact)}</span><span class="nx-bill-open__sub">${esc(S.notLinked)}</span>`;
            const late = inv.overdueDays ? `<span class="nx-bill-open__late">${esc(plural(inv.overdueDays, S.daysOverdue1, S.daysOverdue, { n: intFmt.format(inv.overdueDays) }))}</span>` : '';
            return `<tr data-invoice="${inv.id}">
                <td>${who}</td>
                <td><span class="nx-fin-bexio__nr">${esc(inv.nr)}</span> <span class="nx-fin-bexio__title">${esc(inv.title)}</span></td>
                <td class="nx-fin-bexio__date">${esc(dateText(inv.date))}</td>
                <td class="nx-fin-bexio__date">${esc(dateText(inv.due))}${late}</td>
                <td>${statusHtml(inv.status)}</td>
                <td class="nx-num nx-bill-open__open">${esc(money(inv.open, inv.currency))}</td>
                <td class="nx-num nx-bill-open__total">${esc(money(inv.total, inv.currency))}</td></tr>`;
        }).join('');
        body.innerHTML = kpis + `<div class="nx-fin-table nx-fin-table--wide" data-testid="billing-open-table">
            <div class="nx-fin-matrix" tabindex="0" role="region" aria-label="${esc(S.outstanding)}">
              <table class="nx-table nx-fin-bexio__table">
                <thead><tr><th>${esc(S.client)}</th><th>${esc(S.invoice)}</th><th>${esc(S.datedCol)}</th><th>${esc(S.dueCol)}</th>
                  <th>${esc(S.statusCol)}</th><th class="nx-num">${esc(S.openCol)}</th><th class="nx-num">${esc(S.totalCol)}</th></tr></thead>
                <tbody>${rowsHtml}</tbody></table></div></div>`;
    }

    // ---- the Bexio month ----------------------------------------------------
    function renderMonth(data) {
        state.month = data;
        const err = document.getElementById('bill-error');
        err.hidden = true;
        err.innerHTML = '';
        if (!data.configured) {
            setStatus('failed', S.notConfiguredShort);
            err.hidden = false;
            err.innerHTML = `<p class="nx-fin-note"><i class="fas fa-plug-circle-xmark" aria-hidden="true"></i><span>${esc(S.notConfigured)}</span></p>`;
        } else if (data.error) {
            setStatus('failed', data.error);
            err.hidden = false;
            err.innerHTML = errorHtml(data.error, data.detail, 'month');
        } else {
            setStatus('live', fmt(S.readAt, { time: data.readAt || '' }));
        }
        renderBand(data);
        renderOthers(data);
        renderClients();
    }

    const refresh = document.getElementById('bill-refresh');

    async function loadMonth(fresh) {
        setStatus('running', S.loading);
        const res = await window.NX.apiSafe(BILLING_API + 'month?month=' + encodeURIComponent(CFG.month) + (fresh ? '&fresh=1' : ''));
        renderMonth(res.ok && res.data ? res.data : { configured: true, error: (res.data && res.data.error) || S.loadFailed, clients: [] });
    }

    async function loadFigures() {
        state.figuresDone = false;
        const keys = clients.flatMap(c => c.sections).concat([BPS]);
        await Promise.all(keys.map(async key => {
            const res = await window.NX.apiSafe(BILLING_API + 'figures/' + encodeURIComponent(key) + '?month=' + encodeURIComponent(CFG.month));
            state.figures[key] = res.ok && res.data ? res.data : { error: S.loadFailed, figures: [], hours: {} };
        }));
        state.figuresDone = true;
        renderClients();
    }

    async function loadOutstanding(fresh) {
        const res = await window.NX.apiSafe(BILLING_API + 'outstanding' + (fresh ? '?fresh=1' : ''));
        renderOutstanding(res.ok && res.data ? res.data : { configured: true, error: (res.data && res.data.error) || S.loadFailed });
    }

    async function loadAll(fresh) {
        if (refresh) refresh.disabled = true;
        try {
            await Promise.all([loadMonth(fresh), loadFigures(), loadOutstanding(fresh)]);
        } finally {
            if (refresh) refresh.disabled = false;
        }
    }

    document.addEventListener('click', function (e) {
        const toggle = e.target.closest('[data-lines-toggle]');
        if (toggle) {
            const box = document.querySelector(`[data-lines-for="${toggle.dataset.linesToggle}"]`);
            if (!box) return;
            box.hidden = !box.hidden;
            toggle.setAttribute('aria-expanded', box.hidden ? 'false' : 'true');
            toggle.querySelector('span').textContent = box.hidden ? S.lines : S.hideLines;
            return;
        }
        const retry = e.target.closest('[data-retry]');
        if (!retry) return;
        if (retry.dataset.retry === 'month') loadMonth(true);
        else if (retry.dataset.retry === 'outstanding') loadOutstanding(true);
        else if (retry.dataset.retry === 'figures') loadFigures();
    });
    if (refresh) refresh.addEventListener('click', () => loadAll(true));

    // ---- month picker: a pick is a navigation, the month lives in the URL ----
    (function () {
        const picker = document.getElementById('bill-picker');
        if (!picker) return;
        const pickable = new Set(CFG.months || []);
        const years = (CFG.months || []).map(m => Number(m.slice(0, 4)));
        const minYear = Math.min(...years);
        const maxYear = Math.max(...years);
        const grid = picker.querySelector('[data-role="months"]');
        const states = {};
        let viewYear = Number(CFG.month.slice(0, 4));

        function statusHtmlFor(key) {
            const st = (states[viewYear] || {})[key] || '';
            if (st === 'running') return `<span class="nx-sydoc-picker__cell-status nx-sydoc-picker__cell-status--running"><span class="nx-sydoc-dot"></span>${esc(S.running)}</span>`;
            if (st === 'all') return `<span class="nx-sydoc-picker__cell-status nx-bill-cell--all"><i class="fas fa-check" aria-hidden="true"></i>${esc(S.allInvoiced)}</span>`;
            if (st.startsWith('missing:')) {
                return `<span class="nx-sydoc-picker__cell-status nx-bill-cell--missing"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>${esc(fmt(S.nMissing, { n: st.slice(8) }))}</span>`;
            }
            return '<span class="nx-sydoc-picker__cell-status"></span>';
        }

        function render() {
            picker.querySelector('[data-role="year"]').textContent = String(viewYear);
            picker.querySelector('[data-role="year-prev"]').disabled = viewYear <= minYear;
            picker.querySelector('[data-role="year-next"]').disabled = viewYear >= maxYear;
            grid.innerHTML = Sy.monthCells(viewYear, CFG.today, lang).map(c => {
                const ok = pickable.has(c.key);
                const selected = c.key === CFG.month;
                return `<button type="button" class="nx-sydoc-picker__cell${selected ? ' is-selected' : ''}" data-month="${c.key}"` +
                    `${ok ? '' : ' disabled'}${selected ? ' aria-current="true"' : ''}>` +
                    `<span class="nx-sydoc-picker__cell-name">${esc(c.name)}</span>${ok ? statusHtmlFor(c.key) : '<span class="nx-sydoc-picker__cell-status"></span>'}</button>`;
            }).join('');
        }

        async function loadYear(year) {
            if (states[year]) return;
            states[year] = {};
            const res = await window.NX.apiSafe(BILLING_API + 'months?year=' + year);
            if (res.ok && res.data && res.data.states && !res.data.error) states[year] = res.data.states;
            else delete states[year];  // try again on the next open
            if (year === viewYear && !picker.hidden) render();
        }

        function show(year) {
            viewYear = year;
            render();
            loadYear(year);
        }

        grid.addEventListener('click', e => {
            const cell = e.target.closest('[data-month]');
            if (!cell || cell.disabled) return;
            const url = new URL(window.location.href);
            url.searchParams.set('month', cell.dataset.month);
            url.hash = '';
            window.location.assign(url.toString());
        });
        picker.querySelector('[data-role="year-prev"]').addEventListener('click', () => show(viewYear - 1));
        picker.querySelector('[data-role="year-next"]').addEventListener('click', () => show(viewYear + 1));
        Sy.initPicker({
            root: picker,
            opener: document.querySelector('[data-testid="billing-period-button"]'),
            onOpen: () => {
                viewYear = Number(CFG.month.slice(0, 4));
                render();
                loadYear(viewYear);
            },
        });
    })();

    loadAll(false);
})();

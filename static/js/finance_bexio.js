/* Sydoc Finance: the Bexio invoice panel (#423). Behaviour only -- strings
   arrive on window.NX_FINANCE.bexio (templates/js/_finance_js.html).

   Read-only against Bexio: the panel lists the invoices dated in the month
   after the billed one (the server names the window), per Finance client;
   invoices to contacts no client is linked to are left out. The links live in
   dbo.FinanceBexioContacts (set by migration 0143) and are read-only here:
   nexora writes nothing. */
(function () {
    'use strict';

    const CFG = window.NX_FINANCE;
    const S = CFG.bexio;
    const esc = window.NX.esc;
    const lang = document.documentElement.lang || undefined;
    const panel = document.getElementById('fin-bexio');
    if (!panel) return;
    const body = panel.querySelector('[data-role="body"]');
    const meta = panel.querySelector('[data-role="meta"]');
    const refresh = document.getElementById('fin-bexio-refresh');

    const moneyFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const qtyFmt = new Intl.NumberFormat(lang, { maximumFractionDigits: 3 });
    const intFmt = new Intl.NumberFormat(lang);
    const STATUS_TONE = {
        draft: 'gray', open: 'blue', paid: 'green', partial: 'amber',
        cancelled: 'gray', unpaid: 'red', other: 'gray',
    };
    let state = null;

    function fmt(str, vars) {
        return String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }

    function money(value, currency) {
        const text = moneyFmt.format(Number(value) || 0);
        return currency ? `${currency} ${text}` : text;
    }

    // Totals are CHF only: Bexio sends no exchange rate with a foreign-currency
    // invoice, so those are listed in their own currency but never summed in.
    function totalsText(totals, field) {
        const chf = (totals || []).find(t => t.currency === 'CHF');
        return money(chf ? chf[field] : 0, 'CHF');
    }

    function statusHtml(status) {
        const tone = STATUS_TONE[status] || 'gray';
        return `<span class="nx-label nx-label--${tone}">${esc(S.status[status] || status)}</span>`;
    }

    function dateText(iso) {
        return iso ? window.NX.formatDate(iso) : '';
    }

    function kpisHtml(data) {
        const notInvoiced = data.clients.filter(c => c.state !== 'invoiced').length;
        const count = (data.totals || []).reduce((a, t) => a + t.count, 0);
        const tile = (label, value, testid, sub) => `
            <div class="nx-kpi" data-testid="finance-bexio-${testid}">
              <p class="nx-kpi__label">${esc(label)}</p>
              <div class="nx-kpi__body"><div>
                <p class="nx-kpi__value nx-fin-bexio__value">${esc(value)}</p>
                ${sub ? `<p class="nx-kpi__delta">${esc(sub)}</p>` : ''}
              </div></div>
            </div>`;
        return '<div class="nx-kpi-strip nx-fin-kpis">' +
            tile(S.invoiced, totalsText(data.totals, 'total'), 'total') +
            tile(S.excl, totalsText(data.totals, 'excl'), 'excl') +
            tile(S.invoices, intFmt.format(count), 'count',
                data.drafts ? fmt(S.drafts, { n: intFmt.format(data.drafts) }) : '') +
            tile(S.notInvoiced, intFmt.format(notInvoiced), 'missing') +
            '</div>';
    }

    function actionsHtml(inv) {
        const pdf = window.API_PREFIX + 'api/finance/bexio/invoice/' + inv.id + '/pdf';
        return `<span class="nx-fin-bexio__actions">
            <button type="button" class="nx-btn nx-btn--ghost nx-btn--sm" data-bexio-lines="${inv.id}"
                    aria-expanded="false" data-testid="finance-bexio-lines-${inv.id}">
              <i class="fas fa-list" aria-hidden="true"></i> ${esc(S.lines)}</button>
            <a class="nx-btn nx-btn--ghost nx-btn--sm" href="${esc(pdf)}" target="_blank" rel="noopener"
               data-testid="finance-bexio-pdf-${inv.id}"><i class="fas fa-file-pdf" aria-hidden="true"></i> ${esc(S.pdf)}</a>
          </span>`;
    }

    // One invoice as a table row; `lead` is the first cell (client or contact).
    function invoiceRow(lead, inv, cols) {
        const muted = inv.status === 'cancelled' ? ' is-cancelled' : '';
        return `<tr class="nx-fin-bexio__inv${muted}" data-invoice="${inv.id}">
            <td>${lead}</td>
            <td><span class="nx-fin-bexio__nr">${esc(inv.nr)}</span>
                <span class="nx-fin-bexio__title">${esc(inv.title)}</span></td>
            <td class="nx-fin-bexio__date">${esc(dateText(inv.date))}</td>
            <td>${statusHtml(inv.status)}</td>
            <td class="nx-num">${esc(money(inv.excl, inv.currency))}</td>
            <td class="nx-num">${esc(money(inv.total, inv.currency))}</td>
            <td class="nx-fin-bexio__act">${actionsHtml(inv)}</td>
          </tr>
          <tr class="nx-fin-bexio__lines" data-lines-for="${inv.id}" hidden><td colspan="${cols}"></td></tr>`;
    }

    function contactsHtml(client) {
        if (!client.contacts.length) return '';
        return '<span class="nx-fin-bexio__contacts">' +
            client.contacts.map(c => `<span class="nx-fin-bexio__contact">${esc(c.name)}</span>`).join('') +
            '</span>';
    }

    function clientLead(client) {
        return `<span class="nx-fin-bexio__client">${esc(client.client)}</span>${contactsHtml(client)}`;
    }

    function head(first) {
        return `<thead><tr>
            <th>${esc(first)}</th><th>${esc(S.invoice)}</th><th>${esc(S.date)}</th>
            <th>${esc(S.statusCol)}</th><th class="nx-num">${esc(S.excl)}</th>
            <th class="nx-num">${esc(S.totalCol)}</th><th><span class="nx-fin-sr">${esc(S.actions)}</span></th></tr></thead>`;
    }

    function clientsTable(data, month) {
        const rows = data.clients.map(c => {
            if (c.state === 'unlinked') {
                return `<tr data-client-state="unlinked"><td>${clientLead(c)}</td>
                    <td colspan="6"><span class="nx-label nx-label--gray nx-label--nodot">${esc(S.unlinked)}</span></td></tr>`;
            }
            if (!c.invoices.length) {
                return `<tr data-client-state="missing"><td>${clientLead(c)}</td>
                    <td colspan="6"><span class="nx-label nx-label--amber">${esc(fmt(S.missing, { month }))}</span></td></tr>`;
            }
            return c.invoices.map((inv, i) => invoiceRow(i === 0 ? clientLead(c) : '', inv, 7)).join('');
        }).join('');
        return `<div class="nx-fin-table nx-fin-table--wide" data-testid="finance-bexio-clients">
            <div class="nx-fin-matrix" tabindex="0" role="region" aria-label="${esc(S.client)}">
              <table class="nx-table nx-fin-bexio__table">${head(S.client)}<tbody>${rows}</tbody>
                <tfoot><tr><td>${esc(S.totalCol)}</td><td colspan="3"></td>
                  <td class="nx-num">${esc(totalsText(data.totals, 'excl'))}</td>
                  <td class="nx-num">${esc(totalsText(data.totals, 'total'))}</td><td></td></tr></tfoot>
              </table>
            </div>
          </div>`;
    }

    function render(data) {
        state = data;
        panel.setAttribute('aria-busy', 'false');
        const month = data.window ? data.window.label : '';
        meta.textContent = fmt(S.window, { month });
        if (!data.configured) {
            panel.dataset.state = 'off';
            body.innerHTML = `<p class="nx-fin-note"><i class="fas fa-plug-circle-xmark" aria-hidden="true"></i><span>${esc(S.notConfigured)}</span></p>`;
            return;
        }
        if (data.error) {
            panel.dataset.state = 'error';
            const detail = data.detail ? `<span class="nx-fin-error__detail">${esc(data.detail)}</span>` : '';
            body.innerHTML = `<div class="nx-fin-error" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
                <span>${esc(data.error)}</span>${detail}</div>`;
            return;
        }
        panel.dataset.state = 'ok';
        const parts = [kpisHtml(data)];
        if (!data.count) {
            parts.push(`<p class="nx-fin-empty"><i class="fas fa-inbox" aria-hidden="true"></i> ${esc(fmt(S.nothing, { month }))}</p>`);
        }
        parts.push('<div class="nx-fin-block">' + clientsTable(data, month) + '</div>');
        body.innerHTML = parts.join('');
    }

    async function load(fresh) {
        panel.setAttribute('aria-busy', 'true');
        if (refresh) refresh.disabled = true;
        const res = await window.NX.apiSafe('/api/finance/bexio?month=' + encodeURIComponent(CFG.month) +
            (fresh ? '&fresh=1' : ''));
        if (refresh) refresh.disabled = false;
        if (res.ok && res.data) {
            render(res.data);
        } else {
            render({ configured: true, error: (res.data && res.data.error) || CFG.strings.loadFailed,
                     window: state && state.window });
        }
    }

    // ---- invoice lines, fetched on first open --------------------------------
    function linesHtml(inv) {
        if (!inv.positions || !inv.positions.length) {
            return `<p class="nx-fin-empty">${esc(S.noLines)}</p>`;
        }
        const rows = inv.positions.map(p => {
            const text = esc(p.text || '').replace(/\n/g, '<br>');
            const opt = p.optional ? ` <span class="nx-label nx-label--gray nx-label--nodot">${esc(S.optional)}</span>` : '';
            if (p.kind === 'line') {
                return `<tr><td class="nx-fin-bexio__text">${text}${opt}</td>
                    <td class="nx-num">${esc(qtyFmt.format(p.amount))} ${esc(p.unit)}</td>
                    <td class="nx-num">${esc(money(p.unitPrice, ''))}</td>
                    <td class="nx-num">${p.discount ? esc(qtyFmt.format(p.discount) + ' %') : ''}</td>
                    <td class="nx-num">${esc(money(p.total, ''))}</td></tr>`;
            }
            if (p.kind === 'subtotal' || p.kind === 'discount') {
                const label = p.kind === 'subtotal' ? (text || esc(S.subtotal)) : (text || esc(S.discount));
                return `<tr class="nx-fin-bexio__sub"><td colspan="4">${label}</td>
                    <td class="nx-num">${esc(money(p.total, ''))}</td></tr>`;
            }
            return `<tr class="nx-fin-bexio__textline"><td colspan="5" class="nx-fin-bexio__text">${text}</td></tr>`;
        }).join('');
        return `<table class="nx-table nx-fin-bexio__positions">
            <thead><tr><th>${esc(S.text)}</th><th class="nx-num">${esc(S.quantity)}</th>
              <th class="nx-num">${esc(S.unitPrice)}</th><th class="nx-num">${esc(S.discount)}</th>
              <th class="nx-num">${esc(S.totalCol)} ${esc(inv.currency || '')}</th></tr></thead>
            <tbody>${rows}</tbody>
            <tfoot><tr><td colspan="4">${esc(S.excl)}</td><td class="nx-num">${esc(money(inv.excl, inv.currency))}</td></tr>
              <tr><td colspan="4">${esc(S.totalCol)}</td><td class="nx-num">${esc(money(inv.total, inv.currency))}</td></tr></tfoot>
          </table>
          <p class="nx-fin-bexio__open"><a href="${esc(inv.bexioUrl)}" target="_blank" rel="noopener">
            <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i> ${esc(S.openInBexio)}</a>
            ${inv.due ? `<span>${esc(S.due)} ${esc(dateText(inv.due))}</span>` : ''}</p>`;
    }

    async function toggleLines(button) {
        const id = button.dataset.bexioLines;
        const row = body.querySelector(`[data-lines-for="${id}"]`);
        if (!row) return;
        const open = row.hidden;
        row.hidden = !open;
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (!open || row.dataset.loaded) return;
        const cell = row.firstElementChild;
        cell.innerHTML = `<p class="nx-fin-empty">${esc(CFG.strings.loading)}</p>`;
        const res = await window.NX.apiSafe('/api/finance/bexio/invoice/' + encodeURIComponent(id));
        if (res.ok && res.data) {
            row.dataset.loaded = '1';
            cell.innerHTML = linesHtml(res.data);
        } else {
            cell.innerHTML = `<div class="nx-fin-error" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
                <span>${esc((res.data && res.data.error) || S.linesFailed)}</span></div>`;
        }
    }

    body.addEventListener('click', function (e) {
        const lines = e.target.closest('[data-bexio-lines]');
        if (lines) toggleLines(lines);
    });

    if (refresh) refresh.addEventListener('click', () => load(true));
    load(false);
})();

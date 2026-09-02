// Generali reporting page: filters/pagination/table for daily KPI reports,
// add/edit/delete modals, and an Excel export. Translated strings ride in
// via window.NX_I18N_GENERALI_REPORTING, built by the paired
// templates/js/_generali_reporting_js.html shim (#191).
//
// Relies on the page-global `csrfToken` const defined by static/js/header.js
// (loaded earlier via _header.html) and on window.nxUserFilter, both already
// shared-global conventions used by the other Generali pages.
(function () {
    var I18N = window.NX_I18N_GENERALI_REPORTING || {};

    const API_PREFIX = window.API_PREFIX;
    const canEdit        = document.getElementById('reportingTable').dataset.canEdit === 'true';
    const canEditTransOrg = document.getElementById('reportingTable').dataset.canEditTransorg === 'true';
    const currentOrgCode  = document.getElementById('reportingTable').dataset.orgCode || null;
    const canDelete        = document.getElementById('reportingTable').dataset.canDelete === 'true';
    const canDeleteTransOrg      = document.getElementById('reportingTable').dataset.canDeleteTransorg === 'true';
    const canAddBypassDeadline   = document.getElementById('reportingTable').dataset.canAddBypassDeadline === 'true';
    function getAddMinDate() {
        if (canAddBypassDeadline) return null;
        const t = new Date();
        return t.getDate() <= 3
            ? new Date(t.getFullYear(), t.getMonth() - 1, 1)
            : new Date(t.getFullYear(), t.getMonth(), 1);
    }
    const colSpan = (canEdit || canDelete) ? 7 : 6;
    function canEditRecord(r)   { return canEdit   && (canEditTransOrg   || r.orgCode === currentOrgCode); }
    function canDeleteRecord(r) { return canDelete && (canDeleteTransOrg || r.orgCode === currentOrgCode); }

    let currentPage = 1;
    let _currentRecords = [];
    const CATEGORIES = {
        'export_post':            I18N.kpi1,
        'export_post_scan':       I18N.kpi2,
        'provision_archive':      I18N.kpi3,
        'stray_document_digital': I18N.kpi12,
        'stray_document_physical':I18N.kpi13
    };

    // Details (archive/stray) disabled — these categories now behave like export_post/export_post_scan (on-time/late only)
    const ARCHIVE_CATS = []; // was: ['provision_archive', 'stray_document_digital', 'stray_document_physical']

    function ontimeBadge(ontime) {
        if (ontime) {
            return '<span class="nx-label nx-label--green nx-label--nodot">&#10003; ' + I18N.onTime + '</span>';
        }
        return '<span class="nx-label nx-label--red nx-label--nodot">&#10007; ' + I18N.late + '</span>';
    }

    // formatDate/formatDateTime: shared with nx_core.js (Task 12).
    const formatDate = window.NX.formatDate;
    const formatDateTime = window.NX.formatDateTime;

    // ----------------------------- latest delivery formula ----------------------------- //
    // if weekend → next Tuesday 12:00
    // if before 17:00 → next business day 12:00 (Mon–Thu +1d, Fri +3d)
    // if after  17:00 → two business days later 12:00 (Mon–Wed +2d, Thu–Fri +4d)
    function computeLatestDelivery(datetimeStr) {
        if (!datetimeStr) return null;
        const [datePart, timePart] = datetimeStr.split(' ');
        if (!datePart) return null;
        const [year, month, day] = datePart.split('-').map(Number);
        const [hours, minutes] = (timePart || '00:00').split(':').map(Number);

        let wd = new Date(year, month - 1, day).getDay(); // 0=Sun…6=Sat
        wd = wd === 0 ? 7 : wd;                           // 1=Mon…7=Sun

        const tSec = hours * 3600 + minutes * 60;
        const t17  = 17 * 3600;
        const base = new Date(year, month - 1, day);

        function addDaysAt12(d, n) {
            const r = new Date(d);
            r.setDate(r.getDate() + n);
            r.setHours(12, 0, 0, 0);
            return r;
        }

        let result;
        if (wd === 6 || wd === 7) {
            // Sat(6)→+3=Tue, Sun(7)→+2=Tue
            result = addDaysAt12(base, ((2 - wd + 7) % 7 + 7) % 7);
        } else if (tSec <= t17) {
            result = wd <= 4 ? addDaysAt12(base, 1) : addDaysAt12(base, 3);
        } else {
            result = wd <= 3 ? addDaysAt12(base, 2) : addDaysAt12(base, 4);
        }

        const p = n => String(n).padStart(2, '0');
        return `${result.getFullYear()}-${p(result.getMonth()+1)}-${p(result.getDate())} ${p(result.getHours())}:${p(result.getMinutes())}:00`;
    }

    // ----------------------------- stray document latest delivery formula ----------------------------- //
    // wd ≤ 4 (Mon–Thu): +1 day; Fri: +4 days; Sat: +3 days; Sun: +2 days → always at 12:00
    function computeLatestDeliveryStray(datetimeStr) {
        if (!datetimeStr) return null;
        const [datePart] = datetimeStr.split(/[T ]/);
        if (!datePart) return null;
        const [year, month, day] = datePart.split('-').map(Number);
        let wd = new Date(year, month - 1, day).getDay(); // 0=Sun…6=Sat
        wd = wd === 0 ? 7 : wd;                           // 1=Mon…7=Sun
        const base = new Date(year, month - 1, day);
        function addDaysAt12(d, n) {
            const r = new Date(d); r.setDate(r.getDate() + n); r.setHours(12, 0, 0, 0); return r;
        }
        const daysToAdd = wd <= 4 ? 1 : wd === 5 ? 4 : wd === 6 ? 3 : 2;
        const result = addDaysAt12(base, daysToAdd);
        const p = n => String(n).padStart(2, '0');
        return `${result.getFullYear()}-${p(result.getMonth()+1)}-${p(result.getDate())} ${p(result.getHours())}:${p(result.getMinutes())}:00`;
    }

    // ----------------------------- fetch ----------------------------- //
    function buildParams(page) {
        const p = new URLSearchParams();
        const start  = document.getElementById('filterStartDate').value;
        const end    = document.getElementById('filterEndDate').value;
        const cat    = document.getElementById('filterCategory').value;
        const org    = document.getElementById('filterOrganizationCode').value;
        const userId = document.getElementById('filterUserId')?.value || '';
        const onTime = document.getElementById('filterOnTime')?.value || '';
        if (start)  p.set('startDate', start);
        if (end)    p.set('endDate', end);
        if (cat)    p.set('category', cat);
        if (org)    p.set('organizationcode', org);
        if (userId) p.set('userId', userId);
        if (onTime) p.set('onTime', onTime);
        p.set('page', page);
        return p;
    }

    function loadOrganizations() {
        fetch(`${API_PREFIX}api/generali/reporting/organizations`, {
            headers: { 'X-CSRFToken': csrfToken }
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const sel = document.getElementById('filterOrganizationCode');
            if (!sel) return;
            (data.organizations || []).forEach(o => {
                const opt = document.createElement('option');
                opt.value = o.code;
                opt.textContent = o.name || o.code;
                sel.appendChild(opt);
            });
        })
        .catch(e => console.error('Failed to load organizations', e));
    }

    async function fetchRecords(page = 1) {
        currentPage = page;
        const tbody = document.getElementById('reportingTbody');
        tbody.innerHTML = `<tr><td colspan="${colSpan}" class="text-center py-16"><i class="fas fa-spinner fa-spin text-3xl text-[var(--nx-accent)]"></i></td></tr>`;

        const params = buildParams(page);
        try {
            const res = await fetch(`${API_PREFIX}api/generali/reporting?${params.toString()}`, {
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);
            renderTable(data.records);
            renderPagination(data.pagination);
        } catch (e) {
            console.error('Failed to fetch reporting records:', e);
            tbody.innerHTML = `<tr><td colspan="${colSpan}" class="text-center py-10 text-red-500">${I18N.failedToLoad}</td></tr>`;
        }
    }

    // ----------------------------- render table ----------------------------- //
    function renderTable(records) {
        _currentRecords = records;
        const tbody = document.getElementById('reportingTbody');
        tbody.innerHTML = '';

        if (!records.length) {
            tbody.innerHTML = `<tr><td colspan="${colSpan}">
                <div class="nx-empty"><div class="nx-empty__art"><i class="fas fa-inbox"></i></div>
                <p class="nx-empty__title">${I18N.noRecords}</p>
                <p class="nx-empty__sub">${I18N.adjustFilters}</p></div>
            </td></tr>`;
            return;
        }

        document.getElementById('showingCount').textContent = records.length;

        const recordMap = {};

        records.forEach(r => {
            const catLabel  = CATEGORIES[r.category] || r.category;
            const isArchive = ARCHIVE_CATS.includes(r.category);

            recordMap[r.id] = r;

            const detailsCell = isArchive
                ? `<td class="px-4 py-3 text-center">
                    <button class="view-details-btn nx-btn nx-btn--ghost" data-testid="generali-reporting-view-details-${r.id}">
                        <i class="fas fa-eye mr-1"></i>${I18N.details}
                    </button>
                   </td>`
                : `<td class="px-4 py-3 text-center text-gray-300 text-sm">—</td>`;

            const editable  = canEditRecord(r);
            const deletable = canDeleteRecord(r);
            const showActions = canEdit || canDelete;
            let actionBtns = '';
            if (canEdit)   actionBtns += `<button class="edit-record-btn inline-flex items-center text-xs font-semibold px-2 py-1 rounded-lg transition mr-1 ${editable  ? 'text-[var(--nx-accent)] hover:text-[var(--nx-accent-hover)] hover:bg-[var(--nx-accent-tint)]' : 'text-gray-300 cursor-not-allowed'}" data-id="${r.id}" ${editable  ? '' : 'disabled'} data-testid="generali-reporting-row-edit-${r.id}"><i class="fas fa-pen text-xs"></i></button>`;
            if (canDelete) actionBtns += `<button class="delete-record-btn inline-flex items-center text-xs font-semibold px-2 py-1 rounded-lg transition ${deletable ? 'text-red-500 hover:text-red-700 hover:bg-red-50' : 'text-gray-300 cursor-not-allowed'}" data-id="${r.id}" ${deletable ? '' : 'disabled'} data-testid="generali-reporting-row-delete-${r.id}"><i class="fas fa-trash text-xs"></i></button>`;
            const actionsCell = showActions ? `<td class="px-4 py-3 text-center whitespace-nowrap">${actionBtns}</td>` : '';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="px-4 py-3 text-center whitespace-nowrap"><span class="nx-mono">${formatDate(r.reportForDate)}</span></td>
                <td class="px-4 py-3 text-center text-sm whitespace-nowrap">${r.fullname}</td>
                <td class="px-4 py-3 text-sm">${catLabel}</td>
                <td class="px-4 py-3 text-center">${ontimeBadge(r.ontime)}</td>
                <td class="px-4 py-3 text-center text-sm whitespace-nowrap"><span class="nx-mono" style="color:var(--nx-text-sec)">${formatDateTime(r.reportTimeStamp)}</span></td>
                ${actionsCell}
            `;
            tbody.appendChild(tr);

            if (isArchive) {
                tr.querySelector('.view-details-btn').addEventListener('click', () => openDetailsModal(r));
            }
        });

        tbody._recordMap = recordMap;

        if (canEdit || canDelete) {
            tbody.addEventListener('click', e => {
                if (canEdit) {
                    const editBtn = e.target.closest('.edit-record-btn');
                    if (editBtn && !editBtn.disabled) openEditModal(tbody._recordMap[editBtn.dataset.id]);
                }
                if (canDelete) {
                    const deleteBtn = e.target.closest('.delete-record-btn');
                    if (deleteBtn && !deleteBtn.disabled) deleteRecord(deleteBtn.dataset.id);
                }
            });
        }
    }

    // ----------------------------- pagination ----------------------------- //
    function renderPagination(pagination) {
        const { page, total_pages, total_records, per_page } = pagination;
        document.getElementById('totalCount').textContent = total_records;
        document.getElementById('showingCount').textContent =
            Math.min(per_page, total_records - (page - 1) * per_page);

        const ctrl = document.getElementById('paginationControls');
        ctrl.innerHTML = '';

        if (total_pages <= 1) return;

        const btn = (label, p, disabled) => {
            const el = document.createElement('button');
            el.textContent = label;
            el.disabled = disabled;
            el.className = 'nx-btn nx-btn--secondary';
            if (!disabled) el.addEventListener('click', () => fetchRecords(p));
            return el;
        };

        ctrl.appendChild(btn('‹ ' + I18N.prev, page - 1, page <= 1));

        const pageInfo = document.createElement('span');
        pageInfo.className = 'px-3 py-1.5 text-sm font-medium nx-mono';
        pageInfo.style.color = 'var(--nx-text-sec)';
        pageInfo.textContent = `${I18N.page} ${page} / ${total_pages}`;
        ctrl.appendChild(pageInfo);

        ctrl.appendChild(btn(I18N.next + ' ›', page + 1, page >= total_pages));
    }

    // ----------------------------- modal ----------------------------- //
    const modal      = document.getElementById('addReportModal');
    const openBtn    = document.getElementById('openAddModalBtn');
    const closeBtn   = document.getElementById('closeModalBtn');
    const cancelBtn  = document.getElementById('cancelModalBtn');
    const submitBtn  = document.getElementById('submitReportBtn');
    const modalError = document.getElementById('modalError');

    const ALL_CATEGORIES = [
        { value: 'export_post',             label: I18N.kpi1 },
        { value: 'export_post_scan',        label: I18N.kpi2 },
        { value: 'provision_archive',       label: I18N.kpi3 },
        { value: 'stray_document_digital',  label: I18N.kpi12 },
        { value: 'stray_document_physical', label: I18N.kpi13 }
    ];

    function getToday() {
        return new Date().toISOString().split('T')[0];
    }

    function isDatePast(dateVal) {
        return dateVal < getToday();
    }

    const ONTIME_BTN_CLS = 'entry-ontime-btn flex-shrink-0 h-10 px-3 rounded-lg text-xs font-semibold border transition';
    function ontimeBtnStyle(isOnTime) {
        return isOnTime
            ? 'background:var(--nx-l-green);color:var(--nx-l-green-fg);border-color:transparent;'
            : 'background:var(--nx-l-red);color:var(--nx-l-red-fg);border-color:transparent;';
    }

    function ontimeButtonHtml(ontime, disabled) {
        const label = ontime ? '&#10003; ' + I18N.onTime : '&#10007; ' + I18N.late;
        return `<button type="button" class="${ONTIME_BTN_CLS}" style="${ontimeBtnStyle(ontime)}" data-ontime="${ontime}" ${disabled ? 'disabled' : ''} data-testid="generali-reporting-ontime-${ontime}">${label}</button>`;
    }

    function refreshOntimeBtn(btn, isOnTime) {
        btn.dataset.ontime = String(isOnTime);
        btn.className = ONTIME_BTN_CLS;
        btn.style.cssText = ontimeBtnStyle(isOnTime);
        btn.innerHTML = isOnTime ? '&#10003; ' + I18N.onTime : '&#10007; ' + I18N.late;
    }

    function autoSetOntime(row) {
        const latestVal   = row.querySelector('.latest-delivery-display').dataset.value;
        const deliveryVal = row.querySelector('.delivery-input').value;
        if (latestVal && deliveryVal) {
            refreshOntimeBtn(row.querySelector('.entry-ontime-btn'), deliveryVal <= latestVal);
        }
    }

    // ----------------------------- entry row ----------------------------- //
    function buildEntryRow(isPast) {
        const row = document.createElement('div');
        row.className = 'entry-row';

        const catOptions = ALL_CATEGORIES.map(c =>
            `<option value="${c.value}">${c.label}</option>`
        ).join('');

        row.innerHTML = `
            <div class="flex items-center gap-2">
                <div class="relative flex-1 min-w-0">
                    <select class="entry-category nx-select h-10 appearance-none pr-8">
                        <option value="">${I18N.selectCategory}</option>
                        ${catOptions}
                    </select>
                    <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
                        <i class="fa-solid fa-chevron-down text-xs"></i>
                    </div>
                </div>
                ${ontimeButtonHtml(!isPast, isPast)}
                <button type="button" class="entry-remove-btn flex-shrink-0 h-10 w-10 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition" data-testid="generali-reporting-entry-remove">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
            <div class="archive-details hidden mt-2 rounded-lg p-3 space-y-2" style="background:var(--nx-l-indigo);border:1px solid var(--nx-border);">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="request-time-label block text-xs font-bold uppercase tracking-widest mb-1" style="color:var(--nx-text-meta)">${I18N.emailReceived}</label>
                        <input type="text" class="request-time-input nx-input h-9" placeholder="yyyy-mm-dd hh:mm:ss" data-testid="generali-reporting-request-time-input" />
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase tracking-widest mb-1" style="color:var(--nx-text-meta)">${I18N.delivery}</label>
                        <input type="text" class="delivery-input nx-input h-9" placeholder="yyyy-mm-dd hh:mm:ss" data-testid="generali-reporting-delivery-input" />
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-bold uppercase tracking-widest mb-1" style="color:var(--nx-text-meta)">${I18N.latestDelivery}</label>
                    <div class="latest-delivery-display nx-input h-9 flex items-center" style="color:var(--nx-text-sec)" data-value="">—</div>
                </div>
            </div>
        `;

        row.querySelector('.entry-ontime-btn').addEventListener('click', function () {
            if (this.disabled) return;
            const newVal = this.dataset.ontime !== 'true';
            refreshOntimeBtn(this, newVal);
        });

        row.querySelector('.entry-remove-btn').addEventListener('click', function () {
            const group = row.closest('.date-group');
            if (group && group.querySelectorAll('.entry-row').length <= 1) return;
            row.remove();
            if (group) syncGroupControls(group);
        });

        row.querySelector('.entry-category').addEventListener('change', function () {
            const details   = row.querySelector('.archive-details');
            const ontimeBtn = row.querySelector('.entry-ontime-btn');
            const isArchive = ARCHIVE_CATS.includes(this.value);

            if (isArchive) {
                details.classList.remove('hidden');
                // Update the request-time label based on category
                row.querySelector('.request-time-label').textContent = this.value === 'provision_archive'
                    ? I18N.emailReceived
                    : I18N.mailroomRequest;
                // On-time is auto-determined for archive categories
                ontimeBtn.disabled = true;
            } else {
                details.classList.add('hidden');
                row.querySelector('.request-time-input').value = '';
                row.querySelector('.delivery-input').value = '';
                const display = row.querySelector('.latest-delivery-display');
                display.textContent = '—';
                display.dataset.value = '';
                // Re-enable manual toggle, re-apply past-date lock
                ontimeBtn.disabled = false;
                const group = row.closest('.date-group');
                if (group) {
                    const dateVal = group.querySelector('.group-date').value || getToday();
                    if (isDatePast(dateVal)) {
                        refreshOntimeBtn(ontimeBtn, false);
                        ontimeBtn.disabled = true;
                    }
                }
            }
            const group = row.closest('.date-group');
            if (group) syncGroupControls(group);
        });

        row.querySelector('.request-time-input').addEventListener('input', function () {
            const category = row.querySelector('.entry-category').value;
            const fn = category === 'provision_archive' ? computeLatestDelivery : computeLatestDeliveryStray;
            const latestDelivery = fn(this.value);
            const display = row.querySelector('.latest-delivery-display');
            display.textContent = latestDelivery ? formatDateTime(latestDelivery) : '—';
            display.dataset.value = latestDelivery || '';
            autoSetOntime(row);
        });

        row.querySelector('.delivery-input').addEventListener('input', function () {
            autoSetOntime(row);
        });

        const fpOpts = { dateFormat: 'Y-m-d H:i:S', enableTime: true, enableSeconds: true, allowInput: true, time_24hr: true, maxDate: 'today' };
        const reqIn  = row.querySelector('.request-time-input');
        const delIn  = row.querySelector('.delivery-input');
        flatpickr(reqIn, { ...fpOpts, onChange: () => reqIn.dispatchEvent(new Event('input')) });
        flatpickr(delIn, { ...fpOpts, onChange: () => delIn.dispatchEvent(new Event('input')) });

        return row;
    }

    // ----------------------------- group helpers ----------------------------- //
    function syncGroupControls(group) {
        if (!group) return;
        const rows = group.querySelectorAll('.entry-row');

        // Archive categories are unlimited — only deduplicate non-archive ones
        const usedNonArchive = Array.from(rows)
            .map(r => r.querySelector('.entry-category').value)
            .filter(v => v && !ARCHIVE_CATS.includes(v));

        rows.forEach(row => {
            const sel = row.querySelector('.entry-category');
            const own = sel.value;
            ALL_CATEGORIES.forEach(cat => {
                const opt = sel.querySelector(`option[value="${cat.value}"]`);
                if (opt) opt.disabled = !ARCHIVE_CATS.includes(cat.value)
                    && cat.value !== own
                    && usedNonArchive.includes(cat.value);
            });
            row.querySelector('.entry-remove-btn').style.visibility = rows.length <= 1 ? 'hidden' : 'visible';
        });

        // Archive categories are unlimited so the add button is always available
        const addBtn = group.querySelector('.group-add-entry-btn');
        if (addBtn) addBtn.style.display = '';
    }

    function syncDateGroups() {
        const groups = document.querySelectorAll('#dateGroups .date-group');
        groups.forEach(g => {
            g.querySelector('.group-remove-btn').style.visibility = groups.length <= 1 ? 'hidden' : 'visible';
        });
    }

    // ----------------------------- date group ----------------------------- //
    function buildDateGroup(date) {
        const group = document.createElement('div');
        group.className = 'date-group rounded-xl p-3 space-y-2';
        group.style.border = '1px solid var(--nx-border)';

        group.innerHTML = `
            <div class="flex items-center gap-2">
                <div class="flex-1">
                    <label class="block text-xs font-bold uppercase tracking-widest mb-1" style="color:var(--nx-text-meta)">${I18N.reportDate}</label>
                    <input type="text" class="group-date nx-input h-10" placeholder="yyyy-mm-dd" data-testid="generali-reporting-group-date" />
                </div>
                <button type="button" class="group-remove-btn flex-shrink-0 self-end h-10 w-10 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition" data-testid="generali-reporting-group-remove">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
            <div class="group-entry-rows space-y-2"></div>
            <button type="button" class="group-add-entry-btn flex items-center gap-1.5 text-xs font-semibold text-[var(--nx-accent)] hover:text-[var(--nx-accent-hover)] transition" data-testid="generali-reporting-group-add-entry">
                <i class="fas fa-plus"></i>${I18N.addAnotherCategory}
            </button>
        `;

        const groupDateInput = group.querySelector('.group-date');
        groupDateInput.value = date;
        flatpickr(groupDateInput, { dateFormat: 'Y-m-d', allowInput: true, maxDate: 'today', minDate: getAddMinDate() });

        groupDateInput.addEventListener('change', function () {
            const isPast = isDatePast(this.value);
            group.querySelectorAll('.entry-row').forEach(row => {
                if (ARCHIVE_CATS.includes(row.querySelector('.entry-category').value)) return;
                const btn = row.querySelector('.entry-ontime-btn');
                if (isPast) {
                    refreshOntimeBtn(btn, false);
                    btn.disabled = true;
                } else {
                    btn.disabled = false;
                }
            });
        });

        group.querySelector('.group-add-entry-btn').addEventListener('click', function () {
            const isPast = isDatePast(groupDateInput.value || getToday());
            group.querySelector('.group-entry-rows').appendChild(buildEntryRow(isPast));
            syncGroupControls(group);
        });

        group.querySelector('.group-remove-btn').addEventListener('click', function () {
            if (document.querySelectorAll('#dateGroups .date-group').length <= 1) return;
            group.remove();
            syncDateGroups();
        });

        group.querySelector('.group-entry-rows').appendChild(buildEntryRow(isDatePast(date)));
        syncGroupControls(group);

        return group;
    }

    function addDateGroup() {
        document.getElementById('dateGroups').appendChild(buildDateGroup(getToday()));
        syncDateGroups();
    }

    // ----------------------------- open / close ----------------------------- //
    function openModal() {
        document.getElementById('dateGroups').innerHTML = '';
        document.getElementById('dateGroups').appendChild(buildDateGroup(getToday()));
        syncDateGroups();
        if (modalError) { modalError.classList.add('hidden'); document.getElementById('modalErrorText').textContent = ''; }
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }

    function closeModal() {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }

    if (openBtn)   openBtn.addEventListener('click', openModal);
    if (closeBtn)  closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    if (modal)     modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

    const addDateGroupBtn = document.getElementById('addDateGroupBtn');
    if (addDateGroupBtn) addDateGroupBtn.addEventListener('click', addDateGroup);

    // ----------------------------- submit ----------------------------- //
    if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
            if (modalError) { modalError.classList.add('hidden'); }

            const allEntries = [];

            for (const group of document.querySelectorAll('#dateGroups .date-group')) {
                const reportForDate = group.querySelector('.group-date').value;
                if (!reportForDate) { showModalError(I18N.selectDate); return; }

                const groupEntries = [];
                for (const row of group.querySelectorAll('.entry-row')) {
                    const category = row.querySelector('.entry-category').value;
                    if (!category) { showModalError(I18N.selectCategoryForEntry); return; }
                    const ontime = row.querySelector('.entry-ontime-btn').dataset.ontime === 'true';

                    let emailReceivedTimeStamp = null, mailRoomRequestTimeStamp = null,
                        deliveryTimeStamp = null, latestDeliveryTimeStamp = null;
                    if (ARCHIVE_CATS.includes(category)) {
                        const requestVal        = row.querySelector('.request-time-input').value || null;
                        deliveryTimeStamp       = row.querySelector('.delivery-input').value || null;
                        latestDeliveryTimeStamp = row.querySelector('.latest-delivery-display').dataset.value || null;
                        if (!requestVal)         { showModalError(I18N.setRequestTimestamp); return; }
                        if (!deliveryTimeStamp)  { showModalError(I18N.setDeliveryTimestamp); return; }
                        if (category === 'provision_archive') {
                            emailReceivedTimeStamp = requestVal;
                        } else {
                            mailRoomRequestTimeStamp = requestVal;
                        }
                    }
                    groupEntries.push({ category, ontime, emailReceivedTimeStamp, mailRoomRequestTimeStamp, deliveryTimeStamp, latestDeliveryTimeStamp });
                }

                const cats = groupEntries.map(e => e.category);
                if (new Set(cats).size !== cats.length) {
                    showModalError(I18N.duplicateCategories);
                    return;
                }

                groupEntries.forEach(e => allEntries.push({ reportForDate, ...e }));
            }

            // Catch duplicate date+category across groups
            const keys = allEntries.map(e => `${e.reportForDate}|${e.category}`);
            if (new Set(keys).size !== keys.length) {
                showModalError(I18N.duplicateDateCategory);
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + I18N.submitting;

            const errors = [];
            for (const entry of allEntries) {
                try {
                    const res = await fetch(`${API_PREFIX}api/generali/reporting`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify(entry)
                    });
                    const data = await res.json();
                    if (!data.success) errors.push(data.error || entry.category);
                } catch (e) {
                    errors.push(`${I18N.networkErrorFor} ${entry.category}`);
                }
            }

            submitBtn.disabled = false;
            submitBtn.innerHTML = I18N.submit;

            if (errors.length) {
                showModalError(errors.join(' · '));
            } else {
                closeModal();
                fetchRecords(1);
            }
        });
    }

    function showModalError(msg) {
        if (!modalError) return;
        document.getElementById('modalErrorText').textContent = msg;
        modalError.classList.remove('hidden');
    }

    // ----------------------------- edit modal ----------------------------- //
    const editModal         = document.getElementById('editModal');
    const editOntimeBtn     = document.getElementById('editOntimeBtn');
    const editArchiveFields = document.getElementById('editArchiveFields');
    const editLatestDel     = document.getElementById('editLatestDelivery');
    const editError         = document.getElementById('editError');
    let   _editRecord       = null;

    const fpEditDate = flatpickr('#editReportDate', { dateFormat: 'Y-m-d', allowInput: true, maxDate: 'today' });
    const fpEditRequest = flatpickr('#editRequestTime', {
        dateFormat: 'Y-m-d H:i:S', enableTime: true, enableSeconds: true,
        allowInput: true, time_24hr: true, maxDate: 'today',
        onChange: () => recomputeEditLatest()
    });
    const fpEditDelivery = flatpickr('#editDelivery', {
        dateFormat: 'Y-m-d H:i:S', enableTime: true, enableSeconds: true,
        allowInput: true, time_24hr: true, maxDate: 'today',
        onChange: () => autoSetEditOntime()
    });

    function recomputeEditLatest() {
        const cat = _editRecord ? _editRecord.category : '';
        const fn  = cat === 'provision_archive' ? computeLatestDelivery : computeLatestDeliveryStray;
        const val = fn(document.getElementById('editRequestTime').value);
        editLatestDel.textContent   = val ? formatDateTime(val) : '—';
        editLatestDel.dataset.value = val || '';
        autoSetEditOntime();
    }

    function setEditOntimeBtn(isOnTime) {
        editOntimeBtn.dataset.ontime = String(isOnTime);
        editOntimeBtn.className = 'h-10 px-4 rounded-lg text-xs font-semibold border transition';
        editOntimeBtn.style.cssText = ontimeBtnStyle(isOnTime);
        editOntimeBtn.innerHTML = isOnTime ? '&#10003; ' + I18N.onTime : '&#10007; ' + I18N.late;
    }

    function autoSetEditOntime() {
        const latest   = editLatestDel.dataset.value;
        const delivery = document.getElementById('editDelivery').value;
        if (latest && delivery) {
            setEditOntimeBtn(delivery <= latest);
        }
    }

    if (editOntimeBtn) {
        editOntimeBtn.addEventListener('click', function () {
            setEditOntimeBtn(this.dataset.ontime !== 'true');
        });
    }

    function openEditModal(r) {
        if (!r) return;
        _editRecord = r;
        editError.classList.add('hidden');

        fpEditDate.setDate(r.reportForDate, true);

        setEditOntimeBtn(r.ontime);

        const isArchive = ARCHIVE_CATS.includes(r.category);
        if (isArchive) {
            editArchiveFields.classList.remove('hidden');
            document.getElementById('editRequestLabel').textContent =
                r.category === 'provision_archive' ? I18N.emailReceived : I18N.mailroomRequest;
            const reqVal = r.category === 'provision_archive'
                ? r.emailReceivedTimeStamp : r.mailRoomRequestTimeStamp;
            fpEditRequest.setDate(reqVal || '', true);
            fpEditDelivery.setDate(r.deliveryTimeStamp || '', true);
            const latest = r.latestDeliveryTimeStamp || '';
            editLatestDel.textContent   = latest ? formatDateTime(latest) : '—';
            editLatestDel.dataset.value = latest ? latest.replace('T', ' ') : '';
        } else {
            editArchiveFields.classList.add('hidden');
            fpEditRequest.clear();
            fpEditDelivery.clear();
            editLatestDel.textContent   = '—';
            editLatestDel.dataset.value = '';
        }

        editModal.classList.remove('hidden');
        editModal.classList.add('flex');
    }

    function closeEditModal() {
        editModal.classList.add('hidden');
        editModal.classList.remove('flex');
        _editRecord = null;
    }

    async function saveEdit() {
        if (!_editRecord) return;
        const reportForDate = document.getElementById('editReportDate').value.trim();
        if (!reportForDate) {
            editError.textContent = I18N.reportDateRequired;
            editError.classList.remove('hidden');
            return;
        }
        const ontime    = editOntimeBtn.dataset.ontime === 'true';
        const isArchive = ARCHIVE_CATS.includes(_editRecord.category);
        const requestVal  = isArchive ? document.getElementById('editRequestTime').value.trim() : null;
        const deliveryVal = isArchive ? document.getElementById('editDelivery').value.trim()     : null;
        const latestVal   = isArchive ? (editLatestDel.dataset.value || null)                    : null;

        const payload = { id: _editRecord.id, reportForDate, ontime, latestDeliveryTimeStamp: latestVal || null };
        if (_editRecord.category === 'provision_archive') {
            payload.emailReceivedTimeStamp = requestVal || null;
        } else if (isArchive) {
            payload.mailRoomRequestTimeStamp = requestVal || null;
        }
        if (isArchive) payload.deliveryTimeStamp = deliveryVal || null;

        const saveBtn = document.getElementById('saveEditBtn');
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>' + I18N.saving;

        try {
            const res  = await fetch(`${API_PREFIX}api/generali/reporting`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);
            closeEditModal();
            fetchRecords(currentPage);
        } catch (e) {
            editError.textContent = e.message || I18N.saveFailed;
            editError.classList.remove('hidden');
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = I18N.save;
        }
    }

    if (editModal) {
        document.getElementById('saveEditBtn').addEventListener('click', saveEdit);
        document.getElementById('cancelEditBtn').addEventListener('click', closeEditModal);
        document.getElementById('closeEditBtn').addEventListener('click', closeEditModal);
        editModal.addEventListener('click', e => { if (e.target === editModal) closeEditModal(); });
    }

    // ----------------------------- delete ----------------------------- //
    let pendingDeleteId = null;

    function deleteRecord(id) {
        pendingDeleteId = id;
        document.getElementById('deleteModal').classList.remove('hidden');
        document.getElementById('deleteModal').classList.add('flex');
    }

    function closeDeleteModal() {
        document.getElementById('deleteModal').classList.add('hidden');
        document.getElementById('deleteModal').classList.remove('flex');
        pendingDeleteId = null;
    }

    document.getElementById('cancelDeleteBtn').addEventListener('click', closeDeleteModal);
    document.getElementById('deleteModal').addEventListener('click', function(e) {
        if (e.target === this) closeDeleteModal();
    });

    document.getElementById('confirmDeleteBtn').addEventListener('click', function() {
        if (!pendingDeleteId) return;
        const id = pendingDeleteId;
        this.disabled = true;
        this.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>' + I18N.deleting;
        fetch(`${API_PREFIX}api/generali/reporting/${id}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrfToken }
        })
        .then(r => r.json())
        .then(data => {
            this.disabled = false;
            this.innerHTML = I18N.delete;
            closeDeleteModal();
            if (data.success) {
                fetchRecords(currentPage);
            } else {
                const errDiv = document.createElement('div');
                errDiv.className = 'fixed bottom-4 right-4 z-50 bg-red-500 text-white text-sm font-semibold px-4 py-3 rounded-xl shadow-lg';
                errDiv.textContent = data.error || I18N.errorDeleting;
                document.body.appendChild(errDiv);
                setTimeout(() => errDiv.remove(), 4000);
            }
        })
        .catch(() => {
            this.disabled = false;
            this.innerHTML = I18N.delete;
            closeDeleteModal();
        });
    });

    // ----------------------------- filter ----------------------------- //
    let _filterTimer;
    const applyFiltersSoon = () => { clearTimeout(_filterTimer); _filterTimer = setTimeout(() => fetchRecords(1), 350); };
    document.querySelectorAll('.nx-filter select').forEach(s => s.addEventListener('change', applyFiltersSoon));
    const fpFilterStart = flatpickr('#filterStartDate', { dateFormat: 'Y-m-d', allowInput: true, onChange: applyFiltersSoon });
    const fpFilterEnd   = flatpickr('#filterEndDate',   { dateFormat: 'Y-m-d', allowInput: true, onChange: applyFiltersSoon });

    document.getElementById('resetFilterBtn').addEventListener('click', () => {
        fpFilterStart.clear(false);
        fpFilterEnd.clear(false);
        document.getElementById('filterCategory').value = '';
        document.getElementById('filterOrganizationCode').value = '';
        const fu = document.getElementById('filterUserId');
        if (fu) fu.value = '';
        const fo = document.getElementById('filterOnTime');
        if (fo) fo.value = '';
        fetchRecords(1);
    });

    // ----------------------------- excel export ----------------------------- //
    function showExportError(msg) {
        const errDiv = document.createElement('div');
        errDiv.className = 'fixed bottom-4 right-4 z-50 bg-red-500 text-white text-sm font-semibold px-4 py-3 rounded-xl shadow-lg';
        errDiv.textContent = msg;
        document.body.appendChild(errDiv);
        setTimeout(() => errDiv.remove(), 4000);
    }
    document.getElementById('exportExcelBtn')?.addEventListener('click', exportToExcel); // #193 finding 10


    async function exportToExcel() {
        const btn = document.getElementById('exportExcelBtn');
        const icon = btn ? btn.querySelector('i') : null;
        const originalIconClass = icon ? icon.className : '';
        if (btn) btn.disabled = true;
        if (icon) icon.className = 'fas fa-spinner fa-spin';
        try {
            const params = buildParams(1);
            params.set('all', 'true');
            const res = await fetch(`${API_PREFIX}api/generali/reporting?${params.toString()}`, {
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error || I18N.exportFailed);
            const records = data.records || [];
            if (!records.length) return;
            if (data.truncated) {
                window.NX.toast(
                    `Export limited to the first ${(data.capped_at || records.length).toLocaleString()} rows (more rows matched your filters).`
                );
            }
            const today = new Date().toISOString().split('T')[0];
            const rows = records.map(r => ({
                'ID':          r.id,
                'Date':        r.reportForDate ? r.reportForDate.split('T')[0] : '',
                'Full Name':   r.fullname,
                'Category':    CATEGORIES[r.category] || r.category,
                'On Time':     r.ontime ? 'Yes' : 'No',
                'Recorded At': r.reportTimeStamp ? r.reportTimeStamp.replace('T', ' ').substring(0, 16) : ''
            }));
            const ws = XLSX.utils.json_to_sheet(rows);
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Reporting');
            XLSX.writeFile(wb, `generali_reporting_${today}.xlsx`);
        } catch (e) {
            console.error('Export failed:', e);
            showExportError(I18N.exportFailed);
        } finally {
            if (btn) btn.disabled = false;
            if (icon) icon.className = originalIconClass;
        }
    }

    // ----------------------------- init ----------------------------- //
    loadOrganizations();
    nxUserFilter.init(API_PREFIX + 'api/generali/reporting/filterUsers', applyFiltersSoon);
    fetchRecords(1);
}());

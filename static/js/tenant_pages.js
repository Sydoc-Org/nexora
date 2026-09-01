/* tenant_pages.js -- generic tenant list/CRUD page behaviour (#191 shim pair
   for templates/js/_tenant_page_js.html). Task 5 of the tenant-kernel-ms02-
   pilot plan: renders the window.NX_TENANT-driven page produced by
   nx_lib/views/tenant.py's tenant_page/api_tenant_* route family. Fetches
   rows from /api/t/<tenant_code>/<page_key>, applies the server-rendered
   filter row, paginates, exports (navigates, never fetches), and -- for
   crud pages -- adds/edits/deletes records through the matching write
   endpoints. Self-contained IIFE, no Jinja here (#191/#193 lint), reuses
   the NX.* helper surface from nx_core.js. */
(function () {
    'use strict';

    var cfg = window.NX_TENANT;
    if (!cfg) return;

    var api = window.NX.apiSafe;
    var esc = window.NX.esc;
    var el = window.NX.el;
    var toast = window.NX.toast;
    var formatDate = window.NX.formatDate;
    var I18N = cfg.i18n;

    // ---- URLs ------------------------------------------------------------
    // api()/apiSafe() resolve API_PREFIX themselves (resolveUrl in nx_core.js)
    // from a single leading "/" -- never prepend API_PREFIX before handing a
    // URL to them, or PROD's "/nexora/" prefix gets applied twice. Direct
    // navigation (export) doesn't go through them, so that one URL is
    // resolved by hand, in the same "${API_PREFIX}path" idiom every other
    // shim uses (no leading slash on the path half).
    var LIST_PATH = '/api/t/' + encodeURIComponent(cfg.tenantCode) + '/' + encodeURIComponent(cfg.pageKey);
    var EXPORT_URL = window.API_PREFIX + 'api/t/' + encodeURIComponent(cfg.tenantCode) + '/' +
        encodeURIComponent(cfg.pageKey) + '/export';
    // 'documents' entities are 1:1 with a shared-workitems row (their IdColumn
    // is that source's WorkitemColumn -- see the TenantEntities seed) but the
    // viewer itself is not reimplemented here (task-9 brief / plan K4/K5): it
    // stays on the shared machinery. Link the id cell through the same
    // fallback deep-link the brief calls for -- `/workitems?search=<id>` --
    // rather than duplicating _workitem_detail_panel_js.html.
    var WORKITEMS_SEARCH_URL = window.API_PREFIX + 'workitems?search=';

    function recordPath(id) {
        return LIST_PATH + '/' + encodeURIComponent(id);
    }

    // ---- state -------------------------------------------------------------
    var state = { offset: 0, limit: 0, total: 0, rowsById: {} };

    var tbody = el('tenant-page-tbody');
    var prevBtn = el('tenant-page-prev');
    var nextBtn = el('tenant-page-next');
    var pageInfo = el('tenant-page-info');

    function currentFilters() {
        var params = new URLSearchParams();
        document.querySelectorAll('.tenant-filter-input').forEach(function (input) {
            var value = input.value.trim();
            if (value) params.set(input.dataset.filter, value);
        });
        return params;
    }

    function reportUnavailableOrError(res, fallback) {
        if (res.status === 503 && res.data && res.data.unavailable) {
            toast(I18N.unavailable, true);
        } else {
            toast((res.data && res.data.message) || fallback, true);
        }
    }

    // ---- rows --------------------------------------------------------------
    function formatCell(field, value) {
        if (value === null || value === undefined || value === '') return '—';
        if (field.role === 'date') return esc(formatDate(value));
        return esc(String(value));
    }

    function renderRows(rows) {
        state.rowsById = {};
        if (!tbody) return;
        if (!rows.length) {
            var colspan = 1 + cfg.fields.length + (cfg.canEdit ? 1 : 0);
            tbody.innerHTML = '<tr><td colspan="' + colspan + '" class="admin-empty">' + esc(I18N.noRecords) + '</td></tr>';
            return;
        }
        var html = '';
        rows.forEach(function (row) {
            var id = row[cfg.idColumn];
            state.rowsById[id] = row;
            html += '<tr data-testid="tenant-row-' + esc(id) + '">';
            if (cfg.entityKind === 'documents') {
                // Same fallback deep-link prepared_documents.html's own
                // "Open in Workitems" link uses (?search=<id> on the shared
                // overview) -- reuses that exact translated string.
                html += '<td><a href="' + esc(WORKITEMS_SEARCH_URL + encodeURIComponent(id)) + '" ' +
                    'class="text-[var(--nx-accent)] underline" title="' + esc(I18N.openInWorkitems) + '" ' +
                    'data-testid="tenant-row-view-' + esc(id) + '"><i class="fas fa-up-right-from-square mr-1"></i>' +
                    esc(id) + '</a></td>';
            } else {
                html += '<td>' + esc(id) + '</td>';
            }
            cfg.fields.forEach(function (f) {
                html += '<td>' + formatCell(f, row[f.column]) + '</td>';
            });
            if (cfg.canEdit) {
                html += '<td class="align-right">' +
                    '<button type="button" class="nx-btn nx-btn--ghost nx-btn--sm tenant-edit-btn" data-id="' + esc(id) + '" data-testid="tenant-edit-' + esc(id) + '">' + esc(I18N.edit) + '</button> ' +
                    '<button type="button" class="nx-btn nx-btn--ghost nx-btn--sm nx-c-danger tenant-delete-btn" data-id="' + esc(id) + '" data-testid="tenant-delete-' + esc(id) + '">' + esc(I18N.delete) + '</button>' +
                    '</td>';
            }
            html += '</tr>';
        });
        tbody.innerHTML = html;
    }

    function updatePaginationControls() {
        if (!pageInfo) return;
        var start = state.total === 0 ? 0 : state.offset + 1;
        var end = Math.min(state.offset + state.limit, state.total);
        pageInfo.textContent = I18N.pageInfo
            .replace('{start}', start).replace('{end}', end).replace('{total}', state.total);
        if (prevBtn) prevBtn.disabled = state.offset <= 0;
        if (nextBtn) nextBtn.disabled = state.offset + state.limit >= state.total;
    }

    async function loadRecords() {
        var params = currentFilters();
        params.set('offset', String(state.offset));
        var res = await api(LIST_PATH + '?' + params.toString());
        if (!res.ok) {
            reportUnavailableOrError(res, I18N.loadFailed);
            return;
        }
        state.total = res.data.total;
        state.offset = res.data.offset;
        state.limit = res.data.limit;
        renderRows(res.data.rows);
        updatePaginationControls();
    }

    // ---- filters (debounced text, immediate date) ---------------------------
    var filterTimer = null;
    document.querySelectorAll('.tenant-filter-input').forEach(function (input) {
        var debounced = input.type !== 'date';
        input.addEventListener(debounced ? 'input' : 'change', function () {
            clearTimeout(filterTimer);
            filterTimer = setTimeout(function () {
                state.offset = 0;
                loadRecords();
            }, debounced ? 300 : 0);
        });
    });

    // ---- pagination ----------------------------------------------------------
    if (prevBtn) {
        prevBtn.addEventListener('click', function () {
            state.offset = Math.max(0, state.offset - state.limit);
            loadRecords();
        });
    }
    if (nextBtn) {
        nextBtn.addEventListener('click', function () {
            state.offset = state.offset + state.limit;
            loadRecords();
        });
    }

    // ---- export (navigate, never fetch) ---------------------------------------
    window.exportTenantRecords = function () {
        var params = currentFilters();
        window.location.href = EXPORT_URL + (params.toString() ? '?' + params.toString() : '');
    };

    // ---- CRUD modal (crud pages the caller can edit only) ----------------------
    if (cfg.canEdit) {
        var modal = el('tenantRecordModal');
        var modalTitle = el('tenantRecordModalTitle');
        var form = el('tenantRecordForm');
        var idInput = el('tenantRecordId');

        function openModal() {
            modal.classList.remove('hidden');
            setTimeout(function () {
                modal.classList.remove('opacity-0');
                modal.querySelector('.modal-content').classList.remove('scale-95');
            }, 10);
        }

        function closeModal() {
            modal.classList.add('opacity-0');
            modal.querySelector('.modal-content').classList.add('scale-95');
            setTimeout(function () { modal.classList.add('hidden'); }, 300);
        }

        function setFieldValues(row) {
            cfg.fields.forEach(function (f) {
                var input = el('tenant-field-' + f.column);
                if (!input) return;
                var value = row ? row[f.column] : null;
                input.value = value === null || value === undefined ? '' : value;
            });
        }

        window.openTenantAddModal = function () {
            form.reset();
            idInput.value = '';
            modalTitle.textContent = I18N.addTitle;
            setFieldValues(null);
            openModal();
        };

        function openEditModal(id) {
            form.reset();
            idInput.value = id;
            modalTitle.textContent = I18N.editTitle;
            setFieldValues(state.rowsById[id]);
            openModal();
        }

        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });
        var cancelBtn = el('tenantRecordCancelBtn');
        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            var data = {};
            cfg.fields.forEach(function (f) {
                var input = el('tenant-field-' + f.column);
                if (input) data[f.column] = input.value;
            });
            var id = idInput.value;
            var res = await api(id ? recordPath(id) : LIST_PATH, { method: 'POST', body: JSON.stringify(data) });
            if (!res.ok) {
                reportUnavailableOrError(res, I18N.genericError);
                return;
            }
            closeModal();
            toast((res.data && res.data.message) || '');
            state.offset = 0;
            loadRecords();
        });

        if (tbody) {
            tbody.addEventListener('click', function (e) {
                var editBtn = e.target.closest('.tenant-edit-btn');
                if (editBtn) {
                    openEditModal(editBtn.dataset.id);
                    return;
                }
                var deleteBtn = e.target.closest('.tenant-delete-btn');
                if (!deleteBtn) return;
                // ponytail: window.confirm, same precedent as reporting_simple.js's
                // deleteReport -- swap for a styled dialog if one lands for this page.
                if (!window.confirm(I18N.deleteConfirm)) return;
                api(recordPath(deleteBtn.dataset.id), { method: 'DELETE' }).then(function (res) {
                    if (!res.ok) {
                        reportUnavailableOrError(res, I18N.genericError);
                        return;
                    }
                    toast((res.data && res.data.message) || '');
                    loadRecords();
                });
            });
        }
    }

    loadRecords();
})();

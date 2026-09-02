/*
 * generali_crud.js -- shared list/pagination/export/permission mechanics for
 * the Generali CRUD pages (beautify-phase-0-1, Task 15).
 *
 * Four page partials (_generali_base_services_js.html, _generali_additional_
 * services_js.html, _generali_project_management_js.html, _generali_pdqm_js
 * .html) grew near-identical copies of: reading the can-edit/can-delete/can-
 * add dataset flags off the records table, canEditRecord/canDeleteRecord,
 * getAddMinDate, loadRecords + its colspan/empty-state/total-display
 * plumbing, renderPagination, and exportToExcel. This module holds one
 * implementation of each, driven by a per-page descriptor the shim sets on
 * `window` and passes to `NX.generaliCrud.create(descriptor)`.
 *
 * What stays in each shim (genuine per-page divergence -- not force-
 * uniformed here): renderRow (column set differs: flat category vs 2-level
 * vs 3-level-with-null-sentinel vs comment-only), buildParams (filter fields
 * differ), the add/edit modal wiring and category-cascade selects, the
 * add/edit/delete network calls (payload shape differs -- category vs
 * parentCategory/subCategory vs comment vs quantity), and showExportError
 * (markup differs slightly per page). Those are supplied to the descriptor
 * as callbacks (renderRow, buildParams, exportRowMapper, showExportError)
 * rather than generalized, per the same "keep genuine divergence in the
 * descriptor" rule Task 14 applied on the Python side.
 *
 * No Jinja syntax here -- this file is served as a static asset. Translated
 * strings stay in the Jinja-rendered <script nonce> shim and are passed in
 * on the descriptor (emptyTitle/emptySub/exportFailedText/etc.), read off
 * `window` indirectly via the descriptor object the shim builds.
 */
(function (window, document) {
    'use strict';

    function readFlags(tableEl) {
        var ds = tableEl.dataset;
        return {
            canEdit: ds.canEdit === 'true',
            canEditTransOrg: ds.canEditTransorg === 'true',
            currentOrgCode: ds.orgCode || null,
            canAdd: ds.canAdd === 'true',
            canAddForOrg: ds.canAddForOrg === 'true',
            canAddTransOrg: ds.canAddTransorg === 'true',
            canAddBypassDeadline: ds.canAddBypassDeadline === 'true',
            canDelete: ds.canDelete === 'true',
            canDeleteTransOrg: ds.canDeleteTransorg === 'true'
        };
    }

    function computeAddMinDate(canAddBypassDeadline) {
        if (canAddBypassDeadline) return null;
        var t = new Date();
        return t.getDate() <= 3
            ? new Date(t.getFullYear(), t.getMonth() - 1, 1)
            : new Date(t.getFullYear(), t.getMonth(), 1);
    }

    function renderPagination(container, page, totalPages, onPageClick) {
        container.innerHTML = '';
        if (totalPages <= 1) return;

        function btn(label, targetPage, disabled, active) {
            var b = document.createElement('button');
            b.innerHTML = label;
            b.disabled = disabled;
            b.className = [
                'nx-btn nx-btn--sm',
                active ? 'nx-btn--primary' : 'nx-btn--secondary',
                disabled ? 'opacity-40 cursor-not-allowed' : ''
            ].join(' ');
            if (!disabled) b.onclick = function () { onPageClick(targetPage); };
            return b;
        }

        container.appendChild(btn('<i class="fas fa-chevron-left"></i>', page - 1, page === 1, false));

        var pages = new Set([1, totalPages, page]);
        if (page > 2) pages.add(page - 1);
        if (page < totalPages - 1) pages.add(page + 1);

        var prev = 0;
        Array.from(pages).sort(function (a, b) { return a - b; }).forEach(function (p) {
            if (p - prev > 1) {
                var dots = document.createElement('span');
                dots.textContent = '…';
                dots.className = 'px-2 text-gray-400 text-sm';
                container.appendChild(dots);
            }
            container.appendChild(btn(p, p, false, p === page));
            prev = p;
        });

        container.appendChild(btn('<i class="fas fa-chevron-right"></i>', page + 1, page === totalPages, false));
    }

    /**
     * Build a page's CRUD controller.
     *
     * descriptor:
     *   tableElementId        id of the element carrying the data-can-... / data-org-code flags
     *   tbodyId               records <tbody> id
     *   paginationContainerId
     *   showingCountId, totalCountId
     *   recordsEndpoint       full URL (already through API_PREFIX) for GET list
     *                         and GET ?all=true export; PUT/DELETE append /{id}
     *   colSpanBase           colspan when the actions column is hidden
     *   renderRow(record)     -> row HTML (page-specific)
     *   buildParams(page)     -> URLSearchParams (page-specific)
     *   emptyTitle, emptySub  translated empty-state copy
     *   totalDisplay          optional { elementId, field, format? } -- format
     *                         defaults to identity (pdqm shows a raw quantity;
     *                         the hour-based pages pass format: v => formatHours(v)+' h')
     *   exportButtonId        default 'exportExcelBtn'
     *   exportRowMapper(r)    -> plain object for the xlsx sheet (page-specific)
     *   exportSheetName, exportFilenamePrefix
     *   exportFailedText      translated "Export failed." string
     *   showExportError(msg)  page-specific error toast/flash renderer
     *
     * Returns: { flags..., canEditRecord, canDeleteRecord, getAddMinDate,
     *            colSpan, loadRecords, exportToExcel, getCurrentPage }
     */
    function create(descriptor) {
        var tableEl = document.getElementById(descriptor.tableElementId);
        var flags = readFlags(tableEl);

        function canEditRecord(r) {
            return flags.canEdit && (flags.canEditTransOrg || r.orgCode === flags.currentOrgCode);
        }
        function canDeleteRecord(r) {
            return flags.canDelete && (flags.canDeleteTransOrg || r.orgCode === flags.currentOrgCode);
        }
        var colSpan = (flags.canEdit || flags.canDelete) ? descriptor.colSpanBase + 1 : descriptor.colSpanBase;

        var currentPage = 1;

        function loadRecords(page) {
            currentPage = page;
            var tbody = document.getElementById(descriptor.tbodyId);
            tbody.innerHTML = '<tr><td colspan="' + colSpan + '" class="text-center py-16">' +
                '<i class="fas fa-spinner fa-spin text-3xl text-[var(--nx-accent)]"></i></td></tr>';

            var params = descriptor.buildParams(page);
            fetch(descriptor.recordsEndpoint + '?' + params.toString(), {
                headers: { 'X-CSRFToken': window.NX.csrfToken() }
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    tbody.innerHTML = '<tr><td colspan="' + colSpan + '" class="text-center py-10 text-sm" ' +
                        'style="color:var(--nx-danger)">' + (data.error || 'Error') + '</td></tr>';
                    return;
                }

                if (descriptor.totalDisplay) {
                    var totalEl = document.getElementById(descriptor.totalDisplay.elementId);
                    var raw = data[descriptor.totalDisplay.field];
                    if (totalEl) {
                        totalEl.textContent = raw !== undefined
                            ? (descriptor.totalDisplay.format ? descriptor.totalDisplay.format(raw) : raw)
                            : '—';
                    }
                }

                if (!data.records.length) {
                    tbody.innerHTML = '<tr><td colspan="' + colSpan + '"><div class="nx-empty">' +
                        '<div class="nx-empty__art"><i class="fas fa-inbox"></i></div>' +
                        '<p class="nx-empty__title">' + descriptor.emptyTitle + '</p>' +
                        '<p class="nx-empty__sub">' + descriptor.emptySub + '</p></div></td></tr>';
                } else {
                    tbody.innerHTML = data.records.map(descriptor.renderRow).join('');
                }

                var pg = data.pagination;
                var showing = Math.min((pg.page - 1) * pg.per_page + data.records.length, pg.total_records);
                document.getElementById(descriptor.showingCountId).textContent = showing;
                document.getElementById(descriptor.totalCountId).textContent = pg.total_records;
                renderPagination(
                    document.getElementById(descriptor.paginationContainerId),
                    pg.page, pg.total_pages, loadRecords
                );
            })
            .catch(function (e) {
                tbody.innerHTML = '<tr><td colspan="' + colSpan + '" class="text-center py-10 text-sm" ' +
                    'style="color:var(--nx-danger)">Network error</td></tr>';
                console.error(e);
            });
        }

        async function exportToExcel() {
            var btn = document.getElementById(descriptor.exportButtonId || 'exportExcelBtn');
            var icon = btn ? btn.querySelector('i') : null;
            var originalIconClass = icon ? icon.className : '';
            if (btn) btn.disabled = true;
            if (icon) icon.className = 'fas fa-spinner fa-spin';
            try {
                var params = descriptor.buildParams(1);
                params.set('all', 'true');
                var res = await fetch(descriptor.recordsEndpoint + '?' + params.toString(), {
                    headers: { 'X-CSRFToken': window.NX.csrfToken() }
                });
                var data = await res.json();
                if (!data.success) throw new Error(data.error || 'Export failed');
                var records = data.records || [];
                if (!records.length) return;
                if (data.truncated) {
                    window.NX.toast(
                        'Export limited to the first ' + (data.capped_at || records.length).toLocaleString() +
                        ' rows (more rows matched your filters).'
                    );
                }
                var today = new Date().toISOString().split('T')[0];
                var rows = records.map(descriptor.exportRowMapper);
                var ws = XLSX.utils.json_to_sheet(rows);
                var wb = XLSX.utils.book_new();
                XLSX.utils.book_append_sheet(wb, ws, descriptor.exportSheetName);
                XLSX.writeFile(wb, descriptor.exportFilenamePrefix + '_' + today + '.xlsx');
            } catch (e) {
                console.error('Export failed:', e);
                descriptor.showExportError(descriptor.exportFailedText);
            } finally {
                if (btn) btn.disabled = false;
                if (icon) icon.className = originalIconClass;
            }
        }

        var exportBtn = document.getElementById(descriptor.exportButtonId || 'exportExcelBtn');
        if (exportBtn) exportBtn.addEventListener('click', exportToExcel); // #193 finding 10

        return {
            canEdit: flags.canEdit,
            canEditTransOrg: flags.canEditTransOrg,
            currentOrgCode: flags.currentOrgCode,
            canAdd: flags.canAdd,
            canAddForOrg: flags.canAddForOrg,
            canAddTransOrg: flags.canAddTransOrg,
            canAddBypassDeadline: flags.canAddBypassDeadline,
            canDelete: flags.canDelete,
            canDeleteTransOrg: flags.canDeleteTransOrg,
            colSpan: colSpan,
            canEditRecord: canEditRecord,
            canDeleteRecord: canDeleteRecord,
            getAddMinDate: function () { return computeAddMinDate(flags.canAddBypassDeadline); },
            loadRecords: loadRecords,
            exportToExcel: exportToExcel,
            getCurrentPage: function () { return currentPage; }
        };
    }

    window.NX = window.NX || {};
    window.NX.generaliCrud = { create: create };
})(window, document);

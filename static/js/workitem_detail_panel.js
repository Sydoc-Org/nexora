// Shared workitem detail panel + lightbox renderer (#191). Included from
// workitems_overview.html, reporting.html (drill drawer) and
// prepared_documents.html via templates/js/_workitem_detail_panel_js.html,
// which supplies window.NX_I18N_WORKITEM_DETAIL_PANEL before this loads.
(function () {
  const API_PREFIX = window.API_PREFIX;
  const csrfToken = document.getElementById("csrfToken")?.value || "";
  const I18N = window.NX_I18N_WORKITEM_DETAIL_PANEL;

  window.fieldConfig = window.fieldConfig || { search_options: {}, labels: {} };

  // 4 real stages (nx_lib/views/workitems.py's WORKITEM_STAGES), not the
  // design handoff prototype's fictional 5-step Imported/Classified/.../
  // Exported pipeline -- the icons below are the closest fit per stage.
  const STAGES = ['Import', 'Extraction', 'Validation', 'Delivery'];
  const STAGE_ICONS = ['fa-file-import', 'fa-wand-magic-sparkles', 'fa-circle-check', 'fa-file-export'];

  function buildPanelMarkup(workitemid, status, currentStage, perms, readOnly) {
    const imagesBlock = perms.images
      ? `<div class="wi-doc-col">
           <div class="wi-doc-col__head">
             <p class="nx-eyebrow" id="doc-heading-${workitemid}">${I18N.document}</p>
             <button type="button" class="wi-doc-fullbtn" id="doc-fullbtn-${workitemid}" data-workitemid="${workitemid}" data-testid="workitem-full-mode">
               <i class="fas fa-expand"></i>${I18N.fullMode}
             </button>
           </div>
           <div id="image-container-${workitemid}" class="wi-doc-main">
             <p class="text-gray-500 text-center px-2">${I18N.clickToggleAgain}</p>
           </div>
           <div id="doc-thumbs-${workitemid}" class="wi-doc-thumbs"></div>
           <p id="doc-meta-${workitemid}" class="wi-doc-meta"></p>
           <div id="doc-full-${workitemid}" class="wi-doc-full" hidden></div>
         </div>`
      : `<div class="wi-doc-col"><div class="wi-doc-main wi-doc-main--restricted"><div class="text-center"><i class="fas fa-eye-slash text-gray-400 text-3xl mb-2"></i><p class="text-gray-500">${I18N.mediaPreviewRestricted}</p></div></div></div>`;
    const historyBlock = perms.audit
      ? `<div id="history-container-${workitemid}" class="wi-audit-list"><p class="text-gray-500 italic">${I18N.loadingHistory}</p></div>`
      : `<div class="wi-panel-restricted"><p class="text-gray-400"><i class="fas fa-lock mr-2"></i>${I18N.auditHistoryRestricted}</p></div>`;
    const fieldsBlock = perms.fields
      ? `<div id="fields-container-${workitemid}" data-src-wid="${workitemid}" class="flex-grow pr-2"><p class="text-gray-500 italic">${I18N.loadingDetails}</p></div>`
      : `<div class="wi-panel-restricted"><p class="text-gray-400 italic"><i class="fas fa-lock mr-2"></i>${I18N.documentFieldsRestricted}</p></div>`;
    const showSourcesBtn = perms.images
      ? `<button type="button" class="wi-show-sources-btn" data-workitemid="${workitemid}" data-testid="workitem-show-sources"><i class="fas fa-magnifying-glass-location"></i>${I18N.showSources}</button>`
      : '';
    return `
      <div class="details-content-wrapper wi-detail-panel">
        <div id="detail-panel-header-${workitemid}" class="detail-panel-header"></div>
        ${readOnly ? '' : `<div id="timeline-container-${workitemid}" class="wi-stepper" data-current-stage="${currentStage}" data-status="${status}">
          ${STAGES.map((label, i) => `
            <span class="wi-stepper__step">
              <span class="step-icon-wrapper wi-stepper__icon"><i class="fas ${STAGE_ICONS[i]}"></i></span>
              <span class="step-label wi-stepper__label">${label}</span>
            </span>
            ${i < STAGES.length - 1 ? '<span class="wi-stepper__line"></span>' : ''}
          `).join('')}
        </div>`}
        <div class="wi-detail-grid">
          ${imagesBlock}
          <div class="wi-detail-grid__rule"></div>
          <div class="wi-detail-col">
            <div class="wi-detail-col__head">
              <p class="nx-eyebrow">${I18N.documentDetails}</p>
              ${showSourcesBtn}
            </div>
            ${fieldsBlock}
          </div>
          <div class="wi-detail-grid__rule"></div>
          <div class="wi-detail-col wi-audit-col">
            <p class="nx-eyebrow" style="margin-bottom:8px">${I18N.audit}</p>
            ${historyBlock}
          </div>
        </div>
        ${perms.fields ? `<div id="tables-container-${workitemid}" data-src-wid="${workitemid}" class="wi-tables" hidden></div>` : ''}
      </div>`;
  }

  async function loadHistory(workitemId) {
        const historyContainer = document.getElementById(`history-container-${workitemId}`);
        if (!historyContainer) {
            console.error(`History container not found for workitem ID: ${workitemId}`);
            return;
        }

        if (historyContainer.dataset.loaded === 'true') {
            return;
        }

        try {
            const response = await fetch(`${API_PREFIX}api/get_audithistory/${workitemId}${_clientQS(workitemId, '?')}`, {headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
            }});
            if (response.status === 403) {
                 historyContainer.innerHTML = `<p class="text-gray-400 italic"><i class="fas fa-lock mr-2"></i>${I18N.restricted}</p>`;
                 return;
            }
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            const historyData = await response.json();

            historyContainer.innerHTML = '';

            if (historyData.length === 0) {
                historyContainer.innerHTML = `<p class="text-gray-500">${I18N.noHistory}</p>`;
            } else {
                // Newest-first (the API returns oldest-first); the latest
                // dot is only accent while the workitem is still in flight --
                // once Done every step already crossed, nothing is "current".
                const timelineEl = document.getElementById(`timeline-container-${workitemId}`);
                const inFlight = timelineEl && timelineEl.dataset.status !== 'Done';
                const newestFirst = [...historyData].reverse();

                newestFirst.forEach((item, i) => {
                    const isLast = i === newestFirst.length - 1;
                    const eventDate = new Date(item.DateTime);
                    const formattedDate = eventDate.toLocaleString(undefined, {
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute: '2-digit',
                    });
                    const el = document.createElement('div');
                    el.className = 'wi-audit-item';
                    el.innerHTML = `
                        <span class="wi-audit-item__rail">
                            <span class="wi-audit-item__dot${i === 0 && inFlight ? ' is-latest' : ''}"></span>
                            ${isLast ? '' : '<span class="wi-audit-item__tail"></span>'}
                        </span>
                        <span class="wi-audit-item__body">
                            <span class="wi-audit-item__step"><strong>${srcEsc(item.Step)}</strong> · ${srcEsc(item.Activity)}</span>
                            <span class="wi-audit-item__meta">${srcEsc(formattedDate)}</span>
                        </span>`;
                    historyContainer.appendChild(el);
                });
            }
            historyContainer.dataset.loaded = 'true';
        } catch (error) {
            console.error('Failed to load history:', error);
            historyContainer.innerHTML = `<p class="text-red-500">${I18N.couldNotLoadHistory}</p>`;
        }
    }

  function renderWorkitemTimeline(container) {
        if (!container || container.dataset.rendered === 'true') return;

        const currentStage = container.dataset.currentStage;
        const status = container.dataset.status;
        const stepElements = container.querySelectorAll('.wi-stepper__step');
        const lineElements = container.querySelectorAll('.wi-stepper__line');
        const stageIndex = STAGES.indexOf(currentStage);
        // done = every stage up to (Done) or before (in-flight) the current
        // one; current = the in-flight stage only, never set once status is
        // Done (that state has no "current", every step already crossed).
        const doneCount = status === 'Done' ? STAGES.length : Math.max(0, stageIndex);

        stepElements.forEach((step, i) => {
            const icon = step.querySelector('.wi-stepper__icon');
            const label = step.querySelector('.wi-stepper__label');
            icon.classList.remove('is-done', 'is-current');
            label.classList.remove('is-done', 'is-current');
            if (i < doneCount) {
                icon.classList.add('is-done');
                label.classList.add('is-done');
            } else if (status !== 'Done' && i === stageIndex) {
                icon.classList.add('is-current');
                label.classList.add('is-current');
            }
        });
        lineElements.forEach((line, i) => line.classList.toggle('is-done', i < doneCount));

        container.dataset.rendered = 'true';
    }

  function loadImagesInBatch(container, workitemid, totalImages, batchSize) {
        const thumbs = document.getElementById(`doc-thumbs-${workitemid}`);
        const existingBtn = thumbs && thumbs.querySelector('.load-more-btn');
        if (existingBtn) existingBtn.remove();

        const loadedCount = parseInt(container.dataset.loadedCount || '0', 10);
        const endIndex = Math.min(loadedCount + (batchSize || 7), totalImages);

        for (let i = loadedCount; i < endIndex; i++) {
            loadImage(container, workitemid, i, i === 0);
        }

        container.dataset.loadedCount = endIndex;

        if (thumbs && endIndex < totalImages) {
            const loadMoreBtn = document.createElement('button');
            loadMoreBtn.type = 'button';
            loadMoreBtn.className = 'load-more-btn wi-doc-thumb wi-doc-thumb--more';
            loadMoreBtn.textContent = `+${totalImages - endIndex}`;
            loadMoreBtn.title = `${I18N.loadMore} (${endIndex} / ${totalImages})`;
            loadMoreBtn.dataset.workitemid = workitemid;
            loadMoreBtn.dataset.totalImages = totalImages;
            thumbs.appendChild(loadMoreBtn);
        }
        return endIndex;
    }

    // Load every remaining page (Full mode needs all of them side by side,
    // not the lazy 7-at-a-time trickle the thumbnail strip is happy with).
    async function loadAllImages(workitemid, totalImages) {
        const container = document.getElementById(`image-container-${workitemid}`);
        if (!container) return;
        let loaded = parseInt(container.dataset.loadedCount || '0', 10);
        while (loaded < totalImages) {
            loaded = loadImagesInBatch(container, workitemid, totalImages, totalImages);
        }
        // loadImagesInBatch only *starts* the fetches; the <img> lands in the DOM
        // in onload. Wait for every page (or its failure placeholder) to arrive,
        // capped so a stuck request cannot hang Full mode forever.
        const t0 = Date.now();
        await new Promise(resolve => {
            const tick = () => {
                const settled = container.querySelectorAll('.workitem-image, .bg-red-100').length;
                if (settled >= totalImages || Date.now() - t0 > 20000) resolve();
                else setTimeout(tick, 100);
            };
            tick();
        });
    }

    function updateDocMeta(workitemid, index, total) {
        const meta = document.getElementById(`doc-meta-${workitemid}`);
        // Pages are stacked (all visible), so the meta is a page count, not a position.
        if (meta) meta.textContent = I18N.documentPages.replace('%(n)s', total);
    }

    function setActiveThumb(workitemid, index) {
        const container = document.getElementById(`image-container-${workitemid}`);
        const thumbs = document.getElementById(`doc-thumbs-${workitemid}`);
        if (!container) return;
        container.querySelectorAll('.workitem-image').forEach(img => {
            const active = parseInt(img.dataset.pageIndex, 10) === index;
            img.classList.toggle('wi-main-active', active);
            // Click-to-locate: bring the located page into the stack's viewport.
            if (active && index > 0) container.scrollTop = img.closest('.src-thumb').offsetTop;
        });
        if (thumbs) {
            thumbs.querySelectorAll('.wi-doc-thumb').forEach(t => {
                t.classList.toggle('is-active', parseInt(t.dataset.pageIndex, 10) === index);
            });
        }
        const total = container.dataset.totalImages;
        if (total) updateDocMeta(workitemid, index, total);
    }

    function toggleFullMode(workitemid, totalImages) {
        const btn = document.getElementById(`doc-fullbtn-${workitemid}`);
        const main = document.getElementById(`image-container-${workitemid}`);
        const thumbs = document.getElementById(`doc-thumbs-${workitemid}`);
        const meta = document.getElementById(`doc-meta-${workitemid}`);
        const full = document.getElementById(`doc-full-${workitemid}`);
        const heading = document.getElementById(`doc-heading-${workitemid}`);
        const grid = main && main.closest('.wi-detail-grid');
        if (!btn || !main || !full) return;
        const enteringFull = full.hidden;
        if (grid) grid.classList.toggle('is-full-mode', enteringFull);
        // The line-item tables live outside the grid; hide them along with fields/audit.
        main.closest('.wi-detail-panel')?.classList.toggle('is-full-mode', enteringFull);
        if (heading) heading.textContent = enteringFull
            ? I18N.documentPages.replace('%(n)s', totalImages) : I18N.document;
        if (enteringFull) {
            loadAllImages(workitemid, totalImages).then(() => {
                full.innerHTML = '';
                main.querySelectorAll('.workitem-image').forEach(img => {
                    const clone = document.createElement('img');
                    clone.src = img.src;
                    clone.alt = img.alt;
                    clone.className = 'wi-doc-full__page';
                    full.appendChild(clone);
                });
            });
            btn.innerHTML = `<i class="fas fa-compress"></i>${I18N.compact}`;
        } else {
            btn.innerHTML = `<i class="fas fa-expand"></i>${I18N.fullMode}`;
        }
        full.hidden = !enteringFull;
        main.hidden = enteringFull;
        if (thumbs) thumbs.hidden = enteringFull;
        if (meta) meta.hidden = enteringFull;
    }

  // Escape values interpolated into innerHTML. Field/cell values + column
  // names are extracted document content (attacker-influenceable via a crafted
  // document), so they must never be injected raw. (Box .title is set via the
  // DOM property, which is already safe.)
  // Small fill bar next to the confidence percentage (#299 console redesign);
  // reuses window.srcConfClass's bucket (already computed at each call site)
  // for color, so it always agrees with the badge/highlight-box color.
  function _confBarHtml(confCls, confidence) {
    const pct = Math.round(Math.max(0, Math.min(1, confidence)) * 100);
    return `<span class="src-conf-bar" title="${I18N.extractionConfidence}">`
      + `<span class="src-conf-bar__fill ${confCls}" style="width:${pct}%"></span></span>`;
  }

  function srcEsc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

  // A table cell is "just another source": flatten line-item cells to the
  // same {key,label,value,locations,confidence,kind} shape the overlay draws.
  // key encodes table/row/cell so a grid cell click can pulse exactly its box.
  function tableCellSources(workitemid) {
        const tables = (window.__tableByWorkitem && window.__tableByWorkitem[workitemid]) || [];
        const out = [];
        tables.forEach((t, ti) => (t.rows || []).forEach((row, ri) => row.forEach((c, ci) => {
            out.push({
                key: `t${ti}r${ri}c${ci}`, label: c.col, value: c.value,
                locations: c.locations || [], confidence: c.confidence, kind: 'cell',
            });
        })));
        return out;
    }

  function allSources(workitemid) {
        const fields = (window.__srcByWorkitem && window.__srcByWorkitem[workitemid]) || [];
        return fields.concat(tableCellSources(workitemid));
    }

  // No DB label for a raw Octo column code (e.g. "TabNetAmount", "OrdPk")?
  // Split it into words instead of showing it shouting in one block.
  function splitCode(s) {
        return String(s)
            .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
            .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2');
    }

  // Line-item tables render as REAL tables (one <tr> per row) in their own
  // full-width card below the two-column grid -- the narrow Document Details
  // column could only ever stack cells label-over-value, which made rows
  // impossible to compare (#199). Wide SAP-style Tab*/Ord* grids scroll
  // horizontally inside .src-table-scroll.
  function renderTableGrids(workitemid) {
        const tables = (window.__tableByWorkitem && window.__tableByWorkitem[workitemid]) || [];
        const labels = window.fieldConfig.labels || {};
        let html = '';
        tables.forEach((t, ti) => {
            const rows = t.rows || [];
            if (!rows.length) return;
            // Column order = first seen across all rows (a row may omit cells).
            const cols = [];
            rows.forEach(row => row.forEach(c => { if (cols.indexOf(c.col) === -1) cols.push(c.col); }));
            const title = srcEsc(t.title || 'Table')
                + ` <span class="src-table-count">(${rows.length} ${rows.length === 1 ? I18N.row : I18N.rows})</span>`;
            const head = `<th class="src-table-rownum">#</th>`
                + cols.map(col => `<th>${srcEsc(labels[col.toLowerCase()] || splitCode(col))}</th>`).join('');
            const body = rows.map((row, ri) => {
                const byCol = {};
                row.forEach((c, ci) => { byCol[c.col] = { c: c, ci: ci }; });
                const cells = cols.map(col => {
                    const hit = byCol[col];
                    // Missing cell, or extracted as empty: one em dash. An empty value
                    // with a 0% confidence chip next to it is noise, not information.
                    if (!hit || !String(hit.c.value == null ? '' : hit.c.value).trim()) {
                        return `<td class="src-table-empty">&mdash;</td>`;
                    }
                    const c = hit.c;
                    const hasLoc = !!(c.locations && c.locations.length);
                    const page = hasLoc ? c.locations[0].page : '';
                    const confCls = window.srcConfClass(c.confidence);
                    const confBadge = confCls
                        ? ` ${_confBarHtml(confCls, c.confidence)}<span class="src-conf-badge ${confCls}" title="${I18N.extractionConfidence}">${window.srcConfPct(c.confidence)}</span>`
                        : '';
                    // ponytail: no per-cell "no source location" badge -- one badge per cell
                    // buries the values it annotates. The pointer/hover affordance on
                    // .is-locatable already marks which cells can be located.
                    const titleAttr = hasLoc
                        ? ` title="${I18N.clickToLocate}"` : '';
                    return `<td class="src-field-row${hasLoc ? ' is-locatable' : ''}"`
                        + ` data-key="t${ti}r${ri}c${hit.ci}" data-page="${page}"${titleAttr}>`
                        + `${srcEsc(c.value)}${confBadge}</td>`;
                }).join('');
                return `<tr><td class="src-table-rownum">${ri + 1}</td>${cells}</tr>`;
            }).join('');
            html += `<details class="src-table-grid" open><summary class="src-table-title">${title}</summary>`
                + `<div class="src-table-scroll"><table class="src-table">`
                + `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div></details>`;
        });
        return html;
    }

  function buildSourceDetailsHtml(workitemid, opts) {
        const fields = (window.__fieldsByWorkitem && window.__fieldsByWorkitem[workitemid]) || {};
        // Suppress the "no source location" badge when the user lacks the
        // source-location perm (the backend strips locations from everything,
        // so it's a permission state, not missing data).
        const locVisible = !(window.__srcLocVisibleByWorkitem
            && window.__srcLocVisibleByWorkitem[workitemid] === false);
        let html = '';
        if (Object.keys(fields).length > 0) {
            const srcByKey = {};
            (window.__srcByWorkitem && window.__srcByWorkitem[workitemid] || []).forEach(s => { srcByKey[s.key] = s; });
            let fieldsHtml = '<dl class="divide-y divide-gray-200">';
            for (const key in fields) {
                if (Object.hasOwnProperty.call(fields, key) && fields[key]) {
                    const labelKey = key.toLowerCase();
                    const label = (window.fieldConfig.labels || {})[labelKey] || key;
                    const src = srcByKey[key];
                    const hasLoc = !!(src && src.locations && src.locations.length);
                    const page = hasLoc ? src.locations[0].page : '';
                    const rowCls = 'src-field-row py-2 flex justify-between items-center gap-4'
                        + (hasLoc ? ' is-locatable' : '');
                    const badge = (locVisible && src && !hasLoc)
                        ? ` <span class="src-no-loc-badge">${I18N.noSourceLocation}</span>` : '';
                    const titleAttr = hasLoc
                        ? ` title="${I18N.clickToLocate}"` : '';
                    const confCls = src ? window.srcConfClass(src.confidence) : '';
                    const confBadge = confCls
                        ? ` ${_confBarHtml(confCls, src.confidence)}<span class="src-conf-badge ${confCls}" title="${I18N.extractionConfidence}">${window.srcConfPct(src.confidence)}</span>`
                        : '';
                    fieldsHtml += `
                        <div class="${rowCls}" data-key="${key}" data-page="${page}"${titleAttr}>
                            <dt class="text-gray-500 truncate">${srcEsc(label)}${badge}</dt>
                            <dd class="font-semibold text-gray-900 text-right">${srcEsc(fields[key])}${confBadge}</dd>
                        </div>`;
                }
            }
            fieldsHtml += '</dl>';
            html += fieldsHtml;
        }
        // Inline panel keeps tables out (they live in their own full-width card);
        // the lightbox review panel is standalone, so it still appends them.
        if (!opts || opts.tables !== false) html += renderTableGrids(workitemid);
        return html;
    }

  function renderThumbOverlay(wrap, imgEl, workitemid, page) {
        const old = wrap.querySelector('.src-hl-layer-thumb');
        if (old) old.remove();
        if (localStorage.getItem('srcHlOn') !== '1') return;
        const srcs = allSources(workitemid);
        const natW = imgEl.naturalWidth, natH = imgEl.naturalHeight;
        const w = imgEl.clientWidth, h = imgEl.clientHeight;
        if (!natW || !natH || !w || !h) return;
        const scale = Math.min(w / natW, h / natH);
        const offX = (w - natW * scale) / 2, offY = (h - natH * scale) / 2;
        const layer = document.createElement('div');
        layer.className = 'src-hl-layer-thumb';
        srcs.forEach(s => (s.locations || []).forEach(loc => {
            if (loc.page !== page) return;
            const b = document.createElement('div');
            const confCls = window.srcConfClass(s.confidence);
            b.className = 'src-hl-box' + (confCls ? ' ' + confCls : '')
                + (s.kind === 'cell' ? ' src-hl-box--cell' : '');
            b.style.left = (offX + loc.rect.left * scale) + 'px';
            b.style.top = (offY + loc.rect.top * scale) + 'px';
            b.style.width = (loc.rect.width * scale) + 'px';
            b.style.height = (loc.rect.height * scale) + 'px';
            layer.appendChild(b);
        }));
        wrap.appendChild(layer);
    }

  function refreshThumbOverlays() {
        document.querySelectorAll('.src-thumb').forEach(wrap => {
            const img = wrap.querySelector('img.workitem-image');
            if (img) {
                renderThumbOverlay(wrap, img, wrap.dataset.workitemid,
                                   parseInt(wrap.dataset.page || '0', 10));
            }
        });
    }

  // `container` is the wi-doc-main box (id="image-container-<wid>"): every
  // loaded page lives there inside its own .src-thumb wrap (required by the
  // source-highlight overlay -- renderThumbOverlay draws boxes over
  // img.workitem-image inside that specific wrapper), CSS-hidden except the
  // one page flagged .wi-main-active. The small strip under it
  // (doc-thumbs-<wid>) holds separate, lightweight <img> clones that just
  // switch which page is active -- they don't need their own overlay boxes.
  async function loadImage(container, workitemid, index, makeActive) {
        const placeholder = document.createElement('div');
        placeholder.className = 'flex justify-center items-center w-40 h-40 bg-gray-200 rounded animate-pulse';
        container.appendChild(placeholder);
        try {
            const apiUrl = `${API_PREFIX}api/get_media_raw/${workitemid}/${index}${_clientQS(workitemid, '?')}`;
            // The overview warms first pages into window.NX_MEDIA_CACHE -- reuse.
            let imageUrl = window.NX_MEDIA_CACHE && window.NX_MEDIA_CACHE[apiUrl];
            if (!imageUrl) {
                const response = await fetch(apiUrl, {headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
                }});

                if (!response.ok) {
                    throw new Error(`Status ${response.status}`);
                }

                const imageBlob = await response.blob();
                imageUrl = URL.createObjectURL(imageBlob);
                if (window.NX_MEDIA_CACHE) window.NX_MEDIA_CACHE[apiUrl] = imageUrl;
            }

            const imgElement = document.createElement('img');
            imgElement.src = imageUrl;
            imgElement.alt = `${I18N.media} ${index + 1} ${I18N.forWorkitem}${workitemid}`;
            imgElement.dataset.pageIndex = String(index);
            // object-contain (not cover) shows the whole page so source boxes map correctly.
            imgElement.className = 'wi-doc-page workitem-image cursor-pointer bg-gray-50';

            const thumbWrap = document.createElement('div');
            thumbWrap.className = 'src-thumb';
            thumbWrap.dataset.workitemid = String(workitemid);
            thumbWrap.dataset.page = String(index);
            thumbWrap.appendChild(imgElement);

            imgElement.onload = () => {
                placeholder.replaceWith(thumbWrap);   // keeps page order under concurrent loads
                if (makeActive) setActiveThumb(workitemid, index);
                renderThumbOverlay(thumbWrap, imgElement, String(workitemid), index);
                _appendThumbStripEntry(workitemid, index, imageUrl);
            };

            imgElement.onerror = () => {
                URL.revokeObjectURL(imageUrl);
                throw new Error('Image could not be loaded into element.');
            }


        } catch (error) {
            console.error(`Error loading image index ${index}:`, error);
            placeholder.innerHTML = `<div class="text-center text-xs text-red-600 p-2">${I18N.failedToLoadImage}${index + 1}</div>`;
            placeholder.classList.remove('animate-pulse', 'bg-gray-200');
            placeholder.classList.add('bg-red-100', 'border', 'border-red-400');
        }
    }

  function _appendThumbStripEntry(workitemid, index, imageUrl) {
    const thumbs = document.getElementById(`doc-thumbs-${workitemid}`);
    if (!thumbs) return;
    const moreBtn = thumbs.querySelector('.load-more-btn');
    const thumb = document.createElement('img');
    thumb.src = imageUrl;
    thumb.alt = `${I18N.media} ${index + 1}`;
    thumb.className = 'wi-doc-thumb' + (index === 0 ? ' is-active' : '');
    thumb.dataset.workitemid = String(workitemid);
    thumb.dataset.pageIndex = String(index);
    if (moreBtn) thumbs.insertBefore(thumb, moreBtn);
    else thumbs.appendChild(thumb);
  }

  // Delegated: the thumbnail strip, the "+N" load-more thumb, the Full mode
  // button and the Document details column's Show sources button are all
  // rendered by buildPanelMarkup, shared across workitems/reporting/prepared
  // documents -- one document-level listener covers every instance.
  document.addEventListener('click', (event) => {
    const thumb = event.target.closest('.wi-doc-thumb:not(.load-more-btn)');
    if (thumb) {
      setActiveThumb(thumb.dataset.workitemid, parseInt(thumb.dataset.pageIndex, 10));
      return;
    }
    const moreBtn = event.target.closest('.load-more-btn');
    if (moreBtn) {
      const container = document.getElementById(`image-container-${moreBtn.dataset.workitemid}`);
      if (container) loadImagesInBatch(container, moreBtn.dataset.workitemid, parseInt(moreBtn.dataset.totalImages, 10));
      return;
    }
    const fullBtn = event.target.closest('.wi-doc-fullbtn');
    if (fullBtn) {
      const container = document.getElementById(`image-container-${fullBtn.dataset.workitemid}`);
      const total = container ? parseInt(container.dataset.totalImages || '0', 10) : 0;
      toggleFullMode(fullBtn.dataset.workitemid, total);
      return;
    }
  });

  async function loadDetailData(workitemid, perms) {
    const imageContainer = document.getElementById(`image-container-${workitemid}`);
    const fieldsContainer = document.getElementById(`fields-container-${workitemid}`);
    if (perms && perms.audit !== false) loadHistory(workitemid);
    if (!(imageContainer && imageContainer.dataset.loaded !== 'true') && !fieldsContainer) return;
    if (imageContainer) imageContainer.innerHTML = `<p class="text-gray-500 animate-pulse">${I18N.checkingForMedia}</p>`;
    try {
      const infoResponse = await fetch(`${API_PREFIX}api/get_media_info/${workitemid}${_clientQS(workitemid, '?')}`, {headers: {
        'Content-Type': 'application/json', 'X-CSRFToken': csrfToken
      }});
      if (!infoResponse.ok) {
        if (infoResponse.status === 403) throw new Error("Restricted");
        throw new Error('Could not fetch media information.');
      }
      const mediaInfo = await infoResponse.json();
      const imageCount = mediaInfo.media_count || 0;
      const fields = mediaInfo.fields || {};
      window.__srcByWorkitem = window.__srcByWorkitem || {};
      window.__srcByWorkitem[workitemid] = mediaInfo.field_sources || [];
      window.__tableByWorkitem = window.__tableByWorkitem || {};
      window.__tableByWorkitem[workitemid] = mediaInfo.table_sources || [];
      window.__srcLocVisibleByWorkitem = window.__srcLocVisibleByWorkitem || {};
      window.__srcLocVisibleByWorkitem[workitemid] = mediaInfo.source_location_visible !== false;
      if (fieldsContainer) {
        window.__fieldsByWorkitem = window.__fieldsByWorkitem || {};
        window.__fieldsByWorkitem[workitemid] = fields;
        fieldsContainer.innerHTML = buildSourceDetailsHtml(workitemid, { tables: false })
          || `<p class="text-gray-500 p-2">${I18N.noAdditionalDetails}</p>`;
      }
      const tablesContainer = document.getElementById(`tables-container-${workitemid}`);
      if (tablesContainer) {
        const tablesHtml = renderTableGrids(workitemid);
        tablesContainer.innerHTML = tablesHtml;
        tablesContainer.hidden = !tablesHtml;
      }
      if (imageContainer) {
        imageContainer.dataset.loaded = 'true';
        if (imageCount === 0) {
          imageContainer.innerHTML = `<p class="text-gray-500">${I18N.noMediaFound}</p>`;
          const fullbtn = document.getElementById(`doc-fullbtn-${workitemid}`);
          if (fullbtn) fullbtn.hidden = true;
        } else {
          imageContainer.innerHTML = '';
          imageContainer.dataset.loadedCount = '0';
          imageContainer.dataset.totalImages = String(imageCount);
          loadImagesInBatch(imageContainer, workitemid, imageCount);
        }
      }
    } catch (error) {
      if (imageContainer) {
        imageContainer.innerHTML = `<p class="text-red-500">${I18N.couldNotLoadMedia}</p>`;
        imageContainer.dataset.loaded = 'true';
      }
    }
  }

  window.NexoraWorkitemDetail = window.NexoraWorkitemDetail || {};
  window.NexoraWorkitemDetail._buildPanelMarkup = buildPanelMarkup;
  // wid -> client code of the row it was rendered from (see render()).
  const _clientByWid = {};
  function _clientQS(workitemId, sep) {
    const c = _clientByWid[String(workitemId)];
    return c ? `${sep}client=${encodeURIComponent(c)}` : '';
  }
  window.NexoraWorkitemDetail.render = function (workitemId, containerEl, opts) {
    const { readOnly = false, perms = {} } = opts || {};
    if (!containerEl) return;
    const wid = String(workitemId);
    // Workitem ids are not unique across clients, so every detail request
    // must say which client's row was clicked.
    _clientByWid[wid] = (opts && opts.client) || containerEl.dataset.client || '';
    const status = containerEl.dataset.status || (opts && opts.status) || '';
    const currentStage = containerEl.dataset.currentStage || (opts && opts.currentStage) || '';
    containerEl.innerHTML = buildPanelMarkup(wid, status, currentStage, perms, readOnly);
    renderWorkitemTimeline(containerEl.querySelector('[id^="timeline-container-"]'));
    _renderHeaderChip(wid, opts);            // filled in Task 3.4; no-op until then
    loadDetailData(wid, perms);
    return wid;
  };
  const _PREPARED_DOCS_URL = API_PREFIX + "prepared_documents";
  function _renderHeaderChip(workitemId, opts) {
    const pid = opts && opts.inRegisterPid;
    if (!pid) return;
    const host = document.getElementById(`detail-panel-header-${workitemId}`);
    if (!host) return;
    const url = `${_PREPARED_DOCS_URL}?pid=${encodeURIComponent(pid)}`;
    host.innerHTML = `<a href="${url}" class="nx-label nx-label--blue inline-flex items-center gap-1"
      data-testid="workitem-in-register"><i class="fas fa-clipboard-list"></i>${I18N.inRegister}</a>`;
  }

  window.NexoraWorkitemDetail.attachLightbox = function (cfg) {
    // --- closure-local state per instance ---
    let currentImages = [];
    let currentIndex = 0;

    // --- resolve shell elements from the explicit id-map ---
    const modal = document.getElementById(cfg.modal);
    const modalImg = document.getElementById(cfg.image);
    const srcHlLayer = document.getElementById(cfg.hlLayer);
    const srcHlToggle = document.getElementById(cfg.hlToggle);
    const srcHlToggleLabel = document.getElementById(cfg.hlToggleLabel);

    // No-op when the shell is absent (e.g. partial rendered without the modal markup).
    if (!modal) return { openForWorkitem() {}, close() {} };

    // Optional extras (workitems page only): thumb rail, side-by-side pages, 1/2/3 switch.
    const thumbsEl = document.getElementById(cfg.thumbs);
    const sideEl = document.getElementById(cfg.side);
    const layoutEl = document.getElementById(cfg.layout);
    let cols = Math.min(3, Math.max(1, parseInt(localStorage.getItem('srcLightboxCols') || '1', 10) || 1));

    // Thumb rail: click = jump; the pages currently on screen are marked.
    function renderThumbs() {
        if (!thumbsEl) return;
        thumbsEl.innerHTML = '';
        thumbsEl.hidden = currentImages.length <= 1;
        currentImages.forEach((src, i) => {
            const im = document.createElement('img');
            im.src = src; im.alt = String(i + 1); im.title = String(i + 1);
            if (i === currentIndex) im.className = 'is-active';
            else if (i > currentIndex && i < currentIndex + cols) im.className = 'is-shown';
            im.addEventListener('click', (e) => { e.stopPropagation(); showImage(i); });
            thumbsEl.appendChild(im);
        });
    }
    // Extra pages beside the main one (no source overlay on these -- the
    // overlay is bound to #modalImage; click one to make it the main page).
    function renderSide() {
        if (!sideEl) return;
        sideEl.innerHTML = '';
        for (let i = currentIndex + 1; i < Math.min(currentImages.length, currentIndex + cols); i++) {
            const im = document.createElement('img');
            im.src = currentImages[i]; im.alt = String(i + 1); im.className = 'src-modal-side__page';
            im.addEventListener('click', (e) => { e.stopPropagation(); showImage(i); });
            sideEl.appendChild(im);
        }
    }
    function renderLayout() {
        if (!layoutEl) return;
        layoutEl.hidden = currentImages.length <= 1;
        layoutEl.querySelectorAll('[data-cols]').forEach(b => b.classList.toggle('is-active', parseInt(b.dataset.cols, 10) === cols));
    }
    if (layoutEl) layoutEl.addEventListener('click', (e) => {
        const b = e.target.closest('[data-cols]');
        if (!b) return;
        e.stopPropagation();
        cols = parseInt(b.dataset.cols, 10);
        localStorage.setItem('srcLightboxCols', String(cols));
        showImage(currentIndex);
    });

    // --- modal-scoped button lookups (prevents collision with other .modal-close elements) ---
    const closeBtn = modal.querySelector('.modal-close');
    const prevBtn = modal.querySelector('.modal-prev');
    const nextBtn = modal.querySelector('.modal-next');

    // ---- Source highlighting (read-only: show where values were found) ----
    const srcHl = {
        on: localStorage.getItem('srcHlOn') === '1',
        workitemid: null,
        pendingPulse: null,
    };

    // Safety net: keep the overlay locked to the image's box if it changes size
    // after the initial draw for any reason other than the open zoom (e.g. the
    // values panel reflowing, late image decode, viewport resize). Skipped while a
    // zoom animation is mid-flight -- that frame is handled by drawOverlayWhenStable
    // once the animation finishes, so boxes never flash out of register.
    if (window.ResizeObserver && modalImg) {
        new ResizeObserver(() => {
            if (!modal || modal.style.display !== 'flex') return;
            const animating = modalImg.getAnimations && modalImg.getAnimations().length;
            if (!animating) renderModalOverlay();
        }).observe(modalImg);
    }

    function currentSources() {
        return window.allSources(srcHl.workitemid);
    }

    function hasAnyLocation() {
        return currentSources().some(s => (s.locations || []).length > 0);
    }

    function renderModalOverlay(pulseKey) {
        if (!srcHlLayer || !modalImg) return;
        srcHlLayer.innerHTML = '';
        // Only offer the toggle when this document actually has locations.
        if (srcHlToggle) {
            srcHlToggle.hidden = !hasAnyLocation();
            srcHlToggle.classList.toggle('is-on', srcHl.on);
            if (srcHlToggleLabel) {
                srcHlToggleLabel.textContent = srcHl.on
                    ? I18N.hideSources : I18N.showSources;
            }
        }
        if (!srcHl.on && !pulseKey) return;
        const natW = modalImg.naturalWidth, natH = modalImg.naturalHeight;
        if (!natW || !natH) return;  // image not decoded yet
        // Measure the image's LAYOUT box (offset*), NOT getBoundingClientRect().
        // getBoundingClientRect() returns the *visual* (post-transform) rect, so
        // reading it while the lightbox zoom animation (scale 0.5 -> 1) is mid-flight
        // pinned the overlay to a shrunken frame that was never updated once the zoom
        // settled -> boxes stranded in blank space, and "jumping" on hide/show because
        // the re-render then measured the settled rect. offset* is transform-immune,
        // so the overlay always maps to the final displayed page. The layer is
        // position:absolute inside #imageModal, so offsetLeft/Top share its space.
        const w = modalImg.offsetWidth, h = modalImg.offsetHeight;
        if (!w || !h) return;  // not laid out yet
        srcHlLayer.style.left = modalImg.offsetLeft + 'px';
        srcHlLayer.style.top = modalImg.offsetTop + 'px';
        srcHlLayer.style.width = w + 'px';
        srcHlLayer.style.height = h + 'px';
        currentSources().forEach(src => {
            (src.locations || []).forEach(loc => {
                if (loc.page !== currentIndex) return;
                const confCls = window.srcConfClass(src.confidence);
                const box = document.createElement('div');
                box.className = 'src-hl-box'
                    + (confCls ? ' ' + confCls : '')
                    + (src.kind === 'cell' ? ' src-hl-box--cell' : '')
                    + (pulseKey && src.key === pulseKey ? ' is-pulse' : '');
                box.style.left = (loc.rect.left / natW * w) + 'px';
                box.style.top = (loc.rect.top / natH * h) + 'px';
                box.style.width = (loc.rect.width / natW * w) + 'px';
                box.style.height = (loc.rect.height / natH * h) + 'px';
                const confPct = window.srcConfPct(src.confidence);
                box.title = src.label + ': ' + (src.value == null ? '' : src.value)
                    + (confPct ? ' (' + confPct + ')' : '');
                srcHlLayer.appendChild(box);
            });
        });
    }

    function setSrcHl(on) {
        srcHl.on = on;
        localStorage.setItem('srcHlOn', on ? '1' : '0');
        renderModalOverlay();
        window.refreshThumbOverlays();
    }

    // A value/cell was clicked to locate it -> make sure source boxes are on so
    // the user sees them in context. The toggle flips to "Hide sources" on the
    // next renderModalOverlay (driven by showImage). No-op if already on.
    function ensureSourcesOn() {
        if (srcHl.on) return;
        srcHl.on = true;
        localStorage.setItem('srcHlOn', '1');
        window.refreshThumbOverlays();
    }

    // Open the lightbox for a specific workitem + page (used by click-to-locate
    // and the thumbnail click handler). pulseKey flashes one field's box.
    function openModalForWorkitem(workitemid, index, pulseKey) {
        const ic = document.getElementById('image-container-' + workitemid);
        if (!ic) return;
        const allImages = Array.from(ic.querySelectorAll('.workitem-image'));
        if (!allImages.length) return;
        currentImages = allImages.map(img => img.src);
        srcHl.workitemid = String(workitemid);
        srcHl.pendingPulse = pulseKey || null;
        if (pulseKey) ensureSourcesOn();   // located via a value click -> show boxes
        renderReviewPanel(String(workitemid));
        modal.style.display = 'flex';
        showImage(Math.min(Math.max(index, 0), currentImages.length - 1));
    }

    // Fill the in-lightbox review panel (right pane) with the workitem's extracted
    // values, reusing the exact same rows as the inline panel. Hidden (image goes
    // full-width) when the document has no extracted values.
    function renderReviewPanel(workitemid) {
        const panel = document.getElementById(cfg.reviewPanel);
        const body = document.getElementById(cfg.reviewPanelBody);
        if (!panel || !body) return;
        const html = window.buildSourceDetailsHtml(workitemid, { tables: false });
        body.innerHTML = html;
        panel.hidden = !html;
        renderReviewTables(workitemid);
    }

    // Line-item tables get their own box UNDER the page, spanning the image
    // pane only -- a table squeezed into the values sidebar has to scroll for
    // every column. The box is created lazily so the three templates carrying
    // this modal (workitems, prepared documents, reporting) need no markup.
    function reviewTablesBox() {
        const panel = document.getElementById(cfg.reviewPanel);
        const modalBody = panel && panel.closest('.src-modal-body');
        if (!modalBody) return null;
        let box = modalBody.querySelector('.src-modal-tables');
        if (!box) {
            box = document.createElement('div');
            box.className = 'src-modal-tables';
            modalBody.appendChild(box);
        }
        return box;
    }

    function renderReviewTables(workitemid) {
        const box = reviewTablesBox();
        if (!box) return;
        const html = window.renderTableGrids(workitemid);
        box.innerHTML = html;
        box.hidden = !html;
    }

    // Render the overlay only once the displayed page is geometrically SETTLED:
    // (1) the image bitmap is decoded (so its layout box reflects the real page
    // aspect) and (2) the open-zoom animation (scale 0.5 -> 1) has finished. The
    // overlay layer is a SIBLING of the image, so it never inherits that zoom
    // transform -- drawing mid-animation strands the boxes off the still-scaling
    // page (boxes already visible but in the wrong place), and they only snapped
    // into register on a later hide/show that re-rendered against the settled
    // image. Waiting for each running animation's `finished` promise makes the
    // boxes appear already aligned. With no animation running (e.g. reopening the
    // same lightbox, or prev/next navigation) it renders immediately.
    function drawOverlayWhenStable(pulse) {
        const render = () => requestAnimationFrame(() => renderModalOverlay(pulse));
        const afterDecode = () => {
            const anims = modalImg.getAnimations ? modalImg.getAnimations() : [];
            if (anims.length) Promise.allSettled(anims.map(a => a.finished)).then(render);
            else render();
        };
        if (modalImg.complete && modalImg.naturalWidth) afterDecode();
        else modalImg.addEventListener('load', afterDecode, { once: true });
    }

    function showImage(index) {
        if (index >= 0 && index < currentImages.length) {
            modalImg.src = currentImages[index];
            currentIndex = index;
            // hidden attr, not style.display: an inline display:block would undo
            // the button's inline-flex centring (the chevron escaped its box).
            prevBtn.hidden = !(index > 0);
            nextBtn.hidden = !(index < currentImages.length - 1);
            renderThumbs(); renderSide(); renderLayout();
            const pulse = srcHl.pendingPulse;
            srcHl.pendingPulse = null;
            drawOverlayWhenStable(pulse);
        }
    }

    // renderThumbOverlay / refreshThumbOverlays are defined at module scope
    // (near loadImage) so loadImage's onload handler can reach them.

    const closeModal = () => {
        modal.style.display = "none";
        currentImages = [];
        currentIndex = 0;
        if (srcHlLayer) srcHlLayer.innerHTML = '';
        if (thumbsEl) { thumbsEl.innerHTML = ''; thumbsEl.hidden = true; }
        if (sideEl) sideEl.innerHTML = '';
        const tbox = document.querySelector('.src-modal-tables');
        if (tbox) { tbox.innerHTML = ''; tbox.hidden = true; }
    };

    document.addEventListener('click', (event) => {
        if (event.target.classList.contains('workitem-image')) {
            const imageContainer = event.target.closest('[id^="image-container-"]');
            if (!imageContainer) return;
            const workitemid = imageContainer.id.replace('image-container-', '');
            const allImages = Array.from(imageContainer.querySelectorAll('.workitem-image'));
            const clickedIndex = allImages.findIndex(img => img.src === event.target.src);
            if (clickedIndex !== -1) {
                openModalForWorkitem(workitemid, clickedIndex, null);
            }
        }
    });

    // "Show sources" (Document details column header) -> open the lightbox
    // at page 1 with source boxes already on, via THIS instance's own
    // ensureSourcesOn/openModalForWorkitem closures.
    document.addEventListener('click', (event) => {
        const btn = event.target.closest('.wi-show-sources-btn');
        if (!btn) return;
        ensureSourcesOn();
        openModalForWorkitem(btn.dataset.workitemid, 0, null);
    });

    // Click a field value with a known location -> open the page + pulse its box.
    document.addEventListener('click', (event) => {
        const row = event.target.closest('.src-field-row.is-locatable');
        if (!row) return;
        const fc = row.closest('[data-src-wid]');
        if (!fc) return;
        const workitemid = fc.dataset.srcWid;
        openModalForWorkitem(workitemid, parseInt(row.dataset.page || '0', 10), row.dataset.key);
    });

    // Click a value/cell in the in-lightbox review panel -> the modal is already
    // open, so just navigate to that field's page and pulse its box.
    document.addEventListener('click', (event) => {
        const panel = document.getElementById(cfg.reviewPanel);
        if (!panel) return;
        const row = event.target.closest('.src-field-row.is-locatable');
        if (!row || !row.closest('.src-modal-values, .src-modal-tables')) return;
        ensureSourcesOn();   // clicking a value turns boxes on (toggle -> "Hide sources")
        srcHl.pendingPulse = row.dataset.key;
        showImage(parseInt(row.dataset.page || '0', 10));
    });

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (modal) modal.addEventListener('click', (event) => {
        // Close when clicking the backdrop or the empty letterbox area around the
        // page (but not the image, the values panel, the nav arrows or the toggle).
        if (event.target === modal || event.target.classList.contains('src-modal-page')) {
            closeModal();
        }
    });

    if (prevBtn) prevBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showImage(currentIndex - 1);
    });

    if (nextBtn) nextBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showImage(currentIndex + 1);
    });

    if (srcHlToggle) srcHlToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        setSrcHl(!srcHl.on);
    });
    window.addEventListener('resize', () => {
        if (modal.style.display === 'flex') renderModalOverlay();
    });

    document.addEventListener('keydown', (event) => {
        if (modal.style.display === "flex") {
            if (event.key === 'Escape') {
                closeModal();
            } else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                showImage(currentIndex - 1);
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                showImage(currentIndex + 1);
            }
        }
    });

    return { openForWorkitem: openModalForWorkitem, close: closeModal };
  };

  Object.assign(window.NexoraWorkitemDetail, {
    loadDetailData, loadHistory, renderWorkitemTimeline,
    loadImage, loadImagesInBatch, buildSourceDetailsHtml,
    renderTableGrids, tableCellSources, allSources, srcEsc, renderThumbOverlay,
    refreshThumbOverlays,
  });
  window.srcEsc = srcEsc; window.tableCellSources = tableCellSources;
  window.allSources = allSources; window.renderTableGrids = renderTableGrids;
  window.buildSourceDetailsHtml = buildSourceDetailsHtml;
  window.renderThumbOverlay = renderThumbOverlay; window.refreshThumbOverlays = refreshThumbOverlays;
  window.loadImage = loadImage; window.loadImagesInBatch = loadImagesInBatch;
  window.loadHistory = loadHistory;
  window.renderWorkitemTimeline = renderWorkitemTimeline;
})();

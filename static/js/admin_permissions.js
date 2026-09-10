/* Permissions x profiles grid (#238). Data arrives via window.NX_PERMS
   (templates/js/admin/_permissions_js.html); this file carries no Jinja.
   NX.apiSafe resolves a leading "/" through API_PREFIX itself. */
(function () {
  const S = window.NX_PERMS, grid = document.getElementById('permsGrid');
  if (!grid) return;
  const granted = new Set(S.grants.map(([a, p]) => `${a}:${p}`));
  const dirty = new Map();  // "a:p" -> bool
  const boxes = [...grid.querySelectorAll('input[type=checkbox]')];
  boxes.forEach(b => { b.checked = granted.has(`${b.dataset.accessId}:${b.dataset.permId}`); });

  function applyGates() {   // grey a child cell while its object's .view is unchecked in that column
    const state = {};
    grid.querySelectorAll('tr.perm-row').forEach(tr => {
      if (!tr.dataset.code.endsWith('.view')) return;
      tr.querySelectorAll('input').forEach(b => { state[`${tr.dataset.code}|${b.dataset.accessId}`] = b.checked; });
    });
    grid.querySelectorAll('tr.perm-row[data-gate]').forEach(tr => {
      const gate = tr.dataset.gate; if (!gate) return;
      tr.querySelectorAll('input').forEach(b => {
        const ok = state[`${gate}|${b.dataset.accessId}`];
        if (ok === undefined) return;
        b.closest('td').style.opacity = ok ? '' : '0.35';
        b.closest('td').title = ok ? '' : S.i18n.needsView;
      });
    });
  }
  function refreshDirty() {
    const n = [...dirty.entries()].filter(([k, v]) => v !== granted.has(k)).length;
    document.getElementById('permsDirty').textContent = n ? S.i18n.changes.replace('{n}', n) : '';
    const save = document.getElementById('permsSave'); if (save) save.disabled = !n;
  }
  grid.addEventListener('change', e => {
    const b = e.target; if (b.type !== 'checkbox') return;
    b.closest('td').classList.toggle('perm-dirty', b.checked !== granted.has(`${b.dataset.accessId}:${b.dataset.permId}`));
    dirty.set(`${b.dataset.accessId}:${b.dataset.permId}`, b.checked);
    applyGates(); refreshDirty();
  });
  document.getElementById('permsSave')?.addEventListener('click', async () => {
    const changes = [...dirty.entries()].filter(([k, v]) => v !== granted.has(k))
      .map(([k, v]) => { const [a, p] = k.split(':').map(Number); return { accessId: a, permissionId: p, granted: v }; });
    const res = await NX.apiSafe('/api/admin/profiles/grants', { method: 'POST', body: JSON.stringify({ changes }) });
    if (!res.ok || !res.data || !res.data.success) { NX.toast(S.i18n.failed, 'error'); return; }
    changes.forEach(c => { const k = `${c.accessId}:${c.permissionId}`; c.granted ? granted.add(k) : granted.delete(k); });
    dirty.clear(); grid.querySelectorAll('.perm-dirty').forEach(td => td.classList.remove('perm-dirty'));
    refreshDirty(); NX.toast(S.i18n.saved, 'success');
  });
  document.getElementById('permsFilter').addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    grid.querySelectorAll('tr.perm-row').forEach(tr => { tr.hidden = !!q && !tr.dataset.search.includes(q); });
    grid.querySelectorAll('tr.perm-area, tr.perm-object').forEach(tr => {
      const rows = [...grid.querySelectorAll(`tr.perm-row[data-area="${tr.dataset.area}"]`)];
      tr.hidden = !!q && rows.every(r => r.hidden);
    });
  });

  // ---- catalogue (admin.permissions.edit) ----
  const modal = document.getElementById('permissionMetaModal');
  function openModal(id, code, desc) {
    document.getElementById('permMetaModalTitle').textContent = id ? S.i18n.editPermission : S.i18n.addPermission;
    document.getElementById('permMetaId').value = id || '';
    document.getElementById('permMetaCode').value = code || '';
    document.getElementById('permMetaDescription').value = desc || '';
    modal.classList.remove('hidden'); setTimeout(() => modal.classList.remove('opacity-0'), 10);
  }
  function closeModal() { modal.classList.add('opacity-0'); setTimeout(() => modal.classList.add('hidden'), 300); }
  document.getElementById('permsAdd')?.addEventListener('click', () => openModal('', '', ''));
  modal?.querySelector('[data-testid="admin-perms-modal-close"]')?.addEventListener('click', closeModal);
  modal?.querySelector('[data-testid="admin-perms-modal-cancel"]')?.addEventListener('click', closeModal);
  modal?.querySelector('[data-testid="admin-perms-modal-save"]')?.addEventListener('click', async () => {
    const id = document.getElementById('permMetaId').value;
    const code = document.getElementById('permMetaCode').value.trim();
    const description = document.getElementById('permMetaDescription').value.trim();
    if (!code || !description) { NX.toast(S.i18n.codeDescRequired, 'error'); return; }
    const url = id ? `/api/admin/permissions/edit/${id}` : '/api/admin/permissions/add';
    const res = await NX.apiSafe(url, { method: 'POST', body: JSON.stringify({ code, description }) });
    if (!res.ok || !res.data || !res.data.success) { NX.toast((res.data && res.data.message) || S.i18n.failed, 'error'); return; }
    location.reload();
  });

  grid.addEventListener('click', async e => {
    const head = e.target.closest('tr.perm-area'); if (head) {
      const collapsed = head.classList.toggle('collapsed');
      grid.querySelectorAll(`tr[data-area="${head.dataset.area}"]:not(.perm-area)`).forEach(r => { r.hidden = collapsed; });
      return;
    }
    const tr = e.target.closest('tr.perm-row'); if (!tr) return;
    const edit = e.target.closest('.perm-edit');
    if (edit) { openModal(tr.dataset.permId, tr.dataset.code, edit.dataset.desc); return; }
    const del = e.target.closest('.perm-delete');
    if (del) {   // two clicks, no dialog (dialogs block automation and CSP-safe code alike)
      if (!del.classList.contains('is-armed')) { del.classList.add('is-armed'); del.title = S.i18n.confirmDelete; return; }
      const res = await NX.apiSafe(`/api/admin/permissions/delete/${tr.dataset.permId}`, { method: 'DELETE' });
      if (!res.ok || !res.data || !res.data.success) { NX.toast((res.data && res.data.message) || S.i18n.failed, 'error'); del.classList.remove('is-armed'); return; }
      tr.remove(); return;
    }
    const cell = e.target.closest('tr.perm-row > td:first-child'); if (!cell) return;
    const aside = document.getElementById('permsHolders');
    // api_admin_permission_holders -> {success, permission:{...}, holders:[{userID, username, fullname, organization, source}]}
    const r = await NX.apiSafe(`/api/admin/permissions/${tr.dataset.permId}/holders`);
    const holders = (r.data && r.data.holders) || [];
    aside.hidden = false;
    aside.innerHTML = `<h3 class="nx-section nx-mono" style="font-size:13px;word-break:break-all">${NX.esc(tr.dataset.code)}</h3>` +
      (holders.length ? `<div class="nx-meta" style="margin:8px 0 4px">${NX.esc(S.i18n.holders)}</div><ul class="perm-holders">${holders.map(u => `<li>${NX.esc(u.fullname || u.username)} <span class="nx-meta">${NX.esc(u.organization || '')} · ${NX.esc(u.source || '')}</span></li>`).join('')}</ul>`
                      : `<div class="nx-meta" style="margin-top:8px">${NX.esc(S.i18n.nobody)}</div>`);
  });
  applyGates();

  // ---- override badges (#275): per (profile, permission) count of users
  // with a personal allow/deny override, shown as a small badge on the cell
  // instead of only via the "click the row to see holders" panel. ----
  const profileNames = {};
  grid.querySelectorAll('thead th[data-access-id]').forEach(th => { profileNames[th.dataset.accessId] = th.querySelector('.nx-mono')?.textContent || ''; });
  const overrideCounts = {};  // "a:p" -> {A: n, D: n}
  (S.overrides || []).forEach(([a, p, effect, n]) => {
    const k = `${a}:${p}`;
    (overrideCounts[k] || (overrideCounts[k] = {}))[effect] = n;
  });
  Object.entries(overrideCounts).forEach(([k, counts]) => {
    const [a, p] = k.split(':');
    const badge = grid.querySelector(`sup.perm-override-badge[data-testid="admin-perms-override-${a}-${p}"]`);
    if (!badge) return;
    const allow = counts.A || 0, deny = counts.D || 0;
    const n = allow + deny;
    if (!n) return;
    badge.textContent = n;
    badge.hidden = false;
    badge.classList.toggle('perm-override-deny', deny > 0 && allow === 0);
    const profile = profileNames[a] || a;
    const parts = [];
    if (allow) parts.push(S.i18n.overrideAllow.replace('{n}', allow).replace('{profile}', profile));
    if (deny) parts.push(S.i18n.overrideDeny.replace('{n}', deny).replace('{profile}', profile));
    badge.title = parts.join(' · ');
  });

  // ---- column picker: show/hide + reorder profile columns (#275) ----
  const LS_KEY = 'nx.permsGrid.columns';
  const allIds = [...grid.querySelectorAll('thead th[data-access-id]')].map(th => th.dataset.accessId);
  const columnsPanel = document.getElementById('permsColumnsPanel');
  const columnsList = document.getElementById('permsColumnsList');
  const columnsBtn = document.getElementById('permsColumnsBtn');

  function loadColumnState() {
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { /* ponytail: corrupt/blocked storage falls back to defaults */ }
    const known = new Set(allIds);
    let order = (stored && Array.isArray(stored.order) ? stored.order.filter(id => known.has(id)) : []);
    allIds.forEach(id => { if (!order.includes(id)) order.push(id); });  // new profiles appended at the end
    const hidden = new Set((stored && Array.isArray(stored.hidden) ? stored.hidden : []).filter(id => known.has(id)));
    return { order, hidden };
  }
  function saveColumnState(state) {
    try { localStorage.setItem(LS_KEY, JSON.stringify({ order: state.order, hidden: [...state.hidden] })); } catch (e) { /* ponytail: quota/blocked storage, state just won't persist */ }
  }
  function applyColumnState(state) {
    grid.querySelectorAll('thead tr, tbody tr.perm-row').forEach(row => {
      const cells = {};
      row.querySelectorAll(':scope > th[data-access-id], :scope > td[data-access-id]').forEach(cell => { cells[cell.dataset.accessId] = cell; });
      state.order.forEach(id => { if (cells[id]) row.appendChild(cells[id]); });
    });
    grid.querySelectorAll('th[data-access-id], td[data-access-id]').forEach(cell => { cell.hidden = state.hidden.has(cell.dataset.accessId); });
    state.order.forEach(id => {
      const row = columnsList.querySelector(`.perms-columns-row[data-access-id="${id}"]`);
      if (row) columnsList.appendChild(row);
    });
    columnsList.querySelectorAll('.perms-col-toggle').forEach(cb => { cb.checked = !state.hidden.has(cb.dataset.accessId); });
  }

  let colState = loadColumnState();
  applyColumnState(colState);

  columnsBtn?.addEventListener('click', () => { columnsPanel.hidden = !columnsPanel.hidden; });
  document.addEventListener('click', e => {
    if (!columnsPanel || columnsPanel.hidden) return;
    if (!columnsPanel.contains(e.target) && e.target !== columnsBtn && !columnsBtn.contains(e.target)) columnsPanel.hidden = true;
  });
  columnsList?.addEventListener('change', e => {
    const cb = e.target.closest('.perms-col-toggle'); if (!cb) return;
    const id = cb.dataset.accessId;
    cb.checked ? colState.hidden.delete(id) : colState.hidden.add(id);
    applyColumnState(colState); saveColumnState(colState);
  });
  columnsList?.addEventListener('click', e => {
    const row = e.target.closest('.perms-columns-row'); if (!row) return;
    const id = row.dataset.accessId;
    const i = colState.order.indexOf(id);
    if (e.target.closest('.perms-col-up') && i > 0) {
      [colState.order[i - 1], colState.order[i]] = [colState.order[i], colState.order[i - 1]];
    } else if (e.target.closest('.perms-col-down') && i < colState.order.length - 1) {
      [colState.order[i + 1], colState.order[i]] = [colState.order[i], colState.order[i + 1]];
    } else return;
    applyColumnState(colState); saveColumnState(colState);
  });
  document.getElementById('permsColumnsReset')?.addEventListener('click', () => {
    try { localStorage.removeItem(LS_KEY); } catch (e) { /* ponytail: nothing to clear */ }
    colState = { order: [...allIds], hidden: new Set() };
    applyColumnState(colState);
  });
})();

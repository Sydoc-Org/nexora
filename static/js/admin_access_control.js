/* Admin Access Control page behaviour (#191 shim-ification). Jinja-rendered
   i18n lives in the paired shim, templates/js/admin/_access_control_js.html,
   as window.NX_I18N_ADMIN_ACCESS_CONTROL. This file reads from that global
   -- it carries no Jinja of its own and never will. `csrfToken` is a
   page-level global declared by static/js/header.js.
   Since #238 the page keeps two tabs: Users and Access Profiles. Grants
   live on /admin/permissions; per-user overrides on /admin/users/<id>. */
(function () {
const API_PREFIX = window.API_PREFIX;
const I18N = window.NX_I18N_ADMIN_ACCESS_CONTROL;

const userModal    = document.getElementById('userModal');
const profileModal = document.getElementById('profileModal');

let allUsersData = [];

// ── Profile badge colours (cycled by AccessProfileID) ────────────
const PROFILE_COLORS = [
    'bg-indigo-100 text-indigo-700 border-indigo-200',
    'bg-emerald-100 text-emerald-700 border-emerald-200',
    'bg-blue-100 text-blue-700 border-blue-200',
    'bg-violet-100 text-violet-700 border-violet-200',
    'bg-orange-100 text-orange-700 border-orange-200',
    'bg-teal-100 text-teal-700 border-teal-200',
    'bg-rose-100 text-rose-700 border-rose-200',
    'bg-amber-100 text-amber-700 border-amber-200',
];
function profileBadge(name, accessId) {
    if (!name) return `<span class="text-xs italic text-red-400">${I18N.noProfile}</span>`;
    const c = PROFILE_COLORS[(accessId || 0) % PROFILE_COLORS.length];
    return `<span class="px-2.5 py-0.5 rounded-full text-xs font-medium border ${c}">${escapeHtml(name)}</span>`;
}

const showNotification = window.NX.toast;
const escapeHtml = window.NX.esc;

function openCenterModal(el) {
    el.classList.remove('hidden');
    setTimeout(() => {
        el.classList.remove('opacity-0');
        const inner = el.querySelector('.modal-content, div.transform');
        if (inner) inner.classList.remove('scale-95');
    }, 10);
}
function closeCenterModal(el) {
    el.classList.add('opacity-0');
    const inner = el.querySelector('.modal-content, div.transform');
    if (inner) inner.classList.add('scale-95');
    setTimeout(() => el.classList.add('hidden'), 300);
}

// ── Tabs ──────────────────────────────────────────────────────────
const TAB_IDS = ['users', 'profiles'];

function switchTab(tabName) {
    TAB_IDS.forEach(id => {
        document.getElementById(`tab-${id}`)?.classList.add('hidden');
        document.getElementById(`tab-${id}-btn`)?.classList.remove('is-active');
    });
    document.getElementById(`tab-${tabName}`)?.classList.remove('hidden');
    document.getElementById(`tab-${tabName}-btn`)?.classList.add('is-active');
}

// ── USERS TAB ─────────────────────────────────────────────────────
async function fetchAllUsers() {
    try {
        const profileEl = document.getElementById('userProfileFilter');
        const orgEl     = document.getElementById('userOrgFilter');
        const params = new URLSearchParams();
        if (profileEl && profileEl.value) params.set('profile', profileEl.value);
        if (orgEl && orgEl.value)         params.set('organization', orgEl.value);

        const url = `${API_PREFIX}api/admin/users${params.toString() ? '?' + params.toString() : ''}`;
        const res = await fetch(url, {
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
        });
        if (!res.ok) throw new Error();
        allUsersData = await res.json();
        renderUsersTable(allUsersData);
        filterUsersTable();
    } catch {
        document.getElementById('usersTableBody').innerHTML =
            `<tr><td colspan="6" class="admin-empty" style="color:var(--nx-danger)">${I18N.errorLoadingData}</td></tr>`;
    }
}

function renderUsersTable(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="admin-empty">${I18N.noUsersFound}</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    users.forEach(u => {
        const badge = profileBadge(u.AccessProfileName, u.AccessProfileID);
        const overrideBadge = u.OverrideCount > 0
            ? `<span class="px-2 py-0.5 text-xs font-medium text-yellow-700 bg-yellow-100 rounded-full border border-yellow-200 whitespace-nowrap">${u.OverrideCount} ${I18N.overrides}</span>`
            : `<span class="px-2 py-0.5 text-xs text-gray-400 bg-gray-100 rounded-full whitespace-nowrap">${I18N.defaultLabel}</span>`;

        const tr = document.createElement('tr');
        tr.className = 'is-clickable';
        tr.id = `user-row-${u.userID}`;
        tr.onclick = () => { window.location.href = `${API_PREFIX}admin/users/${encodeURIComponent(u.userID)}`; };
        tr.setAttribute('data-testid', `admin-ac-user-row-${u.userID}`);
        tr.innerHTML = `
            <td></td>
            <td>
                <div class="font-medium text-gray-900 text-sm">${escapeHtml(u.fullname)}</div>
                <div class="text-xs text-gray-400">@${escapeHtml(u.username)}</div>
                <div class="text-xs text-gray-400">${escapeHtml(u.email || '')}</div>
            </td>
            <td>${badge}</td>
            <td class="text-sm text-gray-600">${escapeHtml(u.organization || '—')}</td>
            <td class="text-center">${overrideBadge}</td>
            <td class="align-right"><i class="fas fa-chevron-right" style="color:var(--nx-text-meta);font-size:12px"></i></td>
        `;
        tbody.appendChild(tr);
    });
}

function clearUserFilters() {
    const search = document.getElementById('userSearchInput');
    const prof   = document.getElementById('userProfileFilter');
    const org    = document.getElementById('userOrgFilter');
    if (search) search.value = '';
    if (prof)   prof.value   = '';
    if (org)    org.value    = '';
    updateClearFilterVisibility();
    fetchAllUsers();
}

function updateClearFilterVisibility() {
    const wrap = document.getElementById('userClearFiltersWrap');
    if (!wrap) return;
    const hasAny =
        (document.getElementById('userSearchInput')?.value || '').trim() !== '' ||
        (document.getElementById('userProfileFilter')?.value || '') !== '' ||
        (document.getElementById('userOrgFilter')?.value || '') !== '';
    wrap.style.display = hasAny ? '' : 'none';
}

function filterUsersTable() {
    const q = document.getElementById('userSearchInput').value.toLowerCase();
    renderUsersTable(allUsersData.filter(u =>
        (u.fullname || '').toLowerCase().includes(q) ||
        (u.username || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q) ||
        (u.AccessProfileName || '').toLowerCase().includes(q) ||
        (u.organization || '').toLowerCase().includes(q)
    ));
}

// ── USER CRUD ─────────────────────────────────────────────────────
// Ticked (the default) = the backend generates the password and mails a
// set-password link, so the field is neither shown nor required.
function syncInviteToggle() {
    const invite = document.getElementById('send_invite').checked;
    document.getElementById('passwordField').classList.toggle('hidden', invite);
    const pw = document.getElementById('password');
    pw.required = !invite;
    if (invite) pw.value = '';
}

document.getElementById('send_invite')?.addEventListener('change', syncInviteToggle);

function openAddUserModal() {
    document.getElementById('userForm').reset();
    syncInviteToggle();
    openCenterModal(userModal);
}

function closeUserModal() { closeCenterModal(userModal); }

document.getElementById('userForm')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(this).entries());

    try {
        const res = await fetch(`${API_PREFIX}admin/users/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(data)
        });
        if (res.status === 403) {
            showNotification(I18N.noPermissionCreateUsers, 'error');
            return;
        }
        const result = await res.json();
        if (res.ok && result.success) {
            closeUserModal();
            showNotification(result.message || I18N.userCreatedSuccessfully);
            fetchAllUsers();
        } else {
            showNotification(`${I18N.errorPrefix} ${result.message}`, 'error');
        }
    } catch {
        showNotification(I18N.networkError, 'error');
    }
});

// ── ACCESS PROFILES TAB (name, description, rank) ─────────────────
function openProfileModal(id, name, desc, rank, org) {
    document.getElementById('profileModalTitle').textContent = id ? `${I18N.editProfilePrefix} ${name}` : I18N.createNewAccessProfile;
    document.getElementById('profileId').value   = id || '';
    document.getElementById('profileName').value = name || '';
    document.getElementById('profileDesc').value = desc || '';
    document.getElementById('profileRank').value = rank ?? '';
    const orgSel = document.getElementById('profileOrg'); if (orgSel) orgSel.value = org || '';
    openCenterModal(profileModal);
}
function closeProfileModal() { closeCenterModal(profileModal); }

async function saveProfile() {
    const id = document.getElementById('profileId').value;
    const payload = {
        accessId:    id ? Number(id) : null,
        name:        document.getElementById('profileName').value.trim(),
        description: document.getElementById('profileDesc').value.trim(),
        rank:        Number(document.getElementById('profileRank').value || 0),
        organizationCode: document.getElementById('profileOrg')?.value || null,
    };
    try {
        const res = await fetch(`${API_PREFIX}api/admin/access_profile/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
            showNotification(result.message);
            closeProfileModal();
            localStorage.setItem('acl_tab', 'profiles');
            setTimeout(() => location.reload(), 600);
        } else {
            showNotification(result.message, 'error');
        }
    } catch {
        showNotification(I18N.networkError, 'error');
    }
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // #193 finding 10: onclick/oninput="" attribute handlers aren't
    // nonce-covered by CSP; bind them here instead.
    document.getElementById('tab-users-btn')?.addEventListener('click', () => switchTab('users'));
    document.getElementById('tab-profiles-btn')?.addEventListener('click', () => switchTab('profiles'));
    document.getElementById('userSearchInput')?.addEventListener('input', () => {
        filterUsersTable();
        updateClearFilterVisibility();
    });
    document.getElementById('userClearFiltersBtn')?.addEventListener('click', clearUserFilters);
    document.querySelector('[data-testid="admin-ac-add-user"]')?.addEventListener('click', openAddUserModal);
    document.querySelector('[data-testid="admin-ac-add-profile"]')?.addEventListener('click', () => openProfileModal('', '', '', '', ''));
    document.querySelector('[data-testid="admin-ac-user-modal-close"]')?.addEventListener('click', closeUserModal);
    document.querySelector('[data-testid="admin-ac-user-modal-cancel"]')?.addEventListener('click', closeUserModal);
    document.querySelector('[data-testid="admin-ac-profile-modal-close"]')?.addEventListener('click', closeProfileModal);
    document.querySelector('[data-testid="admin-ac-profile-modal-cancel"]')?.addEventListener('click', closeProfileModal);
    document.querySelector('[data-testid="admin-ac-profile-modal-save"]')?.addEventListener('click', saveProfile);
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.edit-access-profile-btn');
        if (btn) openProfileModal(btn.dataset.accessId, btn.dataset.name, btn.dataset.desc, btn.dataset.rank, btn.dataset.org);
    });

    fetchAllUsers();

    const saved = localStorage.getItem('acl_tab');
    if (saved && TAB_IDS.includes(saved)) {
        switchTab(saved);
        localStorage.removeItem('acl_tab');
    }

    ['userProfileFilter', 'userOrgFilter'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', () => {
            updateClearFilterVisibility();
            fetchAllUsers();
        });
    });

    // Deep-link from command palette: /admin/access_control#add-user
    if (window.location.hash === '#add-user') {
        switchTab('users');
        openAddUserModal();
        history.replaceState(null, '', window.location.pathname + window.location.search);
    }
});
}());

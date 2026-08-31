    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    function defaultIcon() {
        document.getElementById('profilePicture').src = window.NX_HEADER.defaultAvatar
    }
    // #193 finding 10: onerror="" attribute handlers aren't nonce-covered by CSP;
    // bind in JS instead.
    document.getElementById('profilePicture')?.addEventListener('error', defaultIcon);

    /* Dark mode + sidebar pin are applied pre-paint by the UI-prefs
       script in _header.html <head> (issue #155). */

    /* ---- Session liveness poll ----
       Polls /api/session/heartbeat every 30s. If the admin force-logs us out,
       the before_request hook returns 401 and we bounce to /login. 30s
       matches the server's session-alive cache TTL (nx_lib/user_cache.py):
       polling faster cannot detect a revocation sooner, and at ~500 users
       a 5s poll alone was ~100 req/s of pure overhead. */
    (function() {
        const PUBLIC_PATHS = ['/login', '/logout', '/forgot_password',
            '/set_new_password', '/init_reset', '/init_2FA', '/verify_2fa',
            '/reset_password'];
        if (PUBLIC_PATHS.some(p => window.location.pathname.startsWith(p))) return;

        let stopped = false;
        async function ping() {
            if (stopped) return;
            try {
                const r = await fetch(window.NX_HEADER.heartbeatUrl, {
                    credentials: 'same-origin',
                    cache: 'no-store',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                if (r.status === 401) {
                    stopped = true;
                    window.location.href = window.NX_HEADER.loginUrl;
                }
            } catch (e) {
                // Network blip — keep trying.
            }
        }
        // First check after 2s, then every 30s.
        setTimeout(ping, 2000);
        setInterval(ping, 30000);
    })();

    /* ---- Command palette (Ctrl/Cmd+K) ----
       Server populates the action list based on the user's permissions.
       Adding new commands later = appending to the array below. */
    (function() {
        const ACTIONS = window.NX_HEADER.commands;

        const overlay = document.getElementById('cmdkOverlay');
        const input   = document.getElementById('cmdkInput');
        const list    = document.getElementById('cmdkList');
        if (!overlay || !input || !list) return;

        let visible = false;
        let selectedIdx = 0;
        let filtered = ACTIONS.slice();

        function buildItem(action, index) {
            const li = document.createElement('li');
            li.className = 'cmdk-item' + (index === selectedIdx ? ' is-selected' : '');
            li.setAttribute('role', 'option');
            li.dataset.idx = String(index);

            const icon = document.createElement('i');
            icon.className = 'fas ' + (action.icon || 'fa-arrow-right') + ' cmdk-item-icon';
            li.appendChild(icon);

            const label = document.createElement('span');
            label.className = 'cmdk-item-label';
            label.textContent = action.label || '';
            li.appendChild(label);

            if (action.section) {
                const sec = document.createElement('span');
                sec.className = 'cmdk-item-section';
                sec.textContent = action.section;
                li.appendChild(sec);
            }

            li.addEventListener('click', () => activate(index));
            li.addEventListener('mouseenter', () => { selectedIdx = index; updateSelection(); });
            return li;
        }

        function render() {
            while (list.firstChild) list.removeChild(list.firstChild);
            if (filtered.length === 0) {
                const empty = document.createElement('li');
                empty.className = 'cmdk-empty';
                empty.textContent = window.NX_HEADER.i18n.noCommands;
                list.appendChild(empty);
                return;
            }
            filtered.forEach((a, i) => list.appendChild(buildItem(a, i)));
        }
        function updateSelection() {
            list.querySelectorAll('.cmdk-item').forEach((el, i) => {
                el.classList.toggle('is-selected', i === selectedIdx);
                if (i === selectedIdx) el.scrollIntoView({block: 'nearest'});
            });
        }
        function activate(i) {
            const a = filtered[i];
            if (!a) return;
            if (a.action === 'toggle-dark') {
                const dmToggle = document.getElementById('dark-mode-toggle');
                if (dmToggle) dmToggle.click();
                close();
                return;
            }
            if (a.url) {
                close();
                window.location.href = a.url;
            }
        }
        function applyFilter(q) {
            q = (q || '').trim().toLowerCase();
            if (!q) {
                filtered = ACTIONS.slice();
            } else {
                filtered = ACTIONS.filter(a =>
                    (a.label || '').toLowerCase().includes(q) ||
                    (a.section || '').toLowerCase().includes(q)
                );
            }
            selectedIdx = 0;
            render();
        }
        function open() {
            visible = true;
            overlay.hidden = false;
            input.value = '';
            applyFilter('');
            setTimeout(() => input.focus(), 10);
        }
        function close() {
            visible = false;
            overlay.hidden = true;
            input.blur();
        }

        input.addEventListener('input', e => applyFilter(e.target.value));

        input.addEventListener('keydown', e => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIdx = Math.min(filtered.length - 1, selectedIdx + 1);
                updateSelection();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIdx = Math.max(0, selectedIdx - 1);
                updateSelection();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                activate(selectedIdx);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                close();
            }
        });

        overlay.addEventListener('click', e => {
            if (e.target === overlay) close();
        });

        // Global hotkey
        document.addEventListener('keydown', e => {
            const isCmdK = (e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K');
            if (isCmdK) {
                e.preventDefault();
                visible ? close() : open();
            }
        });

        render();
    })();

    document.addEventListener('DOMContentLoaded', function () {
        const dmToggle = document.getElementById('dark-mode-toggle');
        const dmIcon  = document.getElementById('dark-mode-icon');
        const dmLabel = document.getElementById('dark-mode-label');

        function applyTheme(isDark) {
            if (isDark) {
                document.documentElement.classList.add('dark');
                dmIcon.className  = 'fas fa-sun sidebar-nav-icon';
                if (dmLabel) dmLabel.textContent = 'Light Mode';
            } else {
                document.documentElement.classList.remove('dark');
                dmIcon.className  = 'fas fa-moon sidebar-nav-icon';
                if (dmLabel) dmLabel.textContent = 'Dark Mode';
            }
        }

        // Apply on load
        applyTheme(document.documentElement.classList.contains('dark'));
        // Exposed so the profile Appearance panel can re-sync the
        // sidebar button after changing the theme pref (issue #155).
        window.__nxApplyThemeUi = applyTheme;

        if (dmToggle) {
            dmToggle.addEventListener('click', () => {
                const nowDark = !document.documentElement.classList.contains('dark');
                if (window.nxSetUiPref) window.nxSetUiPref('theme', nowDark ? 'dark' : 'light');
                else localStorage.setItem('nexora-theme', nowDark ? 'dark' : 'light');
                applyTheme(nowDark);
            });
        }

        const sidebar = document.getElementById('nexora-sidebar');
        const pinToggle = document.getElementById('sidebar-pin-toggle');
        const pinIcon = document.getElementById('sidebar-pin-icon');
        const pinLabel = document.getElementById('sidebar-pin-label');

        function applyPinned(isPinned) {
            document.documentElement.classList.toggle('sidebar-pinned', isPinned);
            if (sidebar) sidebar.classList.toggle('pinned', isPinned);
            if (pinIcon) pinIcon.className = isPinned ? 'fas fa-thumbtack sidebar-nav-icon sidebar-pin-active' : 'fas fa-thumbtack sidebar-nav-icon';
            if (pinLabel) pinLabel.textContent = isPinned ? window.NX_HEADER.i18n.unpinSidebar : window.NX_HEADER.i18n.keepSidebarOpen;
        }

        applyPinned(document.documentElement.classList.contains('sidebar-pinned'));
        // Exposed so the appearance page's pin switch can re-sync the
        // sidebar button + aside classes after changing the pref.
        window.__nxApplyPinnedUi = applyPinned;

        if (pinToggle) {
            pinToggle.addEventListener('click', () => {
                const nowPinned = !document.documentElement.classList.contains('sidebar-pinned');
                if (window.nxSetUiPref) window.nxSetUiPref('sidebar', nowPinned ? 'pinned' : 'auto');
                else localStorage.setItem('nexora-sidebar-pinned', nowPinned ? 'true' : 'false');
                applyPinned(nowPinned);
            });
        }

        // ---- Fireflies background option (Appearance > Background) ----
        // #fireflyField lives in _header.html, present on every page.
        // Dots are real DOM nodes (each with its own randomized position/
        // size/timing) rather than a CSS pattern, so they're spawned/torn
        // down here rather than through the data-bg attribute selector
        // Aurora/Grid use directly.
        (function () {
            const COUNT = 16;
            const rand = (min, max) => Math.random() * (max - min) + min;
            function spawn(field) {
                for (let i = 0; i < COUNT; i++) {
                    const dot = document.createElement('span');
                    dot.className = 'firefly';
                    dot.style.setProperty('--ff-left', rand(0, 100).toFixed(1) + '%');
                    dot.style.setProperty('--ff-top', rand(0, 100).toFixed(1) + '%');
                    dot.style.setProperty('--ff-size', rand(3, 7).toFixed(1) + 'px');
                    dot.style.setProperty('--ff-dx', rand(-40, 40).toFixed(0) + 'px');
                    dot.style.setProperty('--ff-dy', rand(-40, 40).toFixed(0) + 'px');
                    dot.style.setProperty('--ff-glow-dur', rand(3, 6).toFixed(1) + 's');
                    dot.style.setProperty('--ff-drift-dur', rand(7, 13).toFixed(1) + 's');
                    dot.style.setProperty('--ff-delay', rand(0, 8).toFixed(1) + 's');
                    dot.style.setProperty('--ff-peak', rand(0.55, 0.9).toFixed(2));
                    field.appendChild(dot);
                }
            }
            function syncFireflies(bg) {
                const field = document.getElementById('fireflyField');
                if (!field) return;
                const wantFireflies = bg === 'fireflies' &&
                    !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                if (wantFireflies && !field.childElementCount) spawn(field);
                else if (!wantFireflies && field.childElementCount) field.innerHTML = '';
            }
            window.__nxSyncFireflies = syncFireflies;
            syncFireflies(document.documentElement.getAttribute('data-bg'));
        })();
    });

    /* ---- Responsive table: auto-apply column labels so rows render as cards on mobile ---- */
    (function() {
        function headerTextFor(th) {
            // Prefer visible text, ignore icon-only headers like <i class="fas fa-flag"></i>
            const t = (th.innerText || th.textContent || '').trim().replace(/\s+/g, ' ');
            // If the header contains only an <i> icon and no text, the title attribute is a decent fallback
            if (!t) {
                const iconWithTitle = th.querySelector('[title]');
                return iconWithTitle ? iconWithTitle.getAttribute('title') : '';
            }
            return t;
        }

        function applyLabels(table) {
            const headers = Array.from(table.querySelectorAll('thead th')).map(headerTextFor);
            if (!headers.length) return;
            table.classList.add('responsive-card-table');
            table.querySelectorAll('tbody tr').forEach(tr => {
                const cells = tr.querySelectorAll(':scope > td');
                // Skip special rows (spinner/no-results/details) — they use colspan
                if (cells.length !== headers.length) return;
                cells.forEach((td, i) => {
                    if (!td.hasAttribute('data-label')) {
                        td.setAttribute('data-label', headers[i] || '');
                    }
                });
            });
        }

        function scan(root) {
            (root.querySelectorAll ? root.querySelectorAll('table') : []).forEach(applyLabels);
        }

        document.addEventListener('DOMContentLoaded', function () {
            scan(document);

            // Re-apply whenever tbody content changes (AJAX table renders)
            const observer = new MutationObserver((mutations) => {
                const seen = new Set();
                for (const m of mutations) {
                    let node = m.target;
                    while (node && node !== document) {
                        if (node.tagName === 'TABLE' && !seen.has(node)) {
                            seen.add(node);
                            applyLabels(node);
                            break;
                        }
                        node = node.parentNode;
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        });
    })();

    /* ---- Switch user (dev-only) ---- */
    (function() {
        const btn = document.getElementById('switchUserBtn');
        const overlay = document.getElementById('switchUserOverlay');
        const input = document.getElementById('switchUserInput');
        const list = document.getElementById('switchUserList');
        if (!btn || !overlay || !input || !list) return;
        const API_PREFIX = window.API_PREFIX;

        let usernames = [];

        function render(filter) {
            const q = (filter || '').trim().toLowerCase();
            const filtered = q ? usernames.filter(u => u.toLowerCase().includes(q)) : usernames;
            list.innerHTML = '';
            if (!filtered.length) {
                const empty = document.createElement('li');
                empty.className = 'cmdk-empty';
                empty.textContent = window.NX_HEADER.i18n.noUsers;
                list.appendChild(empty);
                return;
            }
            filtered.forEach(u => {
                const li = document.createElement('li');
                li.className = 'cmdk-item';
                li.setAttribute('role', 'option');
                li.textContent = u;
                li.addEventListener('click', () => {
                    window.location.href = API_PREFIX + 'dev/login/' + encodeURIComponent(u);
                });
                list.appendChild(li);
            });
        }

        async function open() {
            overlay.hidden = false;
            input.value = '';
            setTimeout(() => input.focus(), 10);
            if (!usernames.length) {
                const r = await fetch(API_PREFIX + 'dev/users', { credentials: 'same-origin' });
                usernames = r.ok ? await r.json() : [];
            }
            render('');
        }
        function close() {
            overlay.hidden = true;
            input.blur();
        }

        btn.addEventListener('click', open);
        input.addEventListener('input', e => render(e.target.value));
        input.addEventListener('keydown', e => {
            if (e.key === 'Escape') { e.preventDefault(); close(); }
            else if (e.key === 'Enter') {
                const first = list.querySelector('.cmdk-item');
                if (first) first.click();
            }
        });
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    })();

    /* ---- Keyboard shortcuts overlay (#173) ---- */
    (function() {
        const btn = document.getElementById('shortcutsOverlayBtn');
        const overlay = document.getElementById('shortcutsOverlay');
        if (!overlay) return;

        function isEditableTarget(el) {
            if (!el) return false;
            const tag = el.tagName;
            return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
        }

        function open() { overlay.hidden = false; }
        function close() { overlay.hidden = true; }

        if (btn) btn.addEventListener('click', open);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

        document.addEventListener('keydown', e => {
            if (!overlay.hidden && e.key === 'Escape') {
                e.preventDefault();
                close();
            } else if (overlay.hidden && e.key === '?' && !isEditableTarget(e.target)) {
                e.preventDefault();
                open();
            }
        });
    })();

    /* ---- Mobile sidebar drawer toggle ---- */
    document.addEventListener('DOMContentLoaded', function () {
        const toggle   = document.getElementById('sidebar-toggle');
        const sidebar  = document.getElementById('nexora-sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (!toggle || !sidebar || !backdrop) return;

        function openSidebar() {
            sidebar.classList.add('open');
            backdrop.classList.add('open');
            toggle.querySelector('i').className = 'fas fa-times';
        }
        function closeSidebar() {
            sidebar.classList.remove('open');
            backdrop.classList.remove('open');
            toggle.querySelector('i').className = 'fas fa-bars';
        }

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            if (sidebar.classList.contains('open')) closeSidebar();
            else openSidebar();
        });
        backdrop.addEventListener('click', closeSidebar);

        // Close when a nav link is tapped (keeps drawer UX snappy)
        sidebar.querySelectorAll('a.sidebar-nav-item').forEach(link => {
            link.addEventListener('click', () => {
                if (window.matchMedia('(max-width: 768px)').matches) closeSidebar();
            });
        });

        // Auto-close when resizing back to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth > 768) closeSidebar();
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const group    = document.getElementById('generaliNavGroup');
        const header   = document.getElementById('generaliNavHeader');
        const subitems = group && group.querySelector('.sidebar-nav-subitems');
        if (!group || !header || !subitems) return;

        function setSubitemsHeight() {
            // Temporarily make it visible to measure its full height
            subitems.style.maxHeight = 'none';
            const h = subitems.scrollHeight;
            subitems.style.maxHeight = '';
            group.style.setProperty('--generali-subitems-height', h + 'px');
        }

        setSubitemsHeight();

        // auto-open when on a generali page, otherwise restore saved state
        const isActive = group.dataset.active === 'true';
        const savedOpen = localStorage.getItem('nexora-generali-nav') === 'true';
        if (isActive || savedOpen) group.classList.add('generali-open');

        header.addEventListener('click', () => {
            const nowOpen = group.classList.toggle('generali-open');
            localStorage.setItem('nexora-generali-nav', nowOpen ? 'true' : 'false');
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const group    = document.getElementById('adminNavGroup');
        const header   = document.getElementById('adminNavHeader');
        const subitems = group && group.querySelector('.sidebar-nav-subitems');
        if (!group || !header || !subitems) return;

        function setSubitemsHeight() {
            subitems.style.maxHeight = 'none';
            const h = subitems.scrollHeight;
            subitems.style.maxHeight = '';
            group.style.setProperty('--admin-subitems-height', h + 'px');
        }

        setSubitemsHeight();

        const isActive = group.dataset.active === 'true';
        const savedOpen = localStorage.getItem('nexora-admin-nav') === 'true';
        if (isActive || savedOpen) group.classList.add('admin-open');

        header.addEventListener('click', () => {
            const nowOpen = group.classList.toggle('admin-open');
            localStorage.setItem('nexora-admin-nav', nowOpen ? 'true' : 'false');
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const group    = document.getElementById('devNavGroup');
        const header   = document.getElementById('devNavHeader');
        const subitems = group && group.querySelector('.sidebar-nav-subitems');
        if (!group || !header || !subitems) return;

        function setSubitemsHeight() {
            subitems.style.maxHeight = 'none';
            const h = subitems.scrollHeight;
            subitems.style.maxHeight = '';
            group.style.setProperty('--dev-subitems-height', h + 'px');
        }

        setSubitemsHeight();

        const isActive = group.dataset.active === 'true';
        const savedOpen = localStorage.getItem('nexora-dev-nav') === 'true';
        if (isActive || savedOpen) group.classList.add('dev-open');

        header.addEventListener('click', () => {
            const nowOpen = group.classList.toggle('dev-open');
            localStorage.setItem('nexora-dev-nav', nowOpen ? 'true' : 'false');
        });
    });

// Admin tenants overview (#256): the search box filters tenant cards, and the
// individual entries inside the two "not in a tenant" cards. Same data-search
// convention as the other admin pages -- lowercase haystack on the element,
// substring match, no ranking.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const input = document.getElementById('tenantSearchInput');
        if (!input) return;

        const cards = document.querySelectorAll('.tenant-card[data-search]');
        const orphans = document.querySelectorAll('.tenant-orphan[data-search]');

        function applyFilter() {
            const q = input.value.trim().toLowerCase();
            cards.forEach(function (el) {
                el.hidden = Boolean(q) && !el.dataset.search.includes(q);
            });
            // Inside an orphan card, narrow to the matching entries; the card
            // itself stays if any entry (or its own heading text) matches.
            orphans.forEach(function (el) {
                el.hidden = Boolean(q) && !el.dataset.search.includes(q);
                if (!el.hidden) el.closest('.tenant-card').hidden = false;
            });
        }

        input.addEventListener('input', applyFilter);
    });
})();

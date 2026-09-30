/* Sydoc BPS (#415, #427): the drill-down's pure logic -- window.BpsView.

   No DOM here: bps.js keeps the state and renders; these functions turn the
   summary rows into one zoom level, lay a level out as a squarified treemap,
   compare a group with the previous period and group a leaf's bookings per
   day. Node harness tests: tests/unit/test_bps_view_js.py. */
(function () {
    'use strict';

    // Drill-down dimension -> field of a summary row.
    const FIELD = { Aufgabe: 'task', Kunde: 'customer', Benutzer: 'person' };
    const round4 = n => Math.round(n * 10000) / 10000;

    /* Squarified treemap (Bruls, Huizing, van Wijk 2000). `items` are
       [{h}] sorted by h descending; the result is [{i, x, y, w, h}] in item
       order, tiling W x H exactly. The caller applies the gap when drawing. */
    function squarify(items, W, H) {
        const total = items.reduce((a, it) => a + (it.h > 0 ? it.h : 0), 0);
        if (!total || W <= 0 || H <= 0) return [];
        const scale = (W * H) / total;
        const rest = items.map((it, i) => ({ i, a: Math.max(0, it.h) * scale })).filter(r => r.a > 0);
        const rects = [];
        let x = 0, y = 0, w = W, h = H;
        let row = [];
        const worst = (rw, side) => {
            if (!rw.length) return Infinity;
            let s = 0, mx = 0, mn = Infinity;
            rw.forEach(r => { s += r.a; if (r.a > mx) mx = r.a; if (r.a < mn) mn = r.a; });
            return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
        };
        const place = rw => {
            const s = rw.reduce((a, r) => a + r.a, 0);
            if (w >= h) {
                const cw = s / h;
                let cy = y;
                rw.forEach(r => { const rh = r.a / cw; rects.push({ i: r.i, x, y: cy, w: cw, h: rh }); cy += rh; });
                x += cw; w -= cw;
            } else {
                const rh = s / w;
                let cx = x;
                rw.forEach(r => { const rw2 = r.a / rh; rects.push({ i: r.i, x: cx, y, w: rw2, h: rh }); cx += rw2; });
                y += rh; h -= rh;
            }
        };
        while (rest.length) {
            const side = Math.min(w, h);
            const c = rest[0];
            if (!row.length || worst(row.concat([c]), side) <= worst(row, side)) {
                row.push(c);
                rest.shift();
            } else {
                place(row);
                row = [];
            }
        }
        if (row.length) place(row);
        return rects.sort((a, b) => a.i - b.i);
    }

    // A value against the previous period: 'new' | 'flat' | 'up' | 'down'.
    function delta(value, prev) {
        const v = Number(value) || 0;
        const p = Number(prev) || 0;
        const diff = round4(v - p);
        if (p === 0) return { dir: v > 0 ? 'new' : 'flat', ratio: null, diff };
        const ratio = round4((v - p) / p);
        return { dir: diff === 0 ? 'flat' : diff > 0 ? 'up' : 'down', ratio, diff };
    }

    // The colour family of a group: its table marker and treemap tile.
    function category(g) {
        if (g.hours > 0 && g.absence / g.hours > 0.5) return 'absence';
        if (g.hours > 0 && g.billable >= g.hours * 0.999) return 'billable';
        if (g.billable > 0) return 'partly';
        return 'service';
    }

    function onPath(order, path) {
        const dims = order.slice(0, path.length);
        return r => dims.every((d, i) => r[FIELD[d]] === path[i]);
    }

    /* One zoom level: the rows under `path` (keys along `order`), grouped by
       the next dimension and sorted by hours. `prev` is the same group's hours
       in the previous period's rows. */
    function level(rows, prevRows, order, path) {
        const dim = order[path.length];
        const field = FIELD[dim];
        const match = onPath(order, path);
        const groups = new Map();
        rows.filter(match).forEach(r => {
            const key = r[field];
            let g = groups.get(key);
            if (!g) {
                g = { key, hours: 0, billable: 0, service: 0, absence: 0, count: 0, prev: 0 };
                groups.set(key, g);
            }
            g.hours += r.hours;
            g.count += r.count;
            g[r.category] += r.hours;
        });
        (prevRows || []).filter(match).forEach(r => {
            const g = groups.get(r[field]);
            if (g) g.prev += r.hours;
        });
        const out = Array.from(groups.values()).filter(g => g.hours > 0);
        out.forEach(g => {
            ['hours', 'billable', 'service', 'absence', 'prev'].forEach(k => { g[k] = round4(g[k]); });
            g.cat = category(g);
        });
        return out.sort((a, b) => b.hours - a.hours || String(a.key).localeCompare(String(b.key)));
    }

    // Hours of the previous period under `path`, filtered like the level.
    function prevTotal(prevRows, order, path) {
        return round4((prevRows || []).filter(onPath(order, path)).reduce((a, r) => a + r.hours, 0));
    }

    // A leaf's bookings grouped per day, in date order.
    function byDay(entries) {
        const days = new Map();
        entries.forEach(e => {
            let d = days.get(e.date);
            if (!d) {
                d = { date: e.date, hours: 0, count: 0, entries: [] };
                days.set(e.date, d);
            }
            d.hours = round4(d.hours + (Number(e.hours) || 0));
            d.count += 1;
            d.entries.push(e);
        });
        return Array.from(days.values()).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    }

    window.BpsView = { FIELD, squarify, delta, category, level, prevTotal, byDay };
})();

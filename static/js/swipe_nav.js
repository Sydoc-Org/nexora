/* Swipe between the tab bar's views on a phone (#368).

   The bar is already the answer to "which views, in what order, for this
   user": its slots are permission-filtered <a> links built from the sidebar's
   own nav_items, and a slot somebody may not open is never rendered. So this
   reads the bar rather than keeping a second list of pages that could drift
   out of step with it -- and for a user scoped to one tenant, whose bar
   carries that tenant's pages instead of the global ones, the right thing
   happens with no extra code.

   Why a separate file rather than another block in header.js: header.js is
   688 lines of unrelated concerns, and this has one. It also keeps the swipe
   out of the way of the owner's own work-in-progress handler in that file.

   Deliberately NOT handled here:

   - Swipes that start within EDGE pixels of either side. That is the
     platform's back/forward gesture, and in an installed app it is the only
     way back out of a page -- there is no browser chrome to press. Taking it
     would trap people, and Safari ignores attempts to suppress it anyway.
     Edges belong to the system, the middle belongs to the views.

   - Anything that would need `preventDefault`, which is why both listeners
     stay `{ passive: true }` and scrolling keeps its smoothness. */
(function () {
    /* Same gate as the CSS, for the same reason: a narrow desktop window is
       not a phone, and a mouse cannot make these events anyway. */
    if (!window.matchMedia("(max-width: 768px) and (pointer: coarse)").matches) return;

    /* 60px of travel. Lower reads a sloppy tap as a swipe -- a thumb pivots at
       the joint, so "straight down" always drifts sideways by some amount. */
    const MIN_DISTANCE = 60;
    const EDGE = 30;

    /* Only the <a> slots are destinations. The last slot is "More", a <button>
       that opens the sheet, so it is not a page to navigate to. */
    function slots() {
        return Array.from(document.querySelectorAll(".nx-tabbar a.nx-tabbar-item"));
    }

    function neighbourHref(step) {
        const items = slots();
        if (items.length < 2) return null;
        let i = items.findIndex((a) => a.classList.contains("nx-tabbar-item--active"));
        if (i === -1) i = items.findIndex((a) => a.getAttribute("aria-current") === "page");
        /* No active slot means this page is not one of the bar's views (the
           profile pages, an admin sub-page). Nothing to step from. */
        if (i === -1) return null;
        /* No wrap at the ends: arriving back at Dashboard from Workitems reads
           as having gone the wrong way, and there is no visual cue that you
           looped. Running out is quieter and matches a tab bar. */
        const target = items[i + step];
        return target ? target.getAttribute("href") : null;
    }

    /* An ancestor that can be dragged sideways gets the gesture instead.
       Nothing on a phone should scroll sideways any more, so this is a safety
       net rather than the load-bearing check -- but a future strip that forgets
       the rule then degrades to "the strip scrolls" instead of "the page
       navigates while you are trying to scroll a strip". */
    function startedInSideScroller(el) {
        let node = el;
        while (node && node !== document.body) {
            if (node.scrollWidth > node.clientWidth + 1) {
                const ox = getComputedStyle(node).overflowX;
                if (ox === "auto" || ox === "scroll") return true;
            }
            node = node.parentElement;
        }
        return false;
    }

    let startX = 0;
    let startY = 0;
    let ignore = true;

    document.addEventListener(
        "touchstart",
        (e) => {
            const t = e.changedTouches[0];
            startX = t.clientX;
            startY = t.clientY;
            const w = document.documentElement.clientWidth;
            /* Everything that can only be known at touchstart is decided here
               and carried, because touchend sees neither the start point nor
               what was under the finger. */
            ignore =
                t.clientX <= EDGE ||
                t.clientX >= w - EDGE ||
                startedInSideScroller(e.target);
        },
        { passive: true },
    );

    document.addEventListener(
        "touchend",
        (e) => {
            if (ignore) return;
            /* Mid-sentence: the keyboard is up and the bar is hidden, so a
               sideways thumb-slip must not change the page under the field. */
            if (document.documentElement.classList.contains("nx-typing")) return;
            /* The sheet is open over the page; a swipe belongs to it, not to
               the navigation behind it. */
            const sheet = document.getElementById("nexora-sidebar");
            if (sheet && sheet.classList.contains("open")) return;

            const t = e.changedTouches[0];
            const dx = t.clientX - startX;
            const dy = t.clientY - startY;

            if (Math.abs(dy) > Math.abs(dx)) return;
            if (Math.abs(dx) < MIN_DISTANCE) return;

            /* Dragging left pulls the next view in, the way a page turns. */
            const href = neighbourHref(dx < 0 ? 1 : -1);
            if (href) window.location.href = href;
        },
        { passive: true },
    );
})();

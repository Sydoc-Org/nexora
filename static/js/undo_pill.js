/* "Saved · Undo" pill after a phone quick entry (#354).
 *
 * Shared by Generali Reporting (one-tap KPI report) and Generali Base
 * Services (quick hours entry). The markup lives in each page -- a
 * `.nx-undo` element with `.nx-undo__text`, `.nx-undo__btn` and
 * `.nx-undo__time` children, rendered `hidden` -- and the look in
 * nexora-ui.css; this file only owns the timing:
 *
 *   - fades out on its own after SHOW_MS, the line along its bottom
 *     counting down;
 *   - goes at once on a tap anywhere else or a finger scroll. touchmove,
 *     not scroll: the list reload after a save can scroll the page by
 *     itself, and that must not close the pill before anyone saw it;
 *   - after Undo, the outcome stays up for AFTER_MS, then fades the same way.
 *
 * The server keeps its own, longer window (UNDO_WINDOW_SECONDS, 10 minutes);
 * the pill is only the shortcut, so it can go quickly.
 */
(function () {
    'use strict';

    const SHOW_MS = 6000;
    const AFTER_MS = 2500;
    const FADE_MS = 220;

    let current = null;  // the bar on screen
    let timer = null;

    function onOutside(e) {
        if (current && !current.contains(e.target)) hide();
    }

    function disarm() {
        clearTimeout(timer);
        document.removeEventListener('pointerdown', onOutside, true);
        document.removeEventListener('touchmove', hide, true);
    }

    function hide() {
        disarm();
        const bar = current;
        current = null;
        if (!bar || bar.hidden) return;
        bar.classList.add('is-leaving');
        setTimeout(() => {
            // A newer show() on the same bar wins over this fade.
            if (current === bar) return;
            bar.hidden = true;
            bar.classList.remove('is-leaving');
        }, FADE_MS);
    }

    function startClock(bar, ms) {
        clearTimeout(timer);
        const time = bar.querySelector('.nx-undo__time');
        if (time) {
            // Restart the countdown line: drop the animation, reflow, put it back.
            time.style.animation = 'none';
            void time.offsetWidth;
            time.style.animation = '';
            bar.style.setProperty('--nx-undo-ms', `${ms}ms`);
        }
        timer = setTimeout(hide, ms);
    }

    /**
     * Show the pill.
     *   bar      the page's `.nx-undo` element
     *   text     what was saved, e.g. "Saved · 2 h · PPR"
     *   title    optional longer text for the tooltip
     *   undo     optional async () => message. Resolve with the text to show
     *            ("Undone."), throw an Error whose message is shown instead.
     *            Without it the pill has no Undo button.
     *   failText fallback message when `undo` throws without one
     */
    function show(bar, { text, title = '', undo = null, failText = '' }) {
        if (!bar) return;
        disarm();
        const textEl = bar.querySelector('.nx-undo__text');
        const btn = bar.querySelector('.nx-undo__btn');
        textEl.textContent = text;
        textEl.title = title;
        btn.hidden = !undo;
        btn.disabled = false;
        btn.onclick = async () => {
            btn.disabled = true;
            clearTimeout(timer);
            try {
                textEl.textContent = await undo();
            } catch (e) {
                textEl.textContent = (e && e.message) || failText;
            }
            btn.hidden = true;
            startClock(bar, AFTER_MS);
        };
        bar.classList.remove('is-leaving');
        bar.hidden = false;
        current = bar;
        startClock(bar, SHOW_MS);
        // Armed on the next tick, so the tap that saved the entry does not
        // count as a tap outside and close the pill straight away.
        setTimeout(() => {
            if (current !== bar) return;
            document.addEventListener('pointerdown', onOutside, true);
            document.addEventListener('touchmove', hide, { capture: true, passive: true, once: true });
        }, 0);
    }

    window.NX = window.NX || {};
    window.NX.undoPill = { show, hide };
})();

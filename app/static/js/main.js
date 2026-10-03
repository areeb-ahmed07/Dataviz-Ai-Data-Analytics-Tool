/**
 * DataViz Pro — Global JavaScript (Phase 15)
 *
 * DOM ready marker, global utility functions.
 */

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        document.documentElement.classList.add('js-ready');
    });

    // ── Global Utility: Format Numbers ────────────────────────────
    window.formatNumber = function (num) {
        if (num == null) return '0';
        if (typeof num !== 'number') num = parseFloat(num);
        if (isNaN(num)) return '0';
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toLocaleString();
    };

    // ── Global Utility: Debounce ─────────────────────────────────
    window.debounce = function (fn, delay) {
        var timer;
        return function () {
            var args = arguments;
            var ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(ctx, args);
            }, delay);
        };
    };

    // ── Global Utility: Throttle ─────────────────────────────────
    window.throttle = function (fn, limit) {
        var last = 0;
        return function () {
            var now = Date.now();
            if (now - last >= limit) {
                last = now;
                fn.apply(this, arguments);
            }
        };
    };

})();

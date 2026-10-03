/* Resolve the saved account preference before the first paint. */
(function () {
    'use strict';
    const root = document.documentElement;
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    function applyTheme() {
        let stored = null;
        try { stored = window.localStorage && window.localStorage.getItem('dv-theme-preference'); } catch (_) { /* storage may be unavailable */ }
        const preference = stored || root.dataset.themePreference;
        const dark = preference === 'dark' || (preference === 'system' && systemTheme.matches);
        root.dataset.theme = dark ? 'dark' : 'light';
        root.style.colorScheme = dark ? 'dark' : 'light';
        const themeColor = document.querySelector('meta[name="theme-color"]');
        if (themeColor) themeColor.content = dark ? '#101c28' : '#0f766e';
        const toggle = document.querySelector('#themeToggle');
        if (toggle) {
            toggle.setAttribute('aria-checked', String(dark));
            toggle.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
        }
    }
    window.DataVizTheme = {setPreference(preference) {
        root.dataset.themePreference = preference;
        applyTheme();
    }};
    applyTheme();
    systemTheme.addEventListener('change', applyTheme);
})();

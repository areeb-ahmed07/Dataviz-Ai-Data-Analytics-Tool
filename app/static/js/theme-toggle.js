(function () {
    'use strict';
    const button = document.getElementById('themeToggle');
    if (!button) return;
    const root = document.documentElement;
    const status = document.getElementById('themeStatus') || {textContent: ''};
    const remember = value => { try { if (window.localStorage) window.localStorage.setItem('dv-theme-preference', value); } catch (_) {} };
    window.DataVizTheme.setPreference(root.dataset.themePreference);
    button.addEventListener('click', async function () {
        if (button.disabled) return;
        const previous = root.dataset.themePreference;
        const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        button.disabled = true;
        remember(next);
        window.DataVizTheme.setPreference(next);
        status.textContent = 'Saving appearance…';
        try {
            if (!button.dataset.url) {
                status.textContent = next === 'dark' ? 'Dark mode enabled.' : 'Light mode enabled.';
                return;
            }
            const response = await fetch(button.dataset.url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                body: JSON.stringify({theme: next}),
            });
            if (!response.ok || response.redirected) throw new Error('Theme was not saved');
            const result = await response.json();
            if (result.theme !== next) throw new Error('Theme was not saved');
            document.querySelectorAll('select[name="theme"], input[name="theme"]').forEach(field => {
                field.value = next;
            });
            status.textContent = next === 'dark' ? 'Dark mode enabled.' : 'Light mode enabled.';
        } catch (error) {
            remember(previous);
            window.DataVizTheme.setPreference(previous);
            status.textContent = 'Could not save appearance. Please try again.';
            if (window.showToast) window.showToast(status.textContent, 'error');
        } finally {
            button.disabled = false;
        }
    });
})();

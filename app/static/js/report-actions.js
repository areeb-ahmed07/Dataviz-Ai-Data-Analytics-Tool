document.addEventListener('submit', event => {
    const form = event.target.closest('.report-delete-form');
    if (!form) return;
    if (!window.confirm(`Delete “${form.dataset.filename}”? This permanently removes the report file.`)) {
        event.preventDefault();
        return;
    }
    form.querySelector('button[type="submit"]').disabled = true;
});

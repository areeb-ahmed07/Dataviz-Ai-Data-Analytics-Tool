/**
 * DataViz Pro - Reports Module JavaScript
 * Handles report preview, format selection, and generation.
 */
const ReportBuilder = {
    datasetId: null,
    selectedFormat: 'pdf',
    previewData: null,

    init(datasetId) {
        this.datasetId = datasetId;
        this.loadPreview();
    },

    selectFormat(format) {
        this.selectedFormat = format;
        document.querySelectorAll('.rpt-format-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.format === format);
        });
    },

    async loadPreview() {
        const previewBody = document.getElementById('rptPreviewBody');
        const sectionsGrid = document.getElementById('rptSectionsGrid');
        if (!previewBody || !sectionsGrid) return;

        previewBody.innerHTML = '<div class="rpt-loading"><div class="rpt-spinner"></div><span>Loading analysis data...</span></div>';
        sectionsGrid.innerHTML = '<div class="rpt-loading"><div class="rpt-spinner"></div><span>Loading...</span></div>';

        try {
            const resp = await fetch(`/reports/api/${this.datasetId}/preview`);
            if (!resp.ok) throw new Error('Failed to load preview');
            const data = await resp.json();
            this.previewData = data;
            this.renderPreview(data);
            this.renderSections(data);
            this.renderModels(data);
        } catch (err) {
            previewBody.innerHTML = `<div class="rpt-loading" style="color:#EF4444;"><span>Error loading preview: ${err.message}</span></div>`;
            sectionsGrid.innerHTML = '';
        }
    },

    renderPreview(data) {
        const body = document.getElementById('rptPreviewBody');
        const qs = data.quality_score || 100;
        const qsClass = qs >= 80 ? 'good' : (qs >= 50 ? 'warn' : 'poor');

        body.innerHTML = `
            <div class="rpt-kpi-grid">
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.row_count.toLocaleString()}</div><div class="rpt-kpi-label">Rows</div></div>
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.col_count}</div><div class="rpt-kpi-label">Columns</div></div>
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.numeric_columns}</div><div class="rpt-kpi-label">Numeric</div></div>
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.categorical_columns}</div><div class="rpt-kpi-label">Categorical</div></div>
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.ml_model_count}</div><div class="rpt-kpi-label">ML Models</div></div>
                <div class="rpt-kpi-item"><div class="rpt-kpi-value">${data.duplicate_rows}</div><div class="rpt-kpi-label">Duplicates</div></div>
            </div>
            <div style="margin-top:1.25rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
                    <span style="font-size:0.85rem;font-weight:600;color:#0F172A;">Data Quality Score</span>
                    <span style="font-size:0.85rem;font-weight:700;color:#4F46E5;">${qs.toFixed(1)}/100</span>
                </div>
                <div class="rpt-quality-bar">
                    <div class="rpt-quality-fill ${qsClass}" style="width:${qs}%"></div>
                </div>
                <p style="font-size:0.8rem;color:#64748B;margin-top:0.5rem;">Missing data: ${data.missing_pct.toFixed(2)}%</p>
            </div>
        `;
    },

    renderSections(data) {
        const grid = document.getElementById('rptSectionsGrid');
        const sections = data.sections || [];
        grid.innerHTML = sections.map(s => `
            <div class="rpt-section-item ${s.available ? 'available' : 'unavailable'}">
                <div class="rpt-section-check">
                    ${s.available ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>' : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>'}
                </div>
                <div class="rpt-section-info">
                    <h4>${s.title}</h4>
                    <p>${s.description}</p>
                </div>
            </div>
        `).join('');
    },

    renderModels(data) {
        const card = document.getElementById('rptModelsCard');
        const body = document.getElementById('rptModelsBody');
        const models = data.ml_models || [];

        if (models.length === 0) {
            card.style.display = 'none';
            return;
        }

        card.style.display = 'block';
        body.innerHTML = models.map(m => `
            <div class="rpt-model-item">
                <div class="rpt-model-name">${m.name}</div>
                <div class="rpt-model-meta">${m.algorithm} | ${m.problem_type}</div>
            </div>
        `).join('');
    },

    async generate() {
        const btn = document.getElementById('rptGenerateBtn');
        const overlay = document.getElementById('rptOverlay');
        const msg = document.getElementById('rptOverlayMsg');

        const formatLabels = {
            pdf: 'PDF', html: 'HTML', pptx: 'PowerPoint', excel: 'Excel', word: 'Word', executive: 'Executive PDF'
        };
        msg.textContent = `Running analysis and building ${formatLabels[this.selectedFormat] || this.selectedFormat} report...`;
        overlay.style.display = 'flex';
        btn.disabled = true;

        try {
            const resp = await fetch(`/reports/api/${this.datasetId}/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.REPORT_CSRF_TOKEN || '' },
                body: JSON.stringify({ format: this.selectedFormat }),
            });

            const result = await resp.json();

            if (!resp.ok || result.error) {
                throw new Error(result.error || 'Generation failed');
            }

            // Trigger download via the download route
            const downloadUrl = `/reports/${this.datasetId}/download?format=${encodeURIComponent(this.selectedFormat)}&filename=${encodeURIComponent(result.filename)}`;
            window.location.href = downloadUrl;

            // Hide overlay after a short delay
            setTimeout(() => { overlay.style.display = 'none'; }, 2000);
        } catch (err) {
            alert('Report generation failed: ' + err.message);
            overlay.style.display = 'none';
        } finally {
            btn.disabled = false;
        }
    }
};

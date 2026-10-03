/**
 * DataViz Pro — Analysis Workspace JavaScript
 *
 * Handles dynamic chart loading, API calls, and Plotly.js visualizations.
 * All analysis data is fetched via Flask API endpoints.
 */

const AnalysisWorkspace = (function () {
    'use strict';

    const API_BASE = '/analysis/api';

    // ── Helper: Show/Hide states ────────────────────────────────

    function showLoading() {
        const el = document.getElementById('analysisLoading');
        const content = document.getElementById('analysisContent');
        const error = document.getElementById('analysisError');
        if (el) el.style.display = 'flex';
        if (content) content.style.display = 'none';
        if (error) error.style.display = 'none';
    }

    function showContent() {
        const el = document.getElementById('analysisLoading');
        const content = document.getElementById('analysisContent');
        const error = document.getElementById('analysisError');
        if (el) el.style.display = 'none';
        if (content) content.style.display = 'block';
        if (error) error.style.display = 'none';
    }

    function showError(msg) {
        const el = document.getElementById('analysisLoading');
        const content = document.getElementById('analysisContent');
        const error = document.getElementById('analysisError');
        const errorMsg = document.getElementById('analysisErrorMsg');
        if (el) el.style.display = 'none';
        if (content) content.style.display = 'none';
        if (error) error.style.display = 'block';
        if (errorMsg) errorMsg.textContent = msg || 'An error occurred while loading analysis data.';
    }

    function formatNumber(n) {
        if (n === null || n === undefined) return '—';
        if (typeof n === 'number') {
            if (Math.abs(n) >= 1000) return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
            return n.toFixed(2);
        }
        return String(n);
    }

    // ── API Fetch Helper ────────────────────────────────────────

    async function fetchJSON(url) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            return await resp.json();
        } catch (err) {
            throw err;
        }
    }

    // ── Overview ─────────────────────────────────────────────────

    async function loadOverview(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/overview`);
            renderOverview(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderOverview(data) {
        const kpis = data.kpis || {};
        setText('kpiRows', formatNumber(kpis.rows));
        setText('kpiCols', formatNumber(kpis.columns));
        setText('kpiNumeric', formatNumber(kpis.numeric_count));
        setText('kpiCategorical', formatNumber(kpis.categorical_count));
        setText('kpiMissing', formatNumber(kpis.missing_values));
        setText('kpiMissingPct', kpis.missing_pct + '%');
        setText('kpiDuplicates', formatNumber(kpis.duplicate_rows));
        setText('kpiMemory', kpis.memory_mb);

        // Schema table
        const schemaBody = document.getElementById('schemaBody');
        if (schemaBody && data.schema) {
            schemaBody.innerHTML = data.schema.map(col => {
                const dtypeClass = col.type || '';
                return `<tr>
                    <td class="td-name">${escapeHtml(col.name)}</td>
                    <td><span class="dtype-badge dtype-${dtypeClass}">${col.type}</span></td>
                    <td>${col.missing > 0 ? `<span class="missing-badge">${col.missing} (${(col.missing / (kpis.rows || 1) * 100).toFixed(1)}%)</span>` : '<span style="color:var(--muted)">0</span>'}</td>
                    <td>${col.unique}</td>
                </tr>`;
            }).join('');
        }

        // Quality summary
        const qs = data.quality_summary || {};
        const scoreWrap = document.getElementById('qualityScoreWrap');
        if (scoreWrap && qs.quality_score !== undefined) {
            scoreWrap.style.display = 'block';
            setText('qualityScoreValue', Math.round(qs.quality_score));
        }
        const qm = document.getElementById('qualityMetrics');
        if (qm) {
            const missingTotal = qs.missing_values ? Object.values(qs.missing_values).reduce((a, b) => a + b, 0) : 0;
            qm.innerHTML = `
                <div class="qm-item"><span class="qm-label">Quality Score</span><span class="qm-value">${Math.round(qs.quality_score || 0)}/100</span></div>
                <div class="qm-item"><span class="qm-label">Missing Values</span><span class="qm-value">${missingTotal.toLocaleString()}</span></div>
                <div class="qm-item"><span class="qm-label">Duplicate Rows</span><span class="qm-value">${(qs.duplicate_rows || 0).toLocaleString()}</span></div>
            `;
        }

        // Insights preview
        const ip = document.getElementById('insightsPreview');
        if (ip && data.insights && data.insights.length > 0) {
            ip.innerHTML = data.insights.slice(0, 5).map(i => renderInsightItem(i)).join('');
        } else if (ip) {
            ip.innerHTML = '<p class="text-muted">No significant insights found for this dataset.</p>';
        }
    }

    // ── Quality ───────────────────────────────────────────────────

    async function loadQuality(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/quality`);
            renderQuality(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderQuality(data) {
        setText('qualityScoreValue', Math.round(data.quality_score || 0));
        setText('qsTotalMissing', (data.total_missing || 0).toLocaleString());
        setText('qsMissingPct', data.missing_pct + '%');
        setText('qsDuplicates', (data.duplicate_rows || 0).toLocaleString());
        setText('qsTotalCells', (data.total_cells || 0).toLocaleString());

        // Missing values table
        const body = document.getElementById('missingBody');
        const noMsg = document.getElementById('noMissingMsg');
        const wrap = document.getElementById('missingTableWrap');
        if (data.missing_per_column && data.missing_per_column.length > 0) {
            wrap.style.display = 'block';
            noMsg.style.display = 'none';
            body.innerHTML = data.missing_per_column.map(item => {
                const severity = item.missing_pct > 20 ? 'high' : item.missing_pct > 5 ? 'medium' : 'low';
                return `<tr>
                    <td class="td-name">${escapeHtml(item.column)}</td>
                    <td>${item.missing_count.toLocaleString()}</td>
                    <td>${item.missing_pct}%</td>
                    <td><span class="severity-badge severity-${severity}">${severity}</span></td>
                </tr>`;
            }).join('');
        } else {
            wrap.style.display = 'none';
            noMsg.style.display = 'block';
        }

        // Consistency issues
        const cPanel = document.getElementById('consistencyPanel');
        const cDiv = document.getElementById('consistencyIssues');
        if (data.consistency_issues && data.consistency_issues.length > 0) {
            cPanel.style.display = 'block';
            cDiv.innerHTML = data.consistency_issues.map(issue =>
                `<div class="consistency-issue">${escapeHtml(issue)}</div>`
            ).join('');
        }

        // Type issues
        const tPanel = document.getElementById('typeIssuesPanel');
        const tDiv = document.getElementById('typeIssues');
        if (data.type_issues && data.type_issues.length > 0) {
            tPanel.style.display = 'block';
            tDiv.innerHTML = data.type_issues.map(item =>
                `<div class="type-issue"><strong>${escapeHtml(item.column)}</strong>: ${escapeHtml(item.issue)} — types: ${escapeHtml(item.types.join(', '))}</div>`
            ).join('');
        }
    }

    // ── Statistics ───────────────────────────────────────────────

    async function loadStatistics(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/statistics`);
            renderStatistics(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderStatistics(data) {
        // Numeric
        setText('numericBadge', `${data.numeric_columns_count} columns`);
        const nBody = document.getElementById('numericBody');
        const nMsg = document.getElementById('noNumericMsg');
        if (data.numeric && data.numeric.length > 0) {
            nBody.innerHTML = data.numeric.map(s => `<tr>
                <td class="td-name">${escapeHtml(s.column)}</td>
                <td>${formatNumber(s.count)}</td>
                <td>${formatNumber(s.mean)}</td>
                <td>${formatNumber(s.std)}</td>
                <td>${formatNumber(s.min)}</td>
                <td>${formatNumber(s.q1)}</td>
                <td>${formatNumber(s.median)}</td>
                <td>${formatNumber(s.q3)}</td>
                <td>${formatNumber(s.max)}</td>
                <td>${formatNumber(s.iqr)}</td>
                <td>${formatNumber(s.skewness)}</td>
                <td>${formatNumber(s.kurtosis)}</td>
                <td>${s.zeros_pct}%</td>
            </tr>`).join('');
        } else {
            nBody.innerHTML = '';
            nMsg.style.display = 'block';
        }

        // Categorical
        setText('categoricalBadge', `${data.categorical_columns_count} columns`);
        const cBody = document.getElementById('categoricalBody');
        const cMsg = document.getElementById('noCategoricalMsg');
        if (data.categorical && data.categorical.length > 0) {
            cBody.innerHTML = data.categorical.map(s => `<tr>
                <td class="td-name">${escapeHtml(s.column)}</td>
                <td>${formatNumber(s.count)}</td>
                <td>${s.unique}</td>
                <td>${escapeHtml(String(s.top_value || '—'))}</td>
                <td>${formatNumber(s.top_frequency)}</td>
                <td>${s.top_pct}%</td>
                <td><span class="cardinality-badge cardinality-${s.cardinality}">${s.cardinality}</span></td>
            </tr>`).join('');
        } else {
            cBody.innerHTML = '';
            cMsg.style.display = 'block';
        }

        // Datetime
        const dPanel = document.getElementById('datetimePanel');
        if (data.datetime && data.datetime.length > 0) {
            dPanel.style.display = 'block';
            setText('datetimeBadge', `${data.datetime_columns_count} columns`);
            document.getElementById('datetimeBody').innerHTML = data.datetime.map(s => `<tr>
                <td class="td-name">${escapeHtml(s.column)}</td>
                <td>${formatNumber(s.count)}</td>
                <td>${s.min}</td>
                <td>${s.max}</td>
                <td>${s.range_days.toLocaleString()}</td>
                <td>${s.missing}</td>
            </tr>`).join('');
        }
    }

    // ── Correlations ──────────────────────────────────────────────

    async function loadCorrelations(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/correlations`);
            renderCorrelations(data, datasetId);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderCorrelations(data) {
        if (!data.columns || data.columns.length < 2) {
            document.getElementById('noCorrelationMsg').style.display = 'block';
            document.getElementById('heatmapContainer').style.display = 'none';
            return;
        }

        // Plotly heatmap
        const trace = {
            z: data.matrix,
            x: data.columns,
            y: data.columns,
            type: 'heatmap',
            colorscale: 'RdBu',
            zmin: -1,
            zmax: 1,
            colorbar: { title: 'Correlation' },
        };

        const layout = {
            margin: { l: 100, r: 40, t: 30, b: 100 },
            xaxis: { tickangle: -45, side: 'bottom' },
            yaxis: { autorange: 'reversed' },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
        };

        Plotly.newPlot('heatmapContainer', [trace], layout, { responsive: true });

        // Strong correlations table
        const panel = document.getElementById('strongCorrPanel');
        const badge = document.getElementById('strongCorrBadge');
        const body = document.getElementById('strongCorrBody');
        const noMsg = document.getElementById('noStrongCorrMsg');

        if (data.strong_correlations && data.strong_correlations.length > 0) {
            panel.style.display = 'block';
            badge.textContent = `${data.strong_correlations.length} pairs`;
            noMsg.style.display = 'none';
            body.innerHTML = data.strong_correlations.map(c => `<tr>
                <td class="td-name">${escapeHtml(c.var1)}</td>
                <td class="td-name">${escapeHtml(c.var2)}</td>
                <td>${c.pearson.toFixed(4)}</td>
                <td>${c.spearman !== null ? c.spearman.toFixed(4) : '—'}</td>
                <td><span class="strength-badge strength-${c.strength}">${c.strength}</span></td>
            </tr>`).join('');
        } else {
            panel.style.display = 'block';
            noMsg.style.display = 'block';
            badge.textContent = '0 pairs';
        }
    }

    // ── Distributions ────────────────────────────────────────────

    async function initDistributions(datasetId) {
        showLoading();
        try {
            // Load column list
            const colData = await fetchJSON(`${API_BASE}/${datasetId}/columns`);
            const numCols = (colData.columns || []).filter(c => c.type === 'numeric');

            const select = document.getElementById('distColumnSelect');
            const loadBtn = document.getElementById('loadDistBtn');
            const noMsg = document.getElementById('noNumericMsg');

            if (numCols.length === 0) {
                showContent();
                noMsg.style.display = 'block';
                return;
            }

            select.innerHTML = '<option value="">— Select column —</option>' +
                numCols.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${c.dtype})</option>`).join('');

            loadBtn.disabled = false;

            loadBtn.addEventListener('click', () => {
                const col = select.value;
                if (col) loadDistribution(datasetId, col);
            });

            select.addEventListener('change', () => {
                loadBtn.disabled = !select.value;
            });

            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    async function loadDistribution(datasetId, column) {
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/distribution?column=${encodeURIComponent(column)}`);
            renderDistribution(data);
        } catch (e) {
            alert('Error loading distribution: ' + e.message);
        }
    }

    function renderDistribution(data) {
        document.getElementById('distChartsContainer').style.display = 'grid';
        document.getElementById('distStatsPanel').style.display = 'block';
        setText('histColName', `— ${escapeHtml(data.column)}`);
        setText('boxColName', `— ${escapeHtml(data.column)}`);

        // Histogram
        const histTrace = {
            x: data.histogram.bins,
            y: data.histogram.counts,
            type: 'bar',
            marker: {
                color: 'rgba(99, 102, 241, 0.7)',
                line: { color: 'rgba(99, 102, 241, 1)', width: 1 },
            },
            name: 'Frequency',
        };

        const histLayout = {
            xaxis: { title: 'Value', gridcolor: '#e5e7eb' },
            yaxis: { title: 'Frequency', gridcolor: '#e5e7eb' },
            bargap: 0.05,
            margin: { l: 60, r: 20, t: 20, b: 50 },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
        };

        Plotly.newPlot('histogramChart', [histTrace], histLayout, { responsive: true });

        // Box plot
        const boxTrace = {
            y: [data.box_plot],
            type: 'box',
            boxpoints: false,
            name: data.column,
            marker: { color: 'rgba(99, 102, 241, 0.7)' },
        };

        const boxLayout = {
            yaxis: { title: 'Value', gridcolor: '#e5e7eb' },
            margin: { l: 60, r: 20, t: 20, b: 40 },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
        };

        Plotly.newPlot('boxPlotChart', [boxTrace], boxLayout, { responsive: true });

        // Stats
        const grid = document.getElementById('distStatsGrid');
        const stats = data.stats || {};
        const bp = data.box_plot || {};
        grid.innerHTML = [
            ['Count', data.count], ['Mean', stats.mean], ['Std Dev', stats.std],
            ['Min', bp.min], ['Q1', bp.q1], ['Median', bp.median],
            ['Q3', bp.q3], ['Max', bp.max], ['IQR', bp.iqr],
            ['Skewness', stats.skewness], ['Kurtosis', stats.kurtosis],
        ].map(([label, val]) => `
            <div class="dist-stat-item">
                <span class="dist-stat-val">${formatNumber(val)}</span>
                <span class="dist-stat-lbl">${label}</span>
            </div>
        `).join('');
    }

    // ── Outliers ─────────────────────────────────────────────────

    async function loadOutliers(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/outliers`);
            renderOutliers(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderOutliers(data) {
        setText('kpiOutlierCols', data.columns_with_outliers);
        setText('kpiTotalOutliers', (data.total_outlier_values || 0).toLocaleString());

        if (!data.outlier_details || data.outlier_details.length === 0) {
            document.getElementById('noOutliersMsg').style.display = 'block';
            return;
        }

        // Box plots using Plotly
        if (data.box_plot_data && data.box_plot_data.length > 0) {
            document.getElementById('outlierBoxPanel').style.display = 'block';
            const traces = data.box_plot_data.map(item => ({
                y: [],
                type: 'box',
                name: item.column,
                q1: [item.q1], median: [item.median], q3: [item.q3],
                lowerfence: [item.lower_fence], upperfence: [item.upper_fence],
                mean: [item.mean],
                whiskerlow: [item.whisker_low], whiskerhigh: [item.whisker_high],
                boxpoints: false,
            }));

            const layout = {
                margin: { l: 80, r: 20, t: 20, b: 40 },
                yaxis: { title: 'Column' },
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                showlegend: false,
            };

            Plotly.newPlot('outlierBoxPlot', traces, layout, { responsive: true });
        }

        // Details table
        document.getElementById('outlierTablePanel').style.display = 'block';
        document.getElementById('outlierBody').innerHTML = data.outlier_details.map(item => `
            <tr>
                <td class="td-name">${escapeHtml(item.column)}</td>
                <td>${item.outlier_count.toLocaleString()}</td>
                <td>${item.outlier_pct}%</td>
                <td>${formatNumber(item.q1)}</td>
                <td>${formatNumber(item.q3)}</td>
                <td>${formatNumber(item.iqr)}</td>
                <td>${formatNumber(item.lower_fence)}</td>
                <td>${formatNumber(item.upper_fence)}</td>
                <td>${formatNumber(item.min_outlier)}</td>
                <td>${formatNumber(item.max_outlier)}</td>
            </tr>
        `).join('');
    }

    // ── Categorical ──────────────────────────────────────────────

    async function initCategorical(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/categorical`);

            const catCols = data.categorical_columns || [];
            const select = document.getElementById('catColumnSelect');
            const loadBtn = document.getElementById('loadCatBtn');
            const noMsg = document.getElementById('noCatMsg');

            if (catCols.length === 0) {
                showContent();
                noMsg.style.display = 'block';
                return;
            }

            select.innerHTML = '<option value="">— Select column —</option>' +
                catCols.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');

            loadBtn.disabled = false;

            loadBtn.addEventListener('click', () => {
                const col = select.value;
                if (col) loadCategorical(datasetId, col);
            });

            select.addEventListener('change', () => {
                loadBtn.disabled = !select.value;
            });

            // Show overview table
            if (data.all_analyses && data.all_analyses.length > 0) {
                document.getElementById('catOverviewPanel').style.display = 'block';
                document.getElementById('catOverviewBody').innerHTML = data.all_analyses.map(a => `
                    <tr>
                        <td class="td-name">${escapeHtml(a.column)}</td>
                        <td>${a.unique}</td>
                        <td>${a.total.toLocaleString()}</td>
                        <td>${escapeHtml(String(a.top_value || '—'))}</td>
                        <td>${a.top_pct}%</td>
                        <td><span class="cardinality-badge cardinality-${a.cardinality}">${a.cardinality}</span></td>
                    </tr>
                `).join('');
            }

            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    async function loadCategorical(datasetId, column) {
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/categorical?column=${encodeURIComponent(column)}`);
            renderCategorical(data);
        } catch (e) {
            alert('Error loading categorical analysis: ' + e.message);
        }
    }

    function renderCategorical(data) {
        const analysis = data.analysis;
        if (!analysis) return;

        document.getElementById('catResultsContainer').style.display = 'grid';
        setText('catColName', `— ${escapeHtml(analysis.column)}`);
        setText('catBarColName', `— ${escapeHtml(analysis.column)}`);

        // Summary
        document.getElementById('catSummary').innerHTML = `
            <span><strong>${analysis.unique}</strong> unique values</span>
            <span><strong>${analysis.total.toLocaleString()}</strong> total</span>
            <span>Top: <strong>${escapeHtml(String(analysis.top_value || '—'))}</strong> (${analysis.top_pct}%)</span>
        `;

        // Frequency table
        document.getElementById('freqBody').innerHTML = (analysis.frequency_table || []).map(row => `
            <tr>
                <td class="td-name">${escapeHtml(row.value)}</td>
                <td>${row.count.toLocaleString()}</td>
                <td>
                    <div style="display:flex;align-items:center;gap:0.5rem;">
                        <div style="flex:1;height:6px;background:#E5E7EB;border-radius:3px;overflow:hidden;">
                            <div style="height:100%;width:${row.percentage}%;background:var(--primary);border-radius:3px;"></div>
                        </div>
                        <span style="min-width:40px;text-align:right;">${row.percentage}%</span>
                    </div>
                </td>
            </tr>
        `).join('');

        // Bar chart
        const values = (analysis.frequency_table || []).map(r => r.value);
        const counts = (analysis.frequency_table || []).map(r => r.count);
        const pcts = (analysis.frequency_table || []).map(r => r.percentage);

        const trace = {
            x: values,
            y: counts,
            type: 'bar',
            marker: {
                color: counts.map((_, i) => i < 5 ? 'rgba(99, 102, 241, 0.7)' : 'rgba(99, 102, 241, 0.4)'),
            },
            text: pcts.map(p => p + '%'),
            textposition: 'outside',
        };

        const layout = {
            xaxis: { title: 'Value', gridcolor: '#e5e7eb' },
            yaxis: { title: 'Count', gridcolor: '#e5e7eb' },
            margin: { l: 60, r: 20, t: 20, b: 80 },
            xaxis: { tickangle: -45 },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
        };

        Plotly.newPlot('catBarChart', [trace], layout, { responsive: true });
    }

    // ── Insights ─────────────────────────────────────────────────

    async function loadInsights(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/insights`);
            renderInsights(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }

    function renderInsights(data) {
        setText('insightTotal', data.total);
        setText('insightHigh', data.high_priority);
        setText('insightMedium', data.medium_priority);
        setText('insightLow', data.low_priority);

        if (!data.insights || data.insights.length === 0) {
            document.getElementById('noInsightsMsg').style.display = 'block';
            document.getElementById('insightsList').style.display = 'none';
            return;
        }

        document.getElementById('insightsList').style.display = 'flex';
        const list = document.getElementById('insightsList');
        list.innerHTML = data.insights.map((insight, i) => {
            const item = renderInsightItem(insight);
            return item.replace('insight-item', `insight-item`); 
        }).join('');

        const aiSections = document.getElementById('aiEngineSections');
        if (aiSections) aiSections.style.display = 'flex';

        // Render Anomalies
        const anomaliesContainer = document.getElementById('anomaliesContainer');
        if (anomaliesContainer) {
            if (data.anomalies && data.anomalies.count > 0) {
                anomaliesContainer.innerHTML = `<p class="text-muted mb-3">Found ${data.anomalies.count} anomalous rows (${data.anomalies.percentage.toFixed(1)}%).</p>` +
                    data.anomalies.items.map(a => `<div class="insight-item"><div class="insight-icon insight-warning">⚠</div><div class="insight-body"><div class="insight-message">Row ${a.index} <span class="priority-badge priority-high">Score: ${Number(a.score).toFixed(2)}</span></div><div class="insight-meta">${a.description} (${a.method})</div></div></div>`).join('');
            } else {
                anomaliesContainer.innerHTML = '<p class="text-muted">No significant anomalies detected.</p>';
            }
        }

        // Render Root Causes
        const rootCausesContainer = document.getElementById('rootCausesContainer');
        if (rootCausesContainer) {
            if (data.root_causes && data.root_causes.length > 0) {
                rootCausesContainer.innerHTML = data.root_causes.map(r => `<div class="insight-item"><div class="insight-icon insight-insight">💡</div><div class="insight-body"><div class="insight-message">${r.issue_type} <span class="priority-badge priority-medium">Impact: ${Number(r.impact_level).toFixed(2)}</span></div><div class="insight-meta mb-1">${r.description}</div><div class="insight-meta" style="color:var(--primary);"><strong>Condition:</strong> ${r.suggested_action}</div></div></div>`).join('');
            } else {
                rootCausesContainer.innerHTML = '<p class="text-muted">No root causes identified.</p>';
            }
        }

        // Render Recommendations
        const recommendationsContainer = document.getElementById('recommendationsContainer');
        if (recommendationsContainer) {
            if (data.recommendations && data.recommendations.length > 0) {
                recommendationsContainer.innerHTML = data.recommendations.map(r => `<div class="insight-item" style="border-left: 3px solid var(--primary);"><div class="insight-icon insight-info">ℹ</div><div class="insight-body"><div class="insight-message">${r.title}</div><div class="insight-meta mb-1">${r.description}</div><div class="insight-meta text-success"><strong>Category:</strong> ${r.expected_impact}</div></div></div>`).join('');
            } else {
                recommendationsContainer.innerHTML = '<p class="text-muted">No recommendations generated.</p>';
            }
        }

        // Add filter functionality
        const filterBtns = document.querySelectorAll('.btn-filter');
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const filter = btn.dataset.filter;
                const items = list.querySelectorAll('.insight-item');
                items.forEach(item => {
                    if (filter === 'all') {
                        item.style.display = 'flex';
                    } else {
                        const priority = item.dataset.priority;
                        const category = item.dataset.category;
                        item.style.display = (priority === filter || category === filter) ? 'flex' : 'none';
                    }
                });
            });
        });
    }

    function renderInsightItem(insight) {
        const iconClass = insight.type === 'warning' ? 'insight-warning' :
            insight.type === 'insight' ? 'insight-insight' : 'insight-info';
        const iconEmoji = insight.type === 'warning' ? '⚠' :
            insight.type === 'insight' ? '💡' : 'ℹ';
        return `<div class="insight-item" data-priority="${insight.priority || ''}" data-category="${insight.category || ''}">
            <div class="insight-icon ${iconClass}">${iconEmoji}</div>
            <div class="insight-body">
                <div class="insight-message">${escapeHtml(insight.message)}</div>
                <div class="insight-meta">
                    <span class="priority-badge priority-${insight.priority || 'low'}">${(insight.priority || 'low').toUpperCase()}</span>
                    ${insight.category ? `<span class="category-badge">${insight.category}</span>` : ''}
                </div>
            </div>
        </div>`;
    }

    // ── Time Series ──────────────────────────────────────────────
    
    async function initTimeseries(datasetId) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/timeseries`);
            
            const dateSelect = document.getElementById('tsDateSelect');
            const valSelect = document.getElementById('tsValueSelect');
            const loadBtn = document.getElementById('loadTsBtn');
            
            if (!data.datetime_cols || data.datetime_cols.length === 0) {
                showError("No datetime columns found in this dataset.");
                return;
            }
            
            dateSelect.innerHTML = data.datetime_cols.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
            valSelect.innerHTML = (data.numeric_cols || []).map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
            
            if (data.date_col) dateSelect.value = data.date_col;
            if (data.value_col) valSelect.value = data.value_col;
            
            loadBtn.disabled = false;
            loadBtn.addEventListener('click', () => {
                const dc = dateSelect.value;
                const vc = valSelect.value;
                if (dc && vc) loadTimeseries(datasetId, dc, vc);
            });
            
            renderTimeseries(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }
    
    async function loadTimeseries(datasetId, dateCol, valueCol) {
        showLoading();
        try {
            const data = await fetchJSON(`${API_BASE}/${datasetId}/timeseries?date_col=${encodeURIComponent(dateCol)}&value_col=${encodeURIComponent(valueCol)}`);
            renderTimeseries(data);
            showContent();
        } catch (e) {
            showError(e.message);
        }
    }
    
    function renderTimeseries(data) {
        document.getElementById('tsOriginalContainer').style.display = 'flex';
        document.getElementById('tsSeasonalityContainer').style.display = 'block';
        document.getElementById('tsForecastContainer').style.display = 'block';
        
        // Original Chart
        if (data.original_data) {
            const trace = {
                x: data.original_data.dates,
                y: data.original_data.values,
                type: 'scatter',
                mode: 'lines',
                line: { color: 'rgba(99, 102, 241, 1)', width: 2 },
                name: data.value_col
            };
            
            // Add anomalies to original chart if any
            const traces = [trace];
            if (data.anomalies && data.anomalies.count > 0 && data.original_data) {
                // Find matching values for anomaly dates to plot markers
                const anomVals = [];
                const anomDates = [];
                for (let i=0; i<data.original_data.dates.length; i++) {
                    if (data.anomalies.dates.includes(data.original_data.dates[i])) {
                        anomDates.push(data.original_data.dates[i]);
                        anomVals.push(data.original_data.values[i]);
                    }
                }
                traces.push({
                    x: anomDates,
                    y: anomVals,
                    type: 'scatter',
                    mode: 'markers',
                    marker: { color: 'red', size: 8, symbol: 'x' },
                    name: 'Anomalies'
                });
            }
            
            const layout = {
                margin: { l: 40, r: 20, t: 10, b: 30 },
                xaxis: { gridcolor: '#e5e7eb' },
                yaxis: { gridcolor: '#e5e7eb' },
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                showlegend: traces.length > 1,
                legend: { orientation: 'h', y: 1.1 }
            };
            Plotly.newPlot('tsOriginalChart', traces, layout, { responsive: true });
        }
        
        // Stationarity & Anomalies
        const statPanel = document.getElementById('tsStationarityContent');
        if (data.stationarity) {
            if (data.stationarity.error) {
                statPanel.innerHTML = `<div class="insight-item"><div class="insight-icon insight-warning">⚠</div><div class="insight-body">${data.stationarity.error}</div></div>`;
            } else {
                const s = data.stationarity;
                const isStat = s.is_stationary;
                statPanel.innerHTML = `
                    <div style="margin-bottom:10px;">
                        <span class="priority-badge ${isStat ? 'priority-high' : 'priority-medium'}" style="font-size:14px; padding:5px 10px;">
                            ${isStat ? 'Stationary' : 'Non-Stationary'}
                        </span>
                    </div>
                    <div class="text-muted mb-2">p-value: ${s.p_value.toFixed(4)}</div>
                    <div class="text-muted">Test Statistic: ${s.test_statistic.toFixed(4)}</div>
                `;
            }
        }
        
        const anomPanel = document.getElementById('tsAnomaliesContent');
        if (data.anomalies) {
            if (data.anomalies.count > 0) {
                anomPanel.innerHTML = `<div class="text-danger fw-bold">Detected ${data.anomalies.count} anomalies</div>`;
            } else {
                anomPanel.innerHTML = `<div class="text-muted">No major anomalies detected in rolling window.</div>`;
            }
        }
        
        // Seasonality
        const sError = document.getElementById('tsSeasonalityContent');
        const sCharts = document.getElementById('tsSeasonalityCharts');
        if (data.seasonality) {
            if (data.seasonality.error) {
                sError.style.display = 'block';
                sError.innerHTML = `<p>${escapeHtml(data.seasonality.error)}</p>`;
                sCharts.style.display = 'none';
            } else {
                sError.style.display = 'none';
                sCharts.style.display = 'block';
                
                const dates = Object.keys(data.seasonality.trend);
                const trend = Object.values(data.seasonality.trend);
                const seasonal = dates.map(d => data.seasonality.seasonal[d]);
                const resid = dates.map(d => data.seasonality.residual[d]);
                
                const layoutBase = {
                    margin: { l: 40, r: 20, t: 30, b: 20 },
                    xaxis: { gridcolor: '#e5e7eb' },
                    yaxis: { gridcolor: '#e5e7eb' },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent'
                };
                
                Plotly.newPlot('tsTrendChart', [{ x: dates, y: trend, type: 'scatter', mode: 'lines', line: {color:'#F59E0B'}, name: 'Trend' }], {...layoutBase, title: 'Trend'}, {responsive: true});
                Plotly.newPlot('tsSeasonalChart', [{ x: dates, y: seasonal, type: 'scatter', mode: 'lines', line: {color:'#10B981'}, name: 'Seasonal' }], {...layoutBase, title: 'Seasonality'}, {responsive: true});
                Plotly.newPlot('tsResidualChart', [{ x: dates, y: resid, type: 'scatter', mode: 'markers', marker: {color:'#6B7280', size:4}, name: 'Residual' }], {...layoutBase, title: 'Residuals'}, {responsive: true});
            }
        }
        
        // Forecast
        const fError = document.getElementById('tsForecastError');
        const fChart = document.getElementById('tsForecastChart');
        if (data.forecast) {
            if (data.forecast.error) {
                fError.style.display = 'block';
                fError.innerHTML = `<p>${escapeHtml(data.forecast.error)}</p>`;
                fChart.style.display = 'none';
            } else if (data.forecast.data) {
                fError.style.display = 'none';
                fChart.style.display = 'block';
                
                const fDates = data.forecast.data.map(d => d.ds);
                const fYhat = data.forecast.data.map(d => d.yhat);
                const fLower = data.forecast.data.map(d => d.yhat_lower);
                const fUpper = data.forecast.data.map(d => d.yhat_upper);
                
                const traces = [];
                
                // Historical
                if (data.original_data) {
                    traces.push({
                        x: data.original_data.dates,
                        y: data.original_data.values,
                        type: 'scatter',
                        mode: 'lines',
                        name: 'Historical',
                        line: { color: 'rgba(107, 114, 128, 0.6)' }
                    });
                }
                
                // Forecast bounds
                traces.push({
                    x: fDates.concat(fDates.slice().reverse()),
                    y: fUpper.concat(fLower.slice().reverse()),
                    fill: 'toself',
                    fillcolor: 'rgba(59, 130, 246, 0.2)',
                    line: { color: 'transparent' },
                    name: '80% Confidence',
                    showlegend: true,
                    type: 'scatter'
                });
                
                // Forecast line
                traces.push({
                    x: fDates,
                    y: fYhat,
                    type: 'scatter',
                    mode: 'lines',
                    name: 'Forecast',
                    line: { color: 'rgba(59, 130, 246, 1)', width: 2, dash: 'dot' }
                });
                
                const layout = {
                    margin: { l: 40, r: 20, t: 20, b: 30 },
                    xaxis: { gridcolor: '#e5e7eb' },
                    yaxis: { gridcolor: '#e5e7eb' },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    hovermode: 'x unified'
                };
                
                Plotly.newPlot('tsForecastChart', traces, layout, { responsive: true });
            }
        }
    }

    // ── Utilities ────────────────────────────────────────────────
    
    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ── Public API ────────────────────────────────────────────────

    return {
        loadOverview,
        loadQuality,
        loadStatistics,
        loadCorrelations,
        initDistributions,
        loadDistribution,
        loadOutliers,
        initCategorical,
        loadCategorical,
        loadInsights,
        initTimeseries,
        loadTimeseries,
    };
})();

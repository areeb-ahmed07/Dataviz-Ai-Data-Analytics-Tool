/**
 * DataViz Pro — XAI (Explainable AI) JavaScript
 * Handles: model selection, workspace, global/local explanations, predictions.
 * Uses Plotly for all chart rendering.
 */

/* ── Constants ──────────────────────────────────────────────── */

var XAI_COLORS = {
    primary: '#6366F1',
    primaryLight: '#818CF8',
    primaryPale: '#A5B4FC',
    primaryGhost: '#C7D2FE',
    positive: '#10B981',
    positiveLight: '#D1FAE5',
    negative: '#EF4444',
    negativeLight: '#FEE2E2',
    shap: '#6366F1',
    lime: '#3B82F6',
    native: '#8B5CF6',
    permutation: '#F59E0B',
};

var XAI_PLOTLY_CONFIG = {
    responsive: true,
    displayModeBar: false,
};

var XAI_PLOTLY_LAYOUT_BASE = {
    paper_bgcolor: 'white',
    plot_bgcolor: 'white',
    font: { family: 'Inter, system-ui, sans-serif', size: 12, color: '#475569' },
    margin: { l: 80, r: 30, t: 30, b: 60 },
    xaxis: { gridcolor: '#E2E8F0', zerolinecolor: '#E2E8F0' },
    yaxis: { gridcolor: '#E2E8F0', zerolinecolor: '#E2E8F0' },
};

/* ── Utility Functions ──────────────────────────────────────── */

function apiFetch(url, options) {
    var opts = options || {};
    var headers = opts.headers || {};
    if (opts.method && opts.method !== 'GET' && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    var token = getCsrfToken();
    if (token) {
        headers['X-CSRFToken'] = token;
    }
    opts.headers = headers;
    return fetch(url, opts).then(function (resp) {
        return resp.json().then(function (data) {
            if (!resp.ok) {
                throw new Error(data.error || data.message || 'Request failed with status ' + resp.status);
            }
            return data;
        });
    });
}

function apiFetchWithPolling(url, options) {
    return new Promise(function (resolve, reject) {
        apiFetch(url, options).then(function (data) {
            if (data && data.job_id) {
                var interval = setInterval(function () {
                    apiFetch('/api/models/' + MODEL_ID + '/xai/status/' + data.job_id).then(function (statusData) {
                        if (statusData.status === 'done') {
                            clearInterval(interval);
                            resolve(statusData.result);
                        } else if (statusData.status === 'error') {
                            clearInterval(interval);
                            reject(new Error(statusData.error || 'Job failed'));
                        }
                    }).catch(function (e) {
                        clearInterval(interval);
                        reject(e);
                    });
                }, 1500);
            } else {
                resolve(data);
            }
        }).catch(reject);
    });
}

function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    var input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return null;
}

function formatNumber(n, decimals) {
    if (n === undefined || n === null) return '—';
    if (typeof n === 'string') return n;
    var d = decimals !== undefined ? decimals : 4;
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

function formatPercent(n) {
    if (n === undefined || n === null) return '—';
    return (Number(n) * 100).toFixed(1) + '%';
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    var s = String(str);
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function renderLoading(containerId, text) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>' + escapeHtml(text || 'Loading...') + '</span></div>';
}

function renderEmpty(containerId, title, desc) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="xai-empty"><h3>' + escapeHtml(title || 'No data') + '</h3>' + (desc ? '<p>' + escapeHtml(desc) + '</p>' : '') + '</div>';
}

function renderError(containerId, message) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="xai-error"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg><span>' + escapeHtml(message || 'An error occurred.') + '</span></div>';
}

function showXAIWarning(containerId, title, message) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.style.display = 'block';
    el.innerHTML = '<strong>' + escapeHtml(title || 'Warning') + '</strong>: ' + escapeHtml(message);
}

function _hideEl(id) { var el = document.getElementById(id); if (el) el.style.display = 'none'; }
function _showEl(id) { var el = document.getElementById(id); if (el) el.style.display = ''; }

/* ── XAI Model Selection (index.html) ──────────────────────── */

var XAIService = {
    models: [],

    init: function () {
        this.loadModels();
    },

    loadModels: function () {
        var grid = document.getElementById('xaiModelsGrid');
        if (!grid) return;
        grid.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Loading models...</span></div>';
        _hideEl('xaiModelsEmpty');
        _hideEl('xaiModelsError');
        _hideEl('xaiModelsLoading');

        apiFetch('/api/xai/models').then(function (data) {
            var models = data.models || data || [];
            if (!Array.isArray(models)) models = [];

            if (models.length === 0) {
                grid.style.display = 'none';
                _showEl('xaiModelsEmpty');
                return;
            }

            var html = '<div class="xai-model-grid">';
            for (var i = 0; i < models.length; i++) {
                html += XAIService._renderCard(models[i]);
            }
            html += '</div>';
            grid.innerHTML = html;
            grid.style.display = '';

            grid.onclick = function (e) {
                var card = e.target.closest('[data-model-id]');
                if (card) window.location.href = '/models/' + card.dataset.modelId + '/explain';
            };
        }).catch(function (err) {
            grid.style.display = 'none';
            _showEl('xaiModelsError');
            var msgEl = document.getElementById('xaiModelsErrorMsg');
            if (msgEl) msgEl.textContent = err.message || 'Failed to load models.';
        });
    },

    _renderCard: function (model) {
        var id = model.id || model.model_id || '';
        var name = model.name || model.model_name || 'Untitled Model';
        var algorithm = model.algorithm || '';
        var problemType = model.problem_type || '';
        var score = model.score;
        var metrics = model.metrics || {};
        var methods = model.supported_methods || model.methods || ['native'];
        var datasetName = model.dataset_name || '';

        var badgesHtml = '';
        for (var i = 0; i < methods.length; i++) {
            var m = methods[i].toLowerCase();
            badgesHtml += '<span class="xai-badge xai-badge-' + m + '">' + escapeHtml(m.toUpperCase()) + '</span>';
        }

        var metricHtml = '';
        var keys = Object.keys(metrics).slice(0, 3);
        if (keys.length > 0) {
            metricHtml = '<div class="xai-model-card-metrics">';
            for (var j = 0; j < keys.length; j++) {
                metricHtml += '<div><div class="xai-metric-label">' + escapeHtml(keys[j]) + '</div><div class="xai-metric-value">' + formatNumber(metrics[keys[j]], 4) + '</div></div>';
            }
            metricHtml += '</div>';
        }

        var scoreHtml = (score !== null && score !== undefined)
            ? '<div class="xai-metric-row"><div><div class="xai-metric-label">Best Score</div><div class="xai-metric-value">' + formatNumber(score, 4) + '</div></div></div>'
            : '';

        return '<div class="xai-model-card" data-model-id="' + escapeHtml(String(id)) + '">' +
            '<div class="xai-model-card-header">' +
                '<div class="xai-model-card-icon"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z"></path><line x1="9" y1="21" x2="15" y2="21"></line></svg></div>' +
                '<div class="xai-model-card-info"><div class="xai-model-card-name">' + escapeHtml(name) + '</div><div class="xai-model-card-type">' + escapeHtml(algorithm) + (problemType ? ' • ' + escapeHtml(problemType) : '') + '</div></div>' +
            '</div>' +
            (datasetName ? '<div style="font-size:0.82rem;color:#475569;">Dataset: ' + escapeHtml(datasetName) + '</div>' : '') +
            scoreHtml + metricHtml +
            '<div class="xai-model-card-badges">' + badgesHtml + '</div></div>';
    }
};

/* ── XAI Workspace (workspace.html) ────────────────────────── */

var XAIWorkspace = {
    modelId: null,
    modelInfo: null,
    activeTab: 'overview',
    apiBase: '',
    totalRows: 0,

    init: function (modelId) {
        this.modelId = modelId || window.MODEL_ID || null;
        if (!this.modelId) return;
        this.apiBase = '/api/xai/models/' + this.modelId;
        this.loadSummary();
    },

    switchTab: function (tabName) {
        this.activeTab = tabName;
        // Update tab buttons
        document.querySelectorAll('.xai-tab').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        // Update tab panels
        document.querySelectorAll('.xai-tab-panel').forEach(function (panel) {
            panel.classList.toggle('active', panel.dataset.tab === tabName);
        });
        // Load tab content
        switch (tabName) {
            case 'overview': this.loadOverview(); break;
            case 'global':
                if (typeof XAIGlobal !== 'undefined') XAIGlobal.init(this.modelId);
                break;
            case 'local':
                if (typeof XAILocal !== 'undefined') XAILocal.init(this.modelId);
                break;
            case 'prediction':
                if (typeof XAIPrediction !== 'undefined') XAIPrediction.init(this.modelId);
                break;
        }
    },

    loadSummary: function () {
        var self = this;
        var container = document.getElementById('xaiModelSummary');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Loading model details...</span></div>';

        apiFetch(this.apiBase + '/summary').then(function (data) {
            self.modelInfo = data;
            self.totalRows = data.total_rows || data.n_samples || 0;
            self._renderSummary(data);
            // Update breadcrumb
            var breadcrumb = document.getElementById('xaiBreadcrumbModel');
            if (breadcrumb) breadcrumb.textContent = data.model_name || data.name || 'Model';
        }).catch(function (err) {
            renderError('xaiModelSummary', err.message || 'Failed to load model summary.');
        });
    },

    _renderSummary: function (data) {
        var container = document.getElementById('xaiModelSummary');
        if (!container) return;

        var name = data.name || data.model_name || 'Model';
        var algorithm = data.algorithm || '';
        var problemType = data.problem_type || '';
        var features = data.n_features || 0;
        var rows = data.n_samples || data.total_rows || 0;
        var score = data.score !== undefined && data.score !== null ? data.score : (data.best_score || null);
        var methods = data.supported_methods || data.methods || ['native'];
        var metrics = data.metrics || {};

        var badgesHtml = '';
        for (var i = 0; i < methods.length; i++) {
            badgesHtml += '<span class="xai-badge xai-badge-' + methods[i].toLowerCase() + '">' + escapeHtml(methods[i].toUpperCase()) + '</span>';
        }

        var statsHtml = '';
        if (score !== null) {
            statsHtml += '<div class="xai-stat-item highlight"><div class="xai-metric-label">Score</div><div class="xai-metric-value">' + formatNumber(score, 4) + '</div></div>';
        }
        for (var key in metrics) {
            if (metrics.hasOwnProperty(key)) {
                statsHtml += '<div class="xai-stat-item"><div class="xai-metric-label">' + escapeHtml(key) + '</div><div class="xai-metric-value">' + formatNumber(metrics[key], 4) + '</div></div>';
            }
        }
        statsHtml += '<div class="xai-stat-item"><div class="xai-metric-label">Features</div><div class="xai-metric-value">' + features + '</div></div>';
        statsHtml += '<div class="xai-stat-item"><div class="xai-metric-label">Samples</div><div class="xai-metric-value">' + rows.toLocaleString() + '</div></div>';

        container.innerHTML =
            '<div class="xai-card"><div class="xai-card-header"><div class="xai-card-title">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z"></path><line x1="9" y1="21" x2="15" y2="21"></line></svg>' +
                escapeHtml(name) + '</div><div class="xai-card-actions">' + badgesHtml + '</div></div>' +
                '<div class="xai-card-body"><div style="font-size:0.85rem;color:#475569;margin-bottom:0.75rem;">' +
                escapeHtml(algorithm) + (problemType ? ' • ' + escapeHtml(problemType.charAt(0).toUpperCase() + problemType.slice(1)) : '') +
                '</div><div class="xai-stat-grid">' + statsHtml + '</div></div></div>';

        // Bind tab clicks
        document.querySelectorAll('.xai-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                XAIWorkspace.switchTab(btn.dataset.tab);
            });
        });

        // Load overview tab by default
        this.switchTab('overview');
    },

    loadOverview: function () {
        var self = this;
        var self2 = this;
        // Load top features
        apiFetch(this.apiBase + '/overview').then(function (data) {
            // Top features chart
            if (data.top_features && data.top_features.length > 0) {
                self.renderFeatureImportanceChart(data.top_features, 'xaiTopFeatures');
            }
            // Model performance
            var perfContainer = document.getElementById('xaiModelPerformance');
            if (perfContainer && (data.performance || data.metrics)) {
                var perf = data.performance || data.metrics || {};
                var html = '<div class="xai-stat-grid">';
                for (var key in perf) {
                    if (perf.hasOwnProperty(key)) {
                        html += '<div class="xai-stat-item"><div class="xai-metric-label">' + escapeHtml(key) + '</div><div class="xai-metric-value">' + formatNumber(perf[key], 4) + '</div></div>';
                    }
                }
                html += '</div>';
                perfContainer.innerHTML = html;
            }
            // Available methods
            var methodsContainer = document.getElementById('xaiAvailableMethods');
            if (methodsContainer && data.task_type) {
                var isClustering = data.task_type === 'clustering';
                var mHtml = '<div style="display:flex;gap:0.5rem;flex-wrap:wrap;">';
                mHtml += '<span class="xai-badge xai-badge-native">NATIVE</span>';
                mHtml += '<span class="xai-badge xai-badge-permutation">PERMUTATION</span>';
                if (!isClustering) {
                    mHtml += '<span class="xai-badge xai-badge-shap">SHAP</span>';
                    mHtml += '<span class="xai-badge xai-badge-lime">LIME</span>';
                }
                mHtml += '</div>';
                methodsContainer.innerHTML = mHtml;
            }
            // Warnings
            if (data.warnings && data.warnings.length > 0) {
                _showEl('xaiOverviewWarnings');
                var wContent = document.getElementById('xaiOverviewWarningsContent');
                if (wContent) wContent.innerHTML = '<ul>' + data.warnings.map(function (w) { return '<li>' + escapeHtml(w) + '</li>'; }).join('') + '</ul>';
            }
        }).catch(function (err) {
            renderError('xaiTopFeatures', err.message);
        });
    },

    /* ── Chart Renderers (shared) ──────────────────────────── */

    renderFeatureImportanceChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var features = Array.isArray(data) ? data : (data.features || []);
        if (features.length === 0) return;

        var names = [], values = [];
        for (var i = 0; i < features.length; i++) {
            var f = features[i];
            names.push(f.name || f.feature || ('Feature ' + (i + 1)));
            values.push(f.importance !== undefined ? f.importance : (f.value || 0));
        }

        var trace = {
            type: 'bar', orientation: 'h',
            y: names.slice().reverse(), x: values.slice().reverse(),
            marker: { color: values.slice().reverse().map(function (v, idx) {
                if (idx < 3) return XAI_COLORS.primary;
                if (idx < 6) return XAI_COLORS.primaryLight;
                if (idx < 9) return XAI_COLORS.primaryPale;
                return XAI_COLORS.primaryGhost;
            }), line: { color: 'white', width: 1 } },
            hovertemplate: '<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, features.length * 32 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 40 },
            xaxis: { title: 'Importance', gridcolor: '#E2E8F0' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    renderSHAPSummaryChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var features = data.features || [];
        var shapValues = data.values || data.shap_values || [];
        var featureValues = data.feature_values || data.data || [];
        if (features.length === 0 || shapValues.length === 0) return;

        var traces = [];
        for (var i = 0; i < features.length; i++) {
            traces.push({
                type: 'scatter', mode: 'markers',
                y: Array(shapValues[i].length).fill(features[i]),
                x: shapValues[i],
                marker: { color: featureValues[i] || [], colorscale: 'RdBu', cmin: -1, cmax: 1, size: 6, line: { color: 'white', width: 0.5 } },
                showlegend: false,
                hovertemplate: '<b>' + features[i] + '</b><br>SHAP: %{x:.4f}<br>Value: %{marker.color:.4f}<extra></extra>',
            });
        }
        var height = Math.max(350, features.length * 32 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 50 },
            xaxis: { title: 'SHAP Value', gridcolor: '#E2E8F0', zeroline: true, zerolinecolor: '#CBD5E1' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, traces, layout, XAI_PLOTLY_CONFIG);
    },

    renderSHAPLocalChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var features = data.features || [];
        var values = data.values || data.shap_values || [];
        var baseValue = data.base_value || data.expected_value || 0;
        if (features.length === 0) return;

        var colors = values.map(function (v) { return v >= 0 ? XAI_COLORS.positive : XAI_COLORS.negative; });
        var textValues = values.map(function (v) { return (v >= 0 ? '+' : '') + v.toFixed(4); });
        var trace = {
            type: 'bar', orientation: 'h',
            y: features.slice().reverse(), x: values.slice().reverse(),
            marker: { color: colors.slice().reverse(), line: { color: 'white', width: 1 } },
            text: textValues.slice().reverse(), textposition: 'outside',
            textfont: { size: 11, color: '#475569' },
            hovertemplate: '<b>%{y}</b><br>SHAP: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, features.length * 30 + 100);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 50, t: 40, b: 40 },
            title: { text: 'Base Value: ' + formatNumber(baseValue, 4), font: { size: 12, color: '#6B7280' } },
            xaxis: { title: 'SHAP Value', gridcolor: '#E2E8F0', zeroline: true, zerolinecolor: '#CBD5E1' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false, barmode: 'relative',
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    renderLIMEChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var features = data.features || data.local_exp || [];
        var values = data.values || [];
        if (features.length === 0) return;

        var names = [], weights = [];
        if (!Array.isArray(features[0])) {
            names = features; weights = values;
        } else {
            for (var i = 0; i < features.length; i++) {
                weights.push(features[i][0] || 0);
                names.push(String(features[i][1] || ''));
            }
        }
        var colors = weights.map(function (w) { return w >= 0 ? XAI_COLORS.positive : XAI_COLORS.negative; });
        var trace = {
            type: 'bar', orientation: 'h',
            y: names.slice().reverse(), x: weights.slice().reverse(),
            marker: { color: colors.slice().reverse(), line: { color: 'white', width: 1 } },
            hovertemplate: '<b>%{y}</b><br>Weight: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, names.length * 30 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 40 },
            xaxis: { title: 'LIME Weight', gridcolor: '#E2E8F0', zeroline: true, zerolinecolor: '#CBD5E1' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    renderProbabilityBars: function (probabilities, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        if (!probabilities || Object.keys(probabilities).length === 0) return;
        var entries = Object.entries(probabilities).sort(function (a, b) { return b[1] - a[1]; });
        var maxP = entries.length > 0 ? entries[0][1] : 1;
        var html = '<div style="max-height:200px;overflow-y:auto;">';
        for (var i = 0; i < entries.length; i++) {
            var label = entries[i][0], prob = entries[i][1];
            var pct = maxP > 0 ? (prob / maxP) * 100 : 0;
            html += '<div style="margin-bottom:0.5rem;"><div style="display:flex;justify-content:space-between;font-size:0.82rem;margin-bottom:0.2rem;"><span>' + escapeHtml(label) + '</span><span>' + formatPercent(prob) + '</span></div>';
            html += '<div style="height:8px;background:#E2E8F0;border-radius:4px;overflow:hidden;"><div style="height:100%;width:' + pct + '%;background:' + XAI_COLORS.primary + ';border-radius:4px;"></div></div></div>';
        }
        html += '</div>';
        el.innerHTML = html;
    },

    renderComparisonChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var rows = data.features || data.rows || [];
        if (rows.length === 0) return;

        var nativeVals = [], shapVals = [], permVals = [], names = [];
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            names.push(r.feature || ('Feature ' + (i + 1)));
            nativeVals.push(r.native !== null && r.native !== undefined ? r.native : 0);
            shapVals.push(r.shap !== null && r.shap !== undefined ? r.shap : 0);
            permVals.push(r.permutation !== null && r.permutation !== undefined ? r.permutation : 0);
        }

        var traces = [];
        traces.push({ type: 'bar', name: 'Native', x: names, y: nativeVals, marker: { color: XAI_COLORS.native } });
        traces.push({ type: 'bar', name: 'SHAP', x: names, y: shapVals, marker: { color: XAI_COLORS.shap } });
        traces.push({ type: 'bar', name: 'Permutation', x: names, y: permVals, marker: { color: XAI_COLORS.permutation } });

        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: Math.max(300, rows.length * 28 + 60),
            margin: { l: 140, r: 30, t: 30, b: 80 },
            barmode: 'group',
            xaxis: { tickangle: -35, gridcolor: 'transparent' },
            yaxis: { title: 'Importance', gridcolor: '#E2E8F0' },
            legend: { orientation: 'h', y: -0.25, x: 0.5, xanchor: 'center' },
        });
        Plotly.newPlot(el, traces, layout, XAI_PLOTLY_CONFIG);
    },

    generateBusinessExplanation: function (data) {
        var container = document.getElementById('xaiPredBusinessContent');
        if (!container) return;
        var text = data.business_explanation || '';
        if (!text) {
            var contributors = data.contributors || [];
            var topPos = contributors.filter(function (c) { return (c.shap_value || c.contribution || 0) > 0; }).slice(0, 3);
            var topNeg = contributors.filter(function (c) { return (c.shap_value || c.contribution || 0) < 0; }).slice(0, 3);
            text = 'This prediction is driven primarily by ';
            if (topPos.length > 0) text += topPos.map(function (c) { return c.feature; }).join(', ');
            if (topNeg.length > 0) text += (topPos.length > 0 ? ' and decreased by ' : ' decreased by ') + topNeg.map(function (c) { return c.feature; }).join(', ');
            text += '.';
        }
        var card = document.getElementById('xaiPredBusinessCard');
        if (card) card.style.display = '';
        container.innerHTML = '<p>' + text + '</p>';
    },

    showWarning: function (containerId, message) {
        var el = document.getElementById(containerId);
        if (!el) return;
        el.style.display = 'block';
        el.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:#D97706;flex-shrink:0;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg><div>' + escapeHtml(message) + '</div>';
    },
};

/* ── XAI Global Explanations (global.html) ──────────────────── */

var XAIGlobal = {
    modelId: null,
    apiBase: '',
    initialized: false,
    features: [],

    init: function (modelId) {
        if (this.initialized && this.modelId === modelId) return;
        this.modelId = modelId || XAIWorkspace.modelId;
        this.apiBase = '/api/xai/models/' + this.modelId + '/global';
        this.initialized = true;
        this.bindEvents();
        this.loadAll();
    },

    bindEvents: function () {
        var topNSelect = document.getElementById('xaiGlobalTopN');
        if (topNSelect) topNSelect.onchange = function () { XAIGlobal.loadAll(); };
        var sampleSelect = document.getElementById('xaiGlobalSampleSize');
        if (sampleSelect) sampleSelect.onchange = function () { XAIGlobal.loadAll(); };
        var depFeature = document.getElementById('xaiDependenceFeature');
        if (depFeature) depFeature.onchange = function () { XAIGlobal.loadDependencePlot(); };
        var depInteraction = document.getElementById('xaiDependenceInteraction');
        if (depInteraction) depInteraction.onchange = function () { XAIGlobal.loadDependencePlot(); };
    },

    getConfig: function () {
        var topN = parseInt(document.getElementById('xaiGlobalTopN') ? document.getElementById('xaiGlobalTopN').value : '20', 10);
        if (topN === 'all') topN = 999;
        var sampleSize = parseInt(document.getElementById('xaiGlobalSampleSize') ? document.getElementById('xaiGlobalSampleSize').value : '500', 10);
        if (sampleSize === 'all' || isNaN(sampleSize)) sampleSize = 0;
        return { topN: topN, sampleSize: sampleSize };
    },

    loadAll: function () {
        this.loadFeatureImportance();
        this.loadPermutationImportance();
        this.loadSHAPGlobal();
        this.loadSHAPSummary();
        this.loadComparison();
        this._populateDependenceFeatureSelector();
    },

    onConfigChange: function () { this.loadAll(); },
    refreshAll: function () { this.loadAll(); },

    switchSubTab: function (subtab) {
        document.querySelectorAll('.xai-subtab').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.subtab === subtab);
        });
        document.querySelectorAll('.xai-subtab-panel').forEach(function (panel) {
            panel.classList.toggle('active', panel.dataset.subtab === subtab);
        });
        // Load content for specific subtabs
        if (subtab === 'shap-dependence') this._populateDependenceFeatureSelector();
    },

    _populateDependenceFeatureSelector: function () {
        var select = document.getElementById('xaiDependenceFeature');
        if (!select || this.features.length === 0) {
            // Load features from summary
            var self = this;
            var config = self.getConfig();
            apiFetch(self.apiBase + '/feature-importance?top_n=' + config.topN).then(function (data) {
                if (data.features) {
                    self.features = data.features;
                    self._fillFeatureSelector(select, data.features);
                }
            }).catch(function () {});
            return;
        }
        this._fillFeatureSelector(select, this.features);
    },

    _fillFeatureSelector: function (select, features) {
        if (!select) return;
        var current = select.value;
        select.innerHTML = '<option value="">Select a feature...</option>';
        for (var i = 0; i < features.length; i++) {
            var opt = document.createElement('option');
            opt.value = i;
            opt.textContent = features[i].name || features[i].feature || ('Feature ' + (i + 1));
            select.appendChild(opt);
        }
        if (current) select.value = current;
        // Also populate interaction selector
        var interSelect = document.getElementById('xaiDependenceInteraction');
        if (interSelect) {
            var currentInt = interSelect.value;
            interSelect.innerHTML = '<option value="">None</option>';
            for (var j = 0; j < features.length; j++) {
                var opt2 = document.createElement('option');
                opt2.value = j;
                opt2.textContent = features[j].name || features[j].feature || ('Feature ' + (j + 1));
                interSelect.appendChild(opt2);
            }
            if (currentInt) interSelect.value = currentInt;
        }
    },

    loadDependencePlot: function () {
        var featureSelect = document.getElementById('xaiDependenceFeature');
        var featureIndex = featureSelect ? parseInt(featureSelect.value, 10) : -1;
        if (isNaN(featureIndex) || featureIndex < 0) {
            _showEl('xaiGlobalShapDependenceEmpty');
            return;
        }
        _hideEl('xaiGlobalShapDependenceEmpty');
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalShapDependenceChart');
        if (container) container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing SHAP dependence values...</span></div>';

        var url = this.apiBase + '/shap/dependence?feature_index=' + featureIndex + '&sample_size=' + config.sampleSize;
        apiFetchWithPolling(url).then(function (data) {
            XAIGlobal.renderDependenceChart(data, 'xaiGlobalShapDependenceChart');
            _showEl('xaiGlobalShapDependenceInfo');
        }).catch(function (err) {
            renderError('xaiGlobalShapDependenceChart', err.message);
        });
    },

    /* ── Feature Importance ─────────────────────────────────── */

    loadFeatureImportance: function () {
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalNativeImportanceChart');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div></div>';

        var url = this.apiBase + '/feature-importance?top_n=' + config.topN;
        apiFetch(url).then(function (data) {
            if (data.features) XAIGlobal.features = data.features;
            if (!data.available || !data.features || data.features.length === 0) {
                _showEl('xaiGlobalNativeImportanceEmpty');
                _hideEl('xaiGlobalNativeImportanceLoading');
                return;
            }
            _hideEl('xaiGlobalNativeImportanceEmpty');
            XAIGlobal._renderNativeImportanceChart(data);
        }).catch(function (err) {
            _hideEl('xaiGlobalNativeImportanceLoading');
            renderError('xaiGlobalNativeImportanceChart', err.message);
        });
    },

    _renderNativeImportanceChart: function (data) {
        var el = document.getElementById('xaiGlobalNativeImportanceChart');
        if (!el) return;
        var features = data.features || [];
        if (features.length === 0) return;

        var names = [], vals = [];
        for (var i = 0; i < features.length; i++) {
            names.push(features[i].name || features[i].feature || ('Feature ' + (i + 1)));
            vals.push(features[i].importance !== undefined ? features[i].importance : (features[i].value || 0));
        }
        var trace = {
            type: 'bar', orientation: 'h',
            y: names.slice().reverse(), x: vals.slice().reverse(),
            marker: { color: vals.slice().reverse().map(function (v, idx) {
                if (idx < 3) return XAI_COLORS.native; if (idx < 6) return '#A78BFA'; return '#C4B5FD';
            }), line: { color: 'white', width: 1 } },
            hovertemplate: '<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, features.length * 32 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 40 },
            xaxis: { title: 'Importance', gridcolor: '#E2E8F0' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    /* ── Permutation Importance ─────────────────────────────── */

    loadPermutationImportance: function () {
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalPermutationChart');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing permutation importance...</span></div>';

        var url = this.apiBase + '/permutation-importance?top_n=' + config.topN + '&n_repeats=5&sample_size=' + config.sampleSize;
        apiFetch(url).then(function (data) {
            XAIGlobal._renderPermutationChart(data);
            _showEl('xaiGlobalPermutationInfo');
        }).catch(function (err) {
            renderError('xaiGlobalPermutationChart', err.message);
        });
    },

    _renderPermutationChart: function (data) {
        var el = document.getElementById('xaiGlobalPermutationChart');
        if (!el) return;
        var features = data.features || [];
        if (features.length === 0) { renderEmpty('xaiGlobalPermutationChart', 'No Permutation Data'); return; }

        var names = [], vals = [], stds = [];
        for (var i = 0; i < features.length; i++) {
            names.push(features[i].name || ('Feature ' + (i + 1)));
            vals.push(features[i].importance || features[i].value || 0);
            stds.push(features[i].std || 0);
        }
        var trace = {
            type: 'bar', orientation: 'h',
            y: names.slice().reverse(), x: vals.slice().reverse(),
            marker: { color: vals.slice().reverse().map(function (v) { return v >= 0 ? XAI_COLORS.permutation : XAI_COLORS.negative; }), line: { color: 'white', width: 1 } },
            error_x: stds.length > 0 ? { array: stds.slice().reverse(), color: '#94A3B8', thickness: 1.5, width: 4 } : undefined,
            hovertemplate: '<b>%{y}</b><br>Importance Decrease: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, features.length * 32 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 40 },
            xaxis: { title: 'Importance Decrease', gridcolor: '#E2E8F0' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    /* ── SHAP Global ─────────────────────────────────────────── */

    loadSHAPGlobal: function () {
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalFeatureImportanceChart');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing SHAP values...</span></div>';

        var url = this.apiBase + '/shap/global?top_n=' + config.topN + '&sample_size=' + config.sampleSize;
        apiFetchWithPolling(url).then(function (data) {
            XAIGlobal._renderSHAPGlobalBars(data);
        }).catch(function (err) {
            renderError('xaiGlobalFeatureImportanceChart', err.message);
        });
    },

    _renderSHAPGlobalBars: function (data) {
        var el = document.getElementById('xaiGlobalFeatureImportanceChart');
        if (!el) return;
        var features = data.features || [];
        if (features.length === 0) { renderEmpty('xaiGlobalFeatureImportanceChart', 'No SHAP Data'); return; }

        var names = [], vals = [];
        for (var i = 0; i < features.length; i++) {
            names.push(features[i].name || ('Feature ' + (i + 1)));
            vals.push(features[i].importance || features[i].value || 0);
        }
        var trace = {
            type: 'bar', orientation: 'h',
            y: names.slice().reverse(), x: vals.slice().reverse(),
            marker: { color: vals.slice().reverse().map(function (v, idx) {
                if (idx < 3) return XAI_COLORS.shap; if (idx < 6) return XAI_COLORS.primaryLight; return XAI_COLORS.primaryPale;
            }), line: { color: 'white', width: 1 } },
            hovertemplate: '<b>%{y}</b><br>Mean |SHAP|: %{x:.4f}<extra></extra>',
        };
        var height = Math.max(300, features.length * 32 + 80);
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: height, margin: { l: 140, r: 30, t: 20, b: 40 },
            xaxis: { title: 'Mean |SHAP Value|', gridcolor: '#E2E8F0' },
            yaxis: { automargin: true, gridcolor: 'transparent' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    /* ── SHAP Summary (Beeswarm) ──────────────────────────────── */

    loadSHAPSummary: function () {
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalShapSummaryChart');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing SHAP summary...</span></div>';

        var maxFeatures = Math.min(config.topN, 15);
        var url = this.apiBase + '/shap/summary?max_features=' + maxFeatures + '&sample_size=' + config.sampleSize;
        apiFetchWithPolling(url).then(function (data) {
            XAIWorkspace.renderSHAPSummaryChart(data, 'xaiGlobalShapSummaryChart');
            _showEl('xaiGlobalShapSummaryInfo');
        }).catch(function (err) {
            renderError('xaiGlobalShapSummaryChart', err.message);
        });
    },

    /* ── SHAP Dependence ──────────────────────────────────────── */

    renderDependenceChart: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var xVals = data.feature_values || [];
        var yVals = data.shap_values || [];
        var fName = data.feature_name || 'Feature';
        if (xVals.length === 0) { renderEmpty(containerId, 'No Dependence Data'); return; }

        var trace = {
            type: 'scatter', mode: 'markers',
            x: xVals, y: yVals,
            marker: { color: xVals, colorscale: 'Viridis', size: 8, opacity: 0.7, line: { color: 'white', width: 0.5 } },
            hovertemplate: '<b>' + fName + '</b>: %{x:.4f}<br>SHAP: %{y:.4f}<extra></extra>',
        };
        var layout = Object.assign({}, XAI_PLOTLY_LAYOUT_BASE, {
            height: 380, margin: { l: 60, r: 30, t: 30, b: 50 },
            title: { text: 'SHAP Dependence: ' + fName, font: { size: 13, color: '#374151' } },
            xaxis: { title: fName + ' Value', gridcolor: '#E2E8F0' },
            yaxis: { title: 'SHAP Value', gridcolor: '#E2E8F0' }, showlegend: false,
        });
        Plotly.newPlot(el, [trace], layout, XAI_PLOTLY_CONFIG);
    },

    /* ── Comparison ──────────────────────────────────────────── */

    loadComparison: function () {
        var config = this.getConfig();
        var container = document.getElementById('xaiGlobalComparisonTable');
        if (!container) return;
        container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing comparison...</span></div>';

        var url = this.apiBase + '/comparison?top_n=' + config.topN;
        apiFetch(url).then(function (data) {
            XAIGlobal._renderComparisonTable(data);
            XAIWorkspace.renderComparisonChart(data, 'xaiGlobalComparisonChart');
            _showEl('xaiGlobalComparisonInfo');
        }).catch(function (err) {
            renderError('xaiGlobalComparisonTable', err.message);
        });
    },

    _renderComparisonTable: function (data) {
        var container = document.getElementById('xaiGlobalComparisonTable');
        if (!container) return;
        var rows = data.features || data.rows || [];
        if (rows.length === 0) { renderEmpty('xaiGlobalComparisonTable', 'No Comparison Data'); return; }

        var html = '<div class="xai-feature-table-scroll"><table class="xai-comparison-table">';
        html += '<thead><tr><th>#</th><th>Feature</th><th>NATIVE</th><th>NATIVE Rank</th><th>SHAP</th><th>SHAP Rank</th><th>PERMUTATION</th><th>PERMUTATION Rank</th><th>Avg Rank</th></tr></thead><tbody>';
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            html += '<tr><td>' + (i + 1) + '</td>';
            html += '<td class="ct-feature">' + escapeHtml(r.feature || '') + '</td>';
            html += '<td class="ct-value">' + (r.native !== null && r.native !== undefined ? formatNumber(r.native, 4) : '—') + '</td>';
            html += '<td class="ct-value">' + (r.native_rank !== null ? r.native_rank : '—') + '</td>';
            html += '<td class="ct-value">' + (r.shap !== null && r.shap !== undefined ? formatNumber(r.shap, 4) : '—') + '</td>';
            html += '<td class="ct-value">' + (r.shap_rank !== null ? r.shap_rank : '—') + '</td>';
            html += '<td class="ct-value">' + (r.permutation !== null && r.permutation !== undefined ? formatNumber(r.permutation, 4) : '—') + '</td>';
            html += '<td class="ct-value">' + (r.permutation_rank !== null ? r.permutation_rank : '—') + '</td>';
            html += '<td><strong>' + formatNumber(r.avg_rank, 1) + '</strong></td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        container.innerHTML = html;
    },
};

/* ── XAI Local Explanations (local.html) ────────────────────── */

var XAILocal = {
    modelId: null,
    apiBase: '',
    currentRow: 0,
    maxRow: 0,
    shapData: null,
    limeData: null,

    init: function (modelId) {
        this.modelId = modelId || XAIWorkspace.modelId;
        this.apiBase = '/api/xai/models/' + this.modelId + '/local';
        this.maxRow = XAIWorkspace.totalRows > 0 ? XAIWorkspace.totalRows - 1 : 999;
        this.currentRow = 0;
        // Update row hint
        var hint = document.getElementById('xaiLocalRowMax');
        if (hint) hint.textContent = 'of ' + this.maxRow;
        this.bindEvents();
        this.loadExplanation(0);
    },

    bindEvents: function () {
        var self = this;
    },

    explain: function () {
        var input = document.getElementById('xaiLocalRowIndex');
        if (input) {
            var idx = parseInt(input.value, 10);
            if (!isNaN(idx) && idx >= 0 && idx <= this.maxRow) this.loadExplanation(idx);
        }
    },

    explainRandom: function () {
        var randIdx = Math.floor(Math.random() * (this.maxRow + 1));
        this.loadExplanation(randIdx);
    },

    loadExplanation: function (rowIndex) {
        this.currentRow = rowIndex;
        var input = document.getElementById('xaiLocalRowIndex');
        if (input) input.value = rowIndex;

        // Load SHAP
        var shapChart = document.getElementById('xaiLocalShapWaterfallChart');
        if (shapChart) shapChart.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing SHAP...</span></div>';

        apiFetchWithPolling(this.apiBase + '/shap?row_index=' + rowIndex).then(function (data) {
            XAILocal.shapData = data;
            XAIWorkspace.renderSHAPLocalChart(data, 'xaiLocalShapWaterfallChart');
            // Contribution list
            var contribDiv = document.getElementById('xaiLocalShapContributions');
            if (contribDiv) {
                contribDiv.style.display = '';
                XAILocal._renderContributionList(data, 'xaiLocalShapContributions');
            }
        }).catch(function (err) {
            renderError('xaiLocalShapWaterfallChart', err.message);
        });

        // Load LIME
        var limeChart = document.getElementById('xaiLocalLimeDivergingChart');
        if (limeChart) limeChart.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing LIME...</span></div>';

        apiFetchWithPolling(this.apiBase + '/lime?row_index=' + rowIndex).then(function (data) {
            XAILocal.limeData = data;
            XAIWorkspace.renderLIMEChart(data, 'xaiLocalLimeDivergingChart');
            // LIME table
            var tableWrapper = document.getElementById('xaiLocalLimeTableWrapper');
            if (tableWrapper) {
                tableWrapper.style.display = '';
                XAILocal._renderLimeTable(data);
            }
            // Comparison
            XAILocal._renderComparison();
            // Business explanation
            var bizCard = document.getElementById('xaiLocalBusinessExplanation');
            if (bizCard) {
                bizCard.style.display = '';
                var bizContent = document.getElementById('xaiLocalBusinessContent');
                if (bizContent) bizContent.innerHTML = '<p>Prediction explained using SHAP and LIME for observation at row ' + rowIndex + '.</p>';
            }
        }).catch(function (err) {
            renderError('xaiLocalLimeDivergingChart', err.message);
        });
    },

    _renderContributionList: function (data, containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var features = data.features || [];
        var values = data.values || [];
        if (features.length === 0 || values.length === 0) { el.innerHTML = ''; return; }

        var items = [];
        var count = Math.min(features.length, values.length);
        for (var i = 0; i < count; i++) {
            items.push({ name: features[i], value: values[i] || 0 });
        }
        items.sort(function (a, b) { return Math.abs(b.value) - Math.abs(a.value); });
        var maxAbs = 0;
        for (var j = 0; j < items.length; j++) { if (Math.abs(items[j].value) > maxAbs) maxAbs = Math.abs(items[j].value); }
        if (maxAbs === 0) maxAbs = 1;

        var posItems = items.filter(function (it) { return it.value >= 0; }).slice(0, 5);
        var negItems = items.filter(function (it) { return it.value < 0; }).slice(0, 5);

        var html = '';
        for (var p = 0; p < posItems.length; p++) {
            var pct = (Math.abs(posItems[p].value) / maxAbs) * 100;
            html += '<div class="xai-contribution-item xai-contribution-positive"><div class="xai-contribution-bar-track"><div class="xai-contribution-bar" style="width:' + pct + '%;"></div></div><div class="xai-contribution-feature" title="' + escapeHtml(posItems[p].name) + '">' + escapeHtml(posItems[p].name) + '</div><div class="xai-contribution-value">+' + formatNumber(posItems[p].value, 4) + '</div></div>';
        }
        for (var n = 0; n < negItems.length; n++) {
            var pctN = (Math.abs(negItems[n].value) / maxAbs) * 100;
            html += '<div class="xai-contribution-item xai-contribution-negative"><div class="xai-contribution-bar-track"><div class="xai-contribution-bar" style="width:' + pctN + '%;"></div></div><div class="xai-contribution-feature" title="' + escapeHtml(negItems[n].name) + '">' + escapeHtml(negItems[n].name) + '</div><div class="xai-contribution-value">' + formatNumber(negItems[n].value, 4) + '</div></div>';
        }
        el.innerHTML = html;
    },

    _renderLimeTable: function (data) {
        var tbody = document.getElementById('xaiLocalLimeTableBody');
        if (!tbody) return;
        var features = data.features || [];
        var values = data.values || [];
        var conditions = data.conditions || [];
        var count = Math.min(features.length, values.length);
        var html = '';
        for (var i = 0; i < count; i++) {
            var sign = values[i] >= 0 ? '+' : '';
            html += '<tr><td>' + escapeHtml(features[i]) + '</td><td>' + escapeHtml(conditions[i] || features[i]) + '</td><td style="color:' + (values[i] >= 0 ? XAI_COLORS.positive : XAI_COLORS.negative) + ';font-weight:600;">' + sign + formatNumber(values[i], 4) + '</td></tr>';
        }
        tbody.innerHTML = html;
    },

    _renderComparison: function () {
        var container = document.getElementById('xaiLocalComparison');
        if (!container) return;
        if (!this.shapData && !this.limeData) {
            container.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Waiting for explanations...</span></div>';
            return;
        }
        var shapFeatures = (this.shapData && this.shapData.features) ? this.shapData.features : [];
        var shapValues = (this.shapData && this.shapData.values) ? this.shapData.values : [];
        var limeFeatures = (this.limeData && this.limeData.features) ? this.limeData.features : [];
        var limeValues = (this.limeData && this.limeData.values) ? this.limeData.values : [];

        if (limeFeatures.length > 0 && Array.isArray(limeFeatures[0])) {
            limeFeatures = limeFeatures.map(function (f) { return String(f[1] || ''); });
            limeValues = (this.limeData && this.limeData.features) ? this.limeData.features.map(function (f) { return f[0] || 0; }) : [];
        }

        var allFeatures = shapFeatures.concat(limeFeatures).filter(function (v, i, a) { return a.indexOf(v) === i; });
        if (allFeatures.length === 0) { container.style.display = 'none'; return; }
        container.style.display = '';

        var html = '<div class="xai-feature-table-scroll" style="max-height:400px;overflow:auto;"><table class="xai-comparison-table">';
        html += '<thead><tr><th>Feature</th><th style="color:' + XAI_COLORS.shap + '">SHAP</th><th style="color:' + XAI_COLORS.lime + '">LIME</th><th>Agreement</th></tr></thead><tbody>';
        for (var i = 0; i < allFeatures.length; i++) {
            var fname = allFeatures[i];
            var sIdx = shapFeatures.indexOf(fname);
            var lIdx = limeFeatures.indexOf(fname);
            var sVal = sIdx >= 0 ? (shapValues[sIdx] || 0) : 0;
            var lVal = lIdx >= 0 ? (limeValues[lIdx] || 0) : 0;
            var agrees = (sVal >= 0 && lVal >= 0) || (sVal < 0 && lVal < 0);
            html += '<tr><td class="ct-feature">' + escapeHtml(fname) + '</td>';
            html += '<td class="ct-value">' + (sIdx >= 0 ? formatNumber(sVal, 4) : '—') + '</td>';
            html += '<td class="ct-value">' + (lIdx >= 0 ? formatNumber(lVal, 4) : '—') + '</td>';
            html += '<td>' + (sIdx >= 0 && lIdx >= 0 ? (agrees ? '<span style="color:' + XAI_COLORS.positive + '">Agree</span>' : '<span style="color:' + XAI_COLORS.negative + '">Disagree</span>') : '—') + '</td></tr>';
        }
        html += '</tbody></table></div>';
        container.innerHTML = html;
    },
};

/* ── XAI Prediction (prediction.html) ───────────────────────── */

var XAIPrediction = {
    modelId: null,
    apiBase: '',
    currentRow: 0,
    maxRow: 0,

    init: function (modelId) {
        this.modelId = modelId || XAIWorkspace.modelId;
        this.apiBase = '/api/xai/models/' + this.modelId + '/predict';
        this.maxRow = XAIWorkspace.totalRows > 0 ? XAIWorkspace.totalRows - 1 : 999;
        this.currentRow = 0;
        var hint = document.getElementById('xaiPredRowMax');
        if (hint) hint.textContent = 'of ' + this.maxRow;
        this.bindEvents();
        this.loadPrediction(0);
    },

    bindEvents: function () {},

    predictAndExplain: function () {
        var input = document.getElementById('xaiPredRowIndex');
        if (input) {
            var idx = parseInt(input.value, 10);
            if (!isNaN(idx) && idx >= 0 && idx <= this.maxRow) this.loadPrediction(idx);
        }
    },

    predictRandom: function () {
        var randIdx = Math.floor(Math.random() * (this.maxRow + 1));
        this.loadPrediction(randIdx);
    },

    loadPrediction: function (rowIndex) {
        this.currentRow = rowIndex;
        var input = document.getElementById('xaiPredRowIndex');
        if (input) input.value = rowIndex;

        var contentEl = document.getElementById('xaiPredDisplayContent');
        if (contentEl) contentEl.innerHTML = '<div class="xai-loading"><div class="xai-loading-spinner"></div><span>Computing prediction...</span></div>';

        var url = this.apiBase + '?row_index=' + rowIndex;
        apiFetchWithPolling(url).then(function (data) {
            XAIPrediction._renderPredictionCard(data);
            XAIPrediction._renderFeatureValues(data);
            XAIPrediction._renderTopContributors(data);
            XAIPrediction._renderBusinessExplanation(data);
            XAIPrediction._renderModelContext(data);
            XAIPrediction._renderCaveats(data);
        }).catch(function (err) {
            renderError('xaiPredDisplayContent', err.message || 'Failed to load prediction.');
        });
    },

    _renderPredictionCard: function (data) {
        var el = document.getElementById('xaiPredDisplayContent');
        if (!el) return;

        var prediction = data.predicted_class || data.prediction || '—';
        var actual = data.actual;
        var probabilities = data.probabilities || null;
        var problemType = data.task_type || 'classification';

        var html = '<div style="text-align:center;padding:1rem;">';
        html += '<div style="font-size:0.85rem;color:#6B7280;margin-bottom:0.5rem;">Predicted Value</div>';
        html += '<div style="font-size:2.5rem;font-weight:700;color:' + XAI_COLORS.primary + ';">' + escapeHtml(String(prediction)) + '</div>';
        if (probabilities && problemType === 'classification') {
            var topProb = Object.entries(probabilities).sort(function (a, b) { return b[1] - a[1]; })[0];
            if (topProb) html += '<div style="font-size:0.9rem;color:#475569;margin-top:0.5rem;">Confidence: ' + formatPercent(topProb[1]) + '</div>';
        }
        if (actual !== null && actual !== undefined) {
            var isCorrect = String(actual) === String(prediction);
            html += '<div style="font-size:0.88rem;margin-top:0.5rem;color:' + (isCorrect ? '#059669' : '#DC2626') + ';font-weight:600;">Actual: ' + escapeHtml(String(actual)) + ' (' + (isCorrect ? 'Correct' : 'Incorrect') + ')</div>';
        }
        html += '<div style="font-size:0.78rem;color:#94A3B8;margin-top:0.5rem;">Row ' + XAIPrediction.currentRow + '</div>';
        html += '</div>';

        if (probabilities && problemType === 'classification') {
            html += '<div style="margin-top:1rem;padding:0 1rem;"><div style="font-weight:600;font-size:0.85rem;color:#475569;margin-bottom:0.5rem;">Class Probabilities</div><div id="xaiPredProbBars"></div></div>';
        }

        el.innerHTML = html;
        if (probabilities && problemType === 'classification') {
            XAIWorkspace.renderProbabilityBars(probabilities, 'xaiPredProbBars');
        }
    },

    _renderFeatureValues: function (data) {
        var el = document.getElementById('xaiPredFeatureTable');
        if (!el) return;
        var features = data.feature_values || [];
        if (features.length === 0) { el.innerHTML = '<div class="xai-empty"><p>No feature values available.</p></div>'; return; }

        var html = '<div class="xai-feature-table-scroll"><table class="xai-feature-table">';
        html += '<thead><tr><th>Feature</th><th>Value</th></tr></thead><tbody>';
        for (var i = 0; i < features.length; i++) {
            var f = features[i];
            var name = f.feature || f.name || ('Feature ' + (i + 1));
            var val = f.value !== undefined ? f.value : '—';
            var displayVal = typeof val === 'number' ? formatNumber(val, 4) : escapeHtml(String(val));
            html += '<tr><td class="ft-name">' + escapeHtml(name) + '</td><td class="ft-value">' + displayVal + '</td></tr>';
        }
        html += '</tbody></table></div>';
        el.innerHTML = html;
    },

    _renderTopContributors: function (data) {
        var el = document.getElementById('xaiPredContributingContent');
        if (!el) return;
        var contributors = data.contributors || [];
        if (contributors.length === 0) { el.innerHTML = '<div class="xai-empty"><p>No contribution data.</p></div>'; return; }

        var items = contributors.slice(0, 10);
        var maxAbs = 0;
        for (var i = 0; i < items.length; i++) { if (Math.abs(items[i].shap_value || items[i].contribution || 0) > maxAbs) maxAbs = Math.abs(items[i].shap_value || items[i].contribution || 0); }
        if (maxAbs === 0) maxAbs = 1;

        var html = '<div class="xai-contribution-list">';
        for (var j = 0; j < items.length; j++) {
            var c = items[j];
            var val = c.shap_value || c.contribution || 0;
            var isPositive = val >= 0;
            var pct = (Math.abs(val) / maxAbs) * 100;
            var sign = isPositive ? '+' : '';
            var cls = isPositive ? 'xai-contribution-positive' : 'xai-contribution-negative';
            html += '<div class="xai-contribution-item ' + cls + '"><div class="xai-contribution-bar-track"><div class="xai-contribution-bar" style="width:' + pct + '%;"></div></div><div class="xai-contribution-feature" title="' + escapeHtml(c.feature) + '">' + escapeHtml(c.feature) + '</div><div class="xai-contribution-value">' + sign + formatNumber(val, 4) + '</div></div>';
        }
        html += '</div>';
        el.innerHTML = html;
    },

    _renderBusinessExplanation: function (data) {
        var card = document.getElementById('xaiPredBusinessCard');
        if (!card) return;
        card.style.display = '';
        var content = document.getElementById('xaiPredBusinessContent');
        if (!content) return;
        var text = data.business_explanation || 'This prediction is explained through SHAP values showing feature contributions.';
        content.innerHTML = '<p>' + text + '</p>';
    },

    _renderModelContext: function (data) {
        var card = document.getElementById('xaiPredModelContextCard');
        if (!card) return;
        card.style.display = '';
        var content = document.getElementById('xaiPredModelContextContent');
        if (!content) return;
        var metrics = data.metrics || {};
        if (Object.keys(metrics).length === 0) { card.style.display = 'none'; return; }

        var html = '<div class="xai-stat-grid">';
        for (var key in metrics) {
            if (metrics.hasOwnProperty(key)) {
                html += '<div class="xai-stat-item"><div class="xai-metric-label">' + escapeHtml(key) + '</div><div class="xai-metric-value">' + formatNumber(metrics[key], 4) + '</div></div>';
            }
        }
        html += '</div>';
        content.innerHTML = html;
    },

    _renderCaveats: function (data) {
        var card = document.getElementById('xaiPredCaveatsCard');
        if (!card) return;
        var caveats = data.caveats || [];
        if (caveats.length === 0) { card.style.display = 'none'; return; }
        card.style.display = '';
        var content = document.getElementById('xaiPredCaveatsContent');
        if (!content) return;
        var html = '<ul style="list-style:disc;padding-left:1.25rem;margin:0;">';
        for (var i = 0; i < caveats.length; i++) {
            html += '<li style="margin-bottom:0.35rem;font-size:0.85rem;color:#475569;">' + escapeHtml(caveats[i]) + '</li>';
        }
        html += '</ul>';
        content.innerHTML = html;
    },
};

/* ── Initialization ────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', function () {
    // Model selection page (index.html)
    if (document.getElementById('xaiModelsGrid')) {
        XAIService.init();
        return;
    }

    // Workspace page (workspace.html) - detected by xai-workspace class
    if (document.querySelector('.xai-workspace')) {
        var modelId = window.MODEL_ID || null;
        if (modelId) XAIWorkspace.init(modelId);
        return;
    }

    // Global page (global.html)
    if (document.querySelector('.xai-global-page')) {
        var gModelId = window.MODEL_ID || null;
        if (gModelId) {
            // Need to load summary first for totalRows, then init
            apiFetch('/api/xai/models/' + gModelId + '/summary').then(function (summaryData) {
                XAIWorkspace.modelInfo = summaryData;
                XAIWorkspace.totalRows = summaryData.total_rows || summaryData.n_samples || 0;
                XAIGlobal.modelId = gModelId;
                XAIGlobal.apiBase = '/api/xai/models/' + gModelId + '/global';
                XAIGlobal.initialized = false;
                XAIGlobal.init(gModelId);
            }).catch(function (err) {
                renderError('xaiGlobalPageError', err.message);
            });
        }
        return;
    }

    // Local page (local.html)
    if (document.querySelector('.xai-local-page')) {
        var lModelId = window.MODEL_ID || null;
        if (lModelId) {
            apiFetch('/api/xai/models/' + lModelId + '/summary').then(function (summaryData) {
                XAIWorkspace.modelInfo = summaryData;
                XAIWorkspace.totalRows = summaryData.total_rows || summaryData.n_samples || 0;
                XAILocal.modelId = lModelId;
                XAILocal.apiBase = '/api/xai/models/' + lModelId + '/local';
                XAILocal.init(lModelId);
            }).catch(function (err) {
                renderError('xaiLocalPageError', err.message);
            });
        }
        return;
    }

    // Prediction page (prediction.html)
    if (document.querySelector('.xai-prediction-page')) {
        var pModelId = window.MODEL_ID || null;
        if (pModelId) {
            apiFetch('/api/xai/models/' + pModelId + '/summary').then(function (summaryData) {
                XAIWorkspace.modelInfo = summaryData;
                XAIWorkspace.totalRows = summaryData.total_rows || summaryData.n_samples || 0;
                XAIPrediction.modelId = pModelId;
                XAIPrediction.apiBase = '/api/xai/models/' + pModelId + '/predict';
                XAIPrediction.init(pModelId);
            }).catch(function (err) {
                renderError('xaiPredPageError', err.message);
            });
        }
        return;
    }
});

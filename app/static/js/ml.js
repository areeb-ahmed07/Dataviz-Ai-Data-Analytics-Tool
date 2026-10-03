/**
 * DataViz Pro — ML Studio JavaScript
 * Handles the full ML pipeline: target selection, feature selection,
 * preprocessing, training, comparison, and results visualization.
 */

// ── Dataset ID extraction from URL ───────────────────────────────────
// URL pattern: /datasets/<id>/ml
// The template also supports server-injected DATASET_ID.
const DATASET_ID = (function () {
    if (typeof window.DATASET_ID !== 'undefined' && window.DATASET_ID) return window.DATASET_ID;
    const match = window.location.pathname.match(/\/datasets\/([0-9a-f\-]+)\/ml/);
    return match ? match[1] : null;
})();

// CSRF token helper
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return null;
}

const MLStudio = {
    datasetId: DATASET_ID,
    apiBase: `/api/datasets/${DATASET_ID}/ml`,
    modelsApiBase: '/api/models',

    // State
    currentStep: 0,
    totalSteps: 7,
    datasetInfo: null,
    targetAnalysis: null,
    selectedFeatures: [],
    selectedAlgorithms: [],
    isTraining: false,
    trainResults: null,
    currentResults: null,
    prepareInfo: null,
    sortColumn: 'rank',
    sortDir: 'asc',

    stepNames: ['target', 'features', 'problem', 'preprocess', 'train', 'compare', 'results'],

    // ── Initialization ───────────────────────────────────────

    async init() {
        if (!this.datasetId) {
            this.showError('mlError', 'Invalid dataset ID. Please navigate from a dataset page.');
            return;
        }
        this.updateStepUI(0);
        this.bindEvents();
        await this.loadDatasetInfo();
        await this.loadAlgorithms();
        await this.loadExistingResults();
        await this.restoreWorkspace();
        const job = sessionStorage.getItem(`training:${this.datasetId}`);
        if (job) {
            this.isTraining = true;
            this.pollTrainingStatus(job, document.getElementById('mlTrainBtn'), document.getElementById('mlTrainStatus'));
        }
    },

    bindEvents() {
        // Step navigation buttons
        document.querySelectorAll('[data-goto-step]').forEach(btn => {
            btn.addEventListener('click', () => {
                const step = parseInt(btn.dataset.gotoStep, 10);
                this.goToStep(step);
            });
        });

        // Step bar clicks
        document.querySelectorAll('.ml-step-item').forEach(item => {
            item.addEventListener('click', () => {
                const step = parseInt(item.dataset.step, 10);
                this.goToStep(step);
            });
        });

        // Next / Previous buttons
        const btnNext = document.getElementById('mlBtnNext');
        const btnPrev = document.getElementById('mlBtnPrev');
        if (btnNext) btnNext.addEventListener('click', () => this.nextStep());
        if (btnPrev) btnPrev.addEventListener('click', () => this.prevStep());

        // Target column dropdown
        const targetSelect = document.getElementById('targetColumn');
        if (targetSelect) {
            targetSelect.addEventListener('change', () => this.analyzeTarget());
        }

        // Feature selection controls
        const selectAllBtn = document.getElementById('mlSelectAllFeatures');
        const clearAllBtn = document.getElementById('mlClearAllFeatures');
        if (selectAllBtn) selectAllBtn.addEventListener('click', () => this.toggleAllFeatures(true));
        if (clearAllBtn) clearAllBtn.addEventListener('click', () => this.toggleAllFeatures(false));

        // AutoML toggle
        const automlToggle = document.getElementById('mlAutoMLToggle');
        if (automlToggle) {
            automlToggle.addEventListener('change', () => this.onAutoMLToggle());
        }

        // Preprocessing test size slider label
        const testSizeSlider = document.getElementById('mlTestSize');
        const testSizeLabel = document.getElementById('mlTestSizeLabel');
        if (testSizeSlider && testSizeLabel) {
            testSizeSlider.addEventListener('input', () => {
                testSizeLabel.textContent = Math.round(parseFloat(testSizeSlider.value) * 100) + '%';
            });
        }

        // Train button
        const trainBtn = document.getElementById('mlTrainBtn');
        if (trainBtn) trainBtn.addEventListener('click', () => this.startTraining());

        // Prepare button
        const prepareBtn = document.getElementById('mlPrepareBtn');
        if (prepareBtn) prepareBtn.addEventListener('click', () => this.prepareData());

        // Configure button
        const configBtn = document.getElementById('mlConfigureBtn');
        if (configBtn) configBtn.addEventListener('click', () => this.saveConfiguration());

        // Optimize button
        const optimizeBtn = document.getElementById('mlOptimizeBtn');
        if (optimizeBtn) optimizeBtn.addEventListener('click', () => this.runOptimization());

        // Save model button
        const saveModelBtn = document.getElementById('mlSaveModelBtn');
        if (saveModelBtn) saveModelBtn.addEventListener('click', () => this.showSaveModelDialog());

        // Confirm save model
        const confirmSaveModelBtn = document.getElementById('mlConfirmSaveModelBtn');
        if (confirmSaveModelBtn) confirmSaveModelBtn.addEventListener('click', () => this.saveModel());

        // Clear results button
        const clearBtn = document.getElementById('mlClearBtn');
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearResults());

        // Leaderboard sort
        document.querySelectorAll('[data-sort-column]').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sortColumn;
                if (this.sortColumn === col) {
                    this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.sortColumn = col;
                    this.sortDir = 'desc';
                }
                this.renderLeaderboard();
            });
        });

        // Model management (models list page)
        this.bindModelManagementEvents();
    },

    bindModelManagementEvents() {
        document.querySelectorAll('[data-model-delete]').forEach(btn => {
            btn.addEventListener('click', () => {
                const modelId = btn.dataset.modelDelete;
                this.confirmAction('Delete Model?', 'This model will be permanently deleted.', () => {
                    this.deleteModel(modelId);
                });
            });
        });

        document.querySelectorAll('[data-model-download]').forEach(btn => {
            btn.addEventListener('click', () => {
                const modelId = btn.dataset.modelDownload;
                this.downloadModel(modelId);
            });
        });

        document.querySelectorAll('[data-model-view]').forEach(btn => {
            btn.addEventListener('click', () => {
                const modelId = btn.dataset.modelView;
                this.viewModel(modelId);
            });
        });
    },

    // ── Step Navigation ───────────────────────────────────────

    goToStep(step) {
        if (step < 0 || step >= this.totalSteps) return;
        // Validate before advancing past certain steps
        if (step > this.currentStep) {
            for (let s = this.currentStep; s < step; s++) {
                if (!this.validateStep(s)) return;
            }
        }
        this.currentStep = step;
        this.updateStepUI(step);
        this.onStepEnter(step);
    },

    nextStep() {
        if (this.currentStep < this.totalSteps - 1) {
            this.goToStep(this.currentStep + 1);
        }
    },

    prevStep() {
        if (this.currentStep > 0) {
            this.goToStep(this.currentStep - 1);
        }
    },

    validateStep(step) {
        switch (this.stepNames[step]) {
            case 'target': {
                const val = document.getElementById('targetColumn')?.value;
                const problemType = document.getElementById('problemType')?.value;
                if (!val && problemType !== 'clustering') {
                    this.showError('targetError', 'Please select a target column.');
                    return false;
                }
                this.clearError('targetError');
                return true;
            }
            case 'features': {
                const checked = document.querySelectorAll('.ml-feature-check:checked');
                if (checked.length === 0) {
                    this.showError('featuresError', 'Please select at least one feature.');
                    return false;
                }
                this.clearError('featuresError');
                return true;
            }
            case 'problem': {
                const val = document.getElementById('problemType')?.value;
                if (!val) {
                    this.showError('problemError', 'Please select or confirm a problem type.');
                    return false;
                }
                this.clearError('problemError');
                return true;
            }
            default:
                return true;
        }
    },

    updateStepUI(step) {
        // Step bar items
        document.querySelectorAll('.ml-step-item').forEach((item, i) => {
            item.classList.remove('active', 'completed');
            if (i < step) item.classList.add('completed');
            if (i === step) item.classList.add('active');
        });

        // Step panels
        document.querySelectorAll('.ml-step-panel').forEach((panel, i) => {
            panel.style.display = i === step ? 'block' : 'none';
        });

        // Nav buttons
        const prevBtn = document.getElementById('mlBtnPrev');
        const nextBtn = document.getElementById('mlBtnNext');
        if (prevBtn) prevBtn.style.display = step > 0 ? '' : 'none';
        if (nextBtn) nextBtn.style.display = step < this.totalSteps - 1 ? '' : 'none';
    },

    onStepEnter(step) {
        const name = this.stepNames[step];
        if (name === 'compare' && this.trainResults) {
            this.renderLeaderboard();
        }
        if (name === 'results') {
            this.loadResultsDashboard();
        }
        if (name === 'features') {
            this.updateFeatureTypeInfo();
        }
        if (name === 'problem') {
            // Show/hide clustering config if problem type is clustering
            const pt = document.getElementById('problemType');
            if (pt) {
                const cc = document.getElementById('mlClusteringConfig');
                if (cc) cc.style.display = pt.value === 'clustering' ? '' : 'none';
            }
        }
    },

    // ── Dataset Info Loading ───────────────────────────────────

    async loadDatasetInfo() {
        try {
            const resp = await fetch(`${this.apiBase}/info`);
            const data = await resp.json();

            if (data.error) {
                this.showError('mlError', data.error);
                return;
            }

            this.datasetInfo = data;
            this.renderDatasetInfo(data);
            this.populateTargetDropdown(data);
            this.populateFeatureList(data);
        } catch (e) {
            this.showError('mlError', 'Failed to load dataset info. Please try again.');
        }
    },

    renderDatasetInfo(data) {
        const el = document.getElementById('mlDatasetInfo');
        if (!el) return;
        el.textContent = `${(data.rows || 0).toLocaleString()} rows \u2022 ${data.columns || 0} columns`;

        const detailEl = document.getElementById('mlDatasetDetail');
        if (detailEl) {
            const numericCount = (data.column_types || []).filter(c => c.inferred_type === 'numeric').length;
            const catCount = (data.column_types || []).filter(c => c.inferred_type === 'categorical').length;
            const missingCount = data.missing_cells || 0;
            detailEl.textContent = `${numericCount} numeric \u2022 ${catCount} categorical \u2022 ${missingCount.toLocaleString()} missing values`;
        }
    },

    // ── Target Selection ───────────────────────────────────

    populateTargetDropdown(data) {
        const select = document.getElementById('targetColumn');
        if (!select) return;

        const cols = data.column_types || [];
        select.innerHTML = '<option value="">-- Select Target --</option>';

        for (const col of cols) {
            const opt = document.createElement('option');
            opt.value = col.name;
            opt.textContent = `${col.name} (${col.inferred_type})`;
            select.appendChild(opt);
        }
    },

    async analyzeTarget() {
        const column = document.getElementById('targetColumn')?.value;
        const container = document.getElementById('mlTargetAnalysis');
        const card = document.getElementById('mlTargetAnalysisCard');
        if (!container) return;

        if (!column) {
            container.innerHTML = '';
            if (card) card.style.display = 'none';
            this.targetAnalysis = null;
            return;
        }

        if (card) card.style.display = 'block';
        container.innerHTML = '<div class="ml-loading"><div class="ml-loading-spinner"></div> Analyzing target column…</div>';
        this.clearError('targetError');

        try {
            const resp = await fetch(`${this.apiBase}/target?column=${encodeURIComponent(column)}`);
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.targetAnalysis = data;
            this.renderTargetAnalysis(data);

            // Auto-detect problem type — service now returns suggested_problem_type
            const suggested = data.suggested_problem_type || data.suggested_problem;
            if (suggested) {
                const problemSelect = document.getElementById('problemType');
                if (problemSelect && !problemSelect.dataset.userSet) {
                    problemSelect.value = suggested;
                    this.renderProblemTypeInfo(suggested);
                }
            }

            // Update algorithm recommendations
            await this.loadAlgorithms();
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Failed to analyze target. Please try again.</div>';
        }
    },

    renderTargetAnalysis(data) {
        const container = document.getElementById('mlTargetAnalysis');
        if (!container) return;

        let html = '<div class="ml-analysis-card">';

        // Type info
        html += '<div class="ml-analysis-row">';
        html += '<span class="ml-analysis-label">Data Type:</span>';
        html += `<span class="dtype-badge">${this.escapeHtml(data.dtype || 'unknown')}</span>`;
        html += '</div>';

        // Unique count
        html += '<div class="ml-analysis-row">';
        html += '<span class="ml-analysis-label">Unique Values:</span>';
        html += `<span>${(data.unique_count || 0).toLocaleString()}</span>`;
        html += '</div>';

        // Missing
        html += '<div class="ml-analysis-row">';
        html += '<span class="ml-analysis-label">Missing:</span>';
        const missingPct = data.missing_percentage || 0;
        const missingClass = missingPct > 10 ? 'worsened' : missingPct > 0 ? 'ml-warning-text' : 'improved';
        html += `<span class="${missingClass}">${(data.missing_count || 0).toLocaleString()} (${missingPct}%)</span>`;
        html += '</div>';

        // Warnings
        if (data.warnings && data.warnings.length > 0) {
            html += '<div class="ml-warnings">';
            for (const w of data.warnings) {
                html += `<div class="warning-text" style="margin-bottom:0.25rem;">${this.escapeHtml(w)}</div>`;
            }
            html += '</div>';
        }

        // Class distribution (for classification)
        if (data.distribution) {
            html += '<div class="ml-distribution">';
            html += '<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.5rem;">Class Distribution</div>';

            const entries = Object.entries(data.distribution);
            const maxCount = Math.max(...entries.map(([, v]) => v));

            html += '<div class="ml-dist-bars">';
            for (const [label, count] of entries) {
                const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                html += '<div class="ml-dist-row">';
                html += `<span class="ml-dist-label" title="${this.escapeHtml(label)}">${this.escapeHtml(String(label))}</span>`;
                html += `<div class="ml-dist-bar-wrap"><div class="ml-dist-bar" style="width:${pct}%;"></div></div>`;
                html += `<span class="ml-dist-count">${count.toLocaleString()}</span>`;
                html += '</div>';
            }
            html += '</div></div>';
        }

        // Stats for numeric targets
        if (data.statistics) {
            html += '<div style="margin-top:0.75rem;">';
            html += '<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.5rem;">Target Statistics</div>';
            html += '<div class="ml-stats-grid">';
            const stats = data.statistics;
            const statItems = ['mean', 'median', 'std', 'min', 'max'];
            for (const key of statItems) {
                if (stats[key] !== undefined) {
                    html += `<div class="ml-stat-item"><span class="ml-stat-label">${key.charAt(0).toUpperCase() + key.slice(1)}</span><span class="ml-stat-value">${typeof stats[key] === 'number' ? stats[key].toLocaleString(undefined, {maximumFractionDigits: 4}) : stats[key]}</span></div>`;
                }
            }
            html += '</div></div>';
        }

        html += '</div>';
        container.innerHTML = html;
    },

    // ── Feature Selection ───────────────────────────────────

    populateFeatureList(data) {
        const container = document.getElementById('mlFeatureList');
        if (!container) return;

        const cols = data.column_types || [];
        if (cols.length === 0) {
            container.innerHTML = '<div class="info-text">No columns available.</div>';
            return;
        }

        let html = '';
        const numericCols = cols.filter(c => c.inferred_type === 'numeric');
        const catCols = cols.filter(c => c.inferred_type === 'categorical');
        const otherCols = cols.filter(c => c.inferred_type !== 'numeric' && c.inferred_type !== 'categorical');

        if (numericCols.length > 0) {
            html += '<div class="ml-feature-group">';
            html += '<div class="ml-feature-group-title">Numeric</div>';
            for (const c of numericCols) {
                html += `<label class="checkbox-row ml-feature-row">`;
                html += `<input type="checkbox" class="ml-feature-check" value="${this.escapeHtml(c.name)}" data-type="numeric" checked>`;
                html += `${this.escapeHtml(c.name)}`;
                html += `<span class="dtype-badge" style="font-size:0.7rem;">${c.inferred_type}</span>`;
                if (c.missing_count > 0) {
                    html += `<span style="color:#D97706;font-size:0.7rem;">${c.missing_count} missing</span>`;
                }
                html += '</label>';
            }
            html += '</div>';
        }

        if (catCols.length > 0) {
            html += '<div class="ml-feature-group">';
            html += '<div class="ml-feature-group-title">Categorical</div>';
            for (const c of catCols) {
                const highCard = c.unique_count > 20;
                html += `<label class="checkbox-row ml-feature-row">`;
                html += `<input type="checkbox" class="ml-feature-check" value="${this.escapeHtml(c.name)}" data-type="categorical" ${!highCard ? 'checked' : ''}>`;
                html += `${this.escapeHtml(c.name)}`;
                html += `<span class="dtype-badge" style="font-size:0.7rem;">${c.inferred_type}</span>`;
                html += `<span style="color:#9CA3AF;font-size:0.7rem;">${c.unique_count} unique</span>`;
                if (highCard) {
                    html += '<span style="color:#D97706;font-size:0.7rem;">high card.</span>';
                }
                html += '</label>';
            }
            html += '</div>';
        }

        if (otherCols.length > 0) {
            html += '<div class="ml-feature-group">';
            html += '<div class="ml-feature-group-title">Other</div>';
            for (const c of otherCols) {
                html += `<label class="checkbox-row ml-feature-row">`;
                html += `<input type="checkbox" class="ml-feature-check" value="${this.escapeHtml(c.name)}" data-type="${c.inferred_type}">`;
                html += `${this.escapeHtml(c.name)}`;
                html += `<span class="dtype-badge" style="font-size:0.7rem;">${c.inferred_type || 'other'}</span>`;
                html += '</label>';
            }
            html += '</div>';
        }

        container.innerHTML = html;

        // Bind feature checkbox events
        container.querySelectorAll('.ml-feature-check').forEach(cb => {
            cb.addEventListener('change', () => this.updateFeatureTypeInfo());
        });
    },

    toggleAllFeatures(checked) {
        document.querySelectorAll('.ml-feature-check').forEach(cb => {
            cb.checked = checked;
        });
        this.updateFeatureTypeInfo();
    },

    getSelectedFeatures() {
        return Array.from(document.querySelectorAll('.ml-feature-check:checked')).map(cb => cb.value);
    },

    updateFeatureTypeInfo() {
        const features = this.getSelectedFeatures();
        this.selectedFeatures = features;

        const infoEl = document.getElementById('mlFeatureInfo');
        if (!infoEl) return;

        const allFeatures = Array.from(document.querySelectorAll('.ml-feature-check'));
        const numericSelected = allFeatures.filter(cb => cb.checked && cb.dataset.type === 'numeric').length;
        const catSelected = allFeatures.filter(cb => cb.checked && cb.dataset.type === 'categorical').length;

        infoEl.innerHTML = `<strong>${features.length}</strong> selected \u2022 ${numericSelected} numeric \u2022 ${catSelected} categorical \u2022 ${allFeatures.length - features.length} excluded`;

        this.clearError('featuresError');
    },

    // ── Problem Type Detection ───────────────────────────────────

    setupProblemTypeUI() {
        const problemSelect = document.getElementById('problemType');
        if (!problemSelect) return;

        problemSelect.addEventListener('change', () => {
            problemSelect.dataset.userSet = 'true';
            const val = problemSelect.value;
            this.renderProblemTypeInfo(val);
            this.loadAlgorithms();
        });

        // Clustering note
        const clusteringNote = document.getElementById('mlClusteringNote');
        if (clusteringNote) {
            problemSelect.addEventListener('change', () => {
                clusteringNote.style.display = problemSelect.value === 'clustering' ? 'block' : 'none';

                // Show/hide target requirement
                const targetSection = document.getElementById('mlTargetRequired');
                if (targetSection) {
                    targetSection.style.display = problemSelect.value === 'clustering' ? 'none' : '';
                }
            });
        }
    },

    renderProblemTypeInfo(type) {
        const infoEl = document.getElementById('mlProblemTypeInfo');
        if (!infoEl) return;

        const descriptions = {
            classification: 'Predict discrete class labels. Suitable for categorical targets.',
            regression: 'Predict continuous numeric values. Suitable for numeric targets.',
            clustering: 'Group similar data points. No target column needed.',
        };

        const icons = {
            classification: '\uD83C\uDFF7\uFE0F',
            regression: '\uD83D\uDCC8',
            clustering: '\uD83D\uDD17',
        };

        if (!type) {
            infoEl.innerHTML = '';
            return;
        }

        let html = '<div class="ml-analysis-card">';
        html += `<div class="ml-analysis-row"><span class="ml-analysis-label">Type:</span><span><strong>${icons[type] || ''} ${type.charAt(0).toUpperCase() + type.slice(1)}</strong></span></div>`;
        html += `<div style="font-size:0.82rem;color:#6B7280;margin-top:0.25rem;">${descriptions[type] || ''}</div>`;

        if (type === 'classification' && this.targetAnalysis) {
            const nClasses = Object.keys(this.targetAnalysis.distribution || {}).length;
            if (nClasses === 2) {
                html += '<div style="margin-top:0.5rem;font-size:0.82rem;color:#059669;">Binary classification detected.</div>';
            } else if (nClasses > 2) {
                html += `<div style="margin-top:0.5rem;font-size:0.82rem;color:#6366F1;">Multi-class classification (${nClasses} classes).</div>`;
            }
        }

        html += '</div>';
        infoEl.innerHTML = html;
    },

    // ── Algorithm Selection ───────────────────────────────────

    async loadAlgorithms() {
        const container = document.getElementById('mlAlgorithmList');
        if (!container) return;

        const taskType = document.getElementById('problemType')?.value || 'classification';
        const targetColumn = document.getElementById('targetColumn')?.value || '';

        try {
            let url = `${this.apiBase}/algorithms?task_type=${encodeURIComponent(taskType)}`;
            if (targetColumn) url += `&target_column=${encodeURIComponent(targetColumn)}`;

            const resp = await fetch(url);
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.renderAlgorithms(data);
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Failed to load algorithms.</div>';
        }
    },

    renderAlgorithms(data) {
        const container = document.getElementById('mlAlgorithmList');
        if (!container) return;

        const algorithms = data.algorithms || [];
        const recommendations = data.recommendations || [];

        if (algorithms.length === 0) {
            container.innerHTML = '<div class="info-text">No algorithms available for this problem type.</div>';
            return;
        }

        let html = '';

        // Show recommendations if available
        if (recommendations.length > 0) {
            html += '<div class="ml-recommendations">';
            html += '<div style="font-weight:600;font-size:0.82rem;margin-bottom:0.5rem;color:#6366F1;">Recommended</div>';
            for (const rec of recommendations) {
                html += `<div class="ml-rec-item">`;
                html += `<input type="checkbox" class="ml-algo-check" value="${this.escapeHtml(rec.name)}" checked>`;
                html += `<span>${this.escapeHtml(rec.display_name || rec.name)}</span>`;
                if (rec.reason) {
                    html += `<span style="color:#9CA3AF;font-size:0.75rem;"> \u2014 ${this.escapeHtml(rec.reason)}</span>`;
                }
                html += '</div>';
            }
            html += '</div>';
        }

        // Show all algorithms
        html += '<div style="font-weight:600;font-size:0.82rem;margin:0.75rem 0 0.5rem;">All Algorithms</div>';
        html += '<div class="ml-algo-grid">';

        const recommendedNames = new Set(recommendations.map(r => r.name));

        for (const algo of algorithms) {
            const isRec = recommendedNames.has(algo.name);
            html += `<label class="ml-algo-card ${isRec ? 'ml-algo-recommended' : ''}">`;
            html += `<input type="checkbox" class="ml-algo-check" value="${this.escapeHtml(algo.name)}" ${isRec || algo.default ? 'checked' : ''}>`;
            html += `<div class="ml-algo-name">${this.escapeHtml(algo.display_name || algo.name)}</div>`;
            html += `<div class="ml-algo-desc">${this.escapeHtml(algo.description || '')}</div>`;
            if (algo.speed) {
                html += `<div class="ml-algo-meta">Speed: ${this.escapeHtml(algo.speed)}</div>`;
            }
            html += '</label>';
        }
        html += '</div>';

        container.innerHTML = html;
    },

    async onAutoMLToggle() {
        const toggle = document.getElementById('mlAutoMLToggle');
        const isAutoML = toggle ? toggle.checked : true;
        const manualSection = document.getElementById('mlManualAlgoSection');
        const autoInfo = document.getElementById('mlAutoMLInfo');
        if (manualSection) manualSection.style.display = isAutoML ? 'none' : 'block';
        if (autoInfo) autoInfo.style.display = isAutoML ? '' : 'none';
        if (!isAutoML) {
            await this.loadAlgorithms();
        }
    },

    getSelectedAlgorithms() {
        const toggle = document.getElementById('mlAutoMLToggle');
        const isAutoML = toggle ? toggle.checked : true;
        if (isAutoML) return ['auto'];
        return Array.from(document.querySelectorAll('.ml-algo-check:checked')).map(cb => cb.value);
    },

    // ── Preprocessing Config ───────────────────────────────────

    getPreprocessingConfig() {
        const testSizeRaw = parseFloat(document.getElementById('mlTestSize')?.value || '0.2');
        return {
            scaling: document.getElementById('mlScaling')?.value || 'standard',
            encoding: document.getElementById('mlEncoding')?.value || 'onehot',
            imputation: document.getElementById('mlImputation')?.value || 'median',
            test_size: testSizeRaw,
            cv_folds: parseInt(document.getElementById('mlCVFolds')?.value || '5', 10),
            cv_strategy: document.getElementById('cvStrategy')?.value || 'auto',
            random_state: parseInt(document.getElementById('randomState')?.value || '42', 10),
        };
    },

    // ── Configuration ───────────────────────────────────

    async saveConfiguration() {
        const targetColumn = document.getElementById('targetColumn')?.value || null;
        const problemType = document.getElementById('problemType')?.value;
        const features = this.getSelectedFeatures();
        const preprocessing = this.getPreprocessingConfig();
        const algorithms = this.getSelectedAlgorithms();
        const isAutoMode = document.getElementById('mlAutoMLToggle')?.checked !== false;
        const optimizationLevel = document.getElementById('optimizationLevel')?.value || 'off';

        if (!problemType) {
            this.showToast('Please select a problem type.', 'error');
            return;
        }

        if (features.length === 0) {
            this.showToast('Please select at least one feature.', 'error');
            return;
        }

        // Shape the payload to match MLService.save_config expectations
        const body = {
            target_column: targetColumn,
            problem_type: problemType,
            feature_columns: features,          // service reads feature_columns
            selected_algorithms: isAutoMode ? null : algorithms,
            auto_mode: isAutoMode,
            optimization_level: optimizationLevel,
            optimization_iterations: 20,
            experiment_config: problemType === 'clustering' ? {
                n_clusters: Number(document.getElementById('nClusters')?.value || 3),
            } : null,
            // Spread preprocessing fields at top level
            ...preprocessing,
        };

        const btn = document.getElementById('mlConfigureBtn');
        this.setButtonLoading(btn, true);

        try {
            const resp = await fetch(`${this.apiBase}/configure`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }

            this.showToast('Configuration saved.', 'success');
            return true;
        } catch (e) {
            this.showToast('Failed to save configuration.', 'error');
        } finally {
            this.setButtonLoading(btn, false);
        }
    },

    // ── Data Preparation ───────────────────────────────────

    async prepareData() {
        const container = document.getElementById('mlPrepareResult');
        const btn = document.getElementById('mlPrepareBtn');
        if (!container) return;

        // Auto-save configuration first so service has up-to-date config
        if (!await this.saveConfiguration()) return;

        container.innerHTML = '<div class="ml-loading"><div class="ml-loading-spinner"></div> Preparing data (splitting &amp; preprocessing)…</div>';
        if (btn) this.setButtonLoading(btn, true);

        try {
            const resp = await fetch(`${this.apiBase}/prepare`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.prepareInfo = data;
            this.renderPrepareResult(data);
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Failed to prepare data. Please try again.</div>';
        } finally {
            if (btn) this.setButtonLoading(btn, false);
        }
    },

    renderPrepareResult(data) {
        const container = document.getElementById('mlPrepareResult');
        if (!container) return;

        let html = '<div class="ml-analysis-card">';

        // Split info
        html += '<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.5rem;">Data Split</div>';
        html += '<div class="ml-stats-grid">';
        if (data.train_rows !== undefined) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Train</span><span class="ml-stat-value">${data.train_rows.toLocaleString()} rows</span></div>`;
        }
        if (data.test_rows !== undefined) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Test</span><span class="ml-stat-value">${data.test_rows.toLocaleString()} rows</span></div>`;
        }
        if (data.total_features !== undefined) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Features</span><span class="ml-stat-value">${data.total_features}</span></div>`;
        }
        html += '</div>';

        // Preprocessing summary
        if (data.preprocessing_applied) {
            html += '<div style="font-weight:600;font-size:0.85rem;margin:0.75rem 0 0.5rem;">Preprocessing Applied</div>';
            html += '<div class="ml-preprocess-summary">';
            for (const [key, val] of Object.entries(data.preprocessing_applied)) {
                html += `<div class="ml-analysis-row"><span class="ml-analysis-label">${this.escapeHtml(key)}:</span><span>${this.escapeHtml(String(val))}</span></div>`;
            }
            html += '</div>';
        }

        // Warnings
        if (data.warnings && data.warnings.length > 0) {
            html += '<div style="margin-top:0.5rem;">';
            for (const w of data.warnings) {
                html += `<div class="warning-text" style="margin-bottom:0.25rem;">${this.escapeHtml(w)}</div>`;
            }
            html += '</div>';
        }

        html += '</div>';
        container.innerHTML = html;
    },

    // ── Model Training ───────────────────────────────────

    async startTraining() {
        if (this.isTraining) return;

        const btn = document.getElementById('mlTrainBtn');
        const container = document.getElementById('mlTrainStatus');
        if (!btn || !container) return;

        this.isTraining = true;
        this.setButtonLoading(btn, true);
        btn.disabled = true;

        // Show an animated progress bar immediately
        container.innerHTML = '<div class="ml-training-progress">' +
            '<div class="ml-loading"><div class="ml-loading-spinner"></div> Launching training job…</div>' +
            '<div class="ml-progress-bar-wrap"><div class="ml-progress-bar ml-progress-animated"></div></div>' +
            '<div style="font-size:0.82rem;color:#6B7280;margin-top:0.5rem;">Training runs in the background. The UI stays responsive while models are being built.</div>' +
            '</div>';

        try {
            const resp = await fetch(`${this.apiBase}/train`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                this.isTraining = false;
                this.setButtonLoading(btn, false);
                btn.disabled = false;
                return;
            }

            if (data.job_id) {
                this.pollTrainingStatus(data.job_id, btn, container);
            } else {
                // Synchronous fallback
                this.trainResults = data;
                this.renderTrainResults(data);
                this.showToast('Training complete!', 'success');
                this.isTraining = false;
                this.setButtonLoading(btn, false);
                btn.disabled = false;
            }
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Training request failed. Please try again.</div>';
            this.isTraining = false;
            this.setButtonLoading(btn, false);
            btn.disabled = false;
        }
    },

    pollTrainingStatus(jobId, btn, container) {
        sessionStorage.setItem(`training:${this.datasetId}`, jobId);
        btn.disabled = true;
        container.innerHTML = '<p id="trainingStage" role="status">Waiting for training progress…</p><progress id="trainingProgress" max="100" value="0" style="width:100%"></progress><p>Cancellation stops after the current model finishes fitting.</p><button type="button" class="btn btn-secondary" id="cancelTraining">Cancel training</button>';
        document.getElementById('cancelTraining').onclick = async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                const response = await fetch(`${this.apiBase}/train/cancel/${jobId}`, {method:'POST', headers:{'X-CSRFToken':getCsrfToken()}});
                if (!response.ok) throw new Error('Could not cancel');
                document.getElementById('trainingStage').textContent = 'Cancellation requested. Waiting for the current model to finish…';
            } catch (error) {
                button.disabled = false;
                this.showToast('Could not request cancellation. Try again.', 'error');
            }
        };
        let polling = false;
        const interval = setInterval(async () => {
            if (polling) return;
            polling = true;
            try {
                const resp = await fetch(`${this.apiBase}/train/status/${jobId}`);
                const data = await resp.json();
                if (['done', 'error', 'cancelled'].includes(data.status) || data.error) {
                    sessionStorage.removeItem(`training:${this.datasetId}`);
                }
                if (data.status === 'cancelled') {
                    clearInterval(interval);
                    container.textContent = 'Training cancelled. You can change your settings and start again.';
                    this.isTraining = false;
                    this.setButtonLoading(btn, false);
                    btn.disabled = false;
                    return;
                }
                if (['running', 'cancelling'].includes(data.status)) {
                    document.getElementById('trainingProgress').value = data.total ? 100 * data.completed / data.total : 0;
                    document.getElementById('trainingStage').textContent = data.status === 'cancelling' ? 'Cancellation requested. Finishing the current model…' : `${data.completed} of ${data.total || '?'} models completed${data.model ? ' — Training ' + data.model : ' — Preparing'}`;
                }
                
                if (data.error) {
                    clearInterval(interval);
                    container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                    this.isTraining = false;
                    this.setButtonLoading(btn, false);
                    btn.disabled = false;
                    return;
                }
                
                if (data.status === 'done') {
                    clearInterval(interval);
                    this.trainResults = data.result;
                    this.renderTrainResults(data.result);
                    this.showToast('Training complete!', 'success');
                    this.isTraining = false;
                    this.setButtonLoading(btn, false);
                    btn.disabled = false;
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    container.innerHTML = `<div class="ml-inline-error">Training failed: ${this.escapeHtml(data.error)}</div>`;
                    this.isTraining = false;
                    this.setButtonLoading(btn, false);
                    btn.disabled = false;
                }
                // If status === 'running', continue polling
            } catch (e) {
                clearInterval(interval);
                container.innerHTML = '<div class="ml-inline-error">Connection to server lost while checking status.</div>';
                this.isTraining = false;
                this.setButtonLoading(btn, false);
                btn.disabled = false;
            } finally {
                polling = false;
            }
        }, 2000);
    },

    renderTrainResults(data) {
        const container = document.getElementById('mlTrainStatus');
        if (!container) return;

        // API returns: {leaderboard: [...], model_results: {...}, best_model, training_time, task_type}
        const leaderboard = data.leaderboard || data.results || data.models || [];
        const bestModel = data.best_model || (data.task_type !== 'clustering' && leaderboard[0]?.model_name) || '';
        const trainingTime = data.training_time || 0;
        const taskType = data.task_type || '';

        // Populate optimize model dropdown
        const optimizeSelect = document.getElementById('mlOptimizeModel');
        if (optimizeSelect) {
            optimizeSelect.innerHTML = '<option value="">-- Select a trained model --</option>';
            for (const entry of leaderboard) {
                const name = entry.model_name || entry.name || entry.algorithm;
                if (name) {
                    const opt = document.createElement('option');
                    opt.value = name;
                    opt.textContent = name;
                    optimizeSelect.appendChild(opt);
                }
            }
        }

        if (leaderboard.length === 0) {
            container.innerHTML = '<div class="info-text">No models were trained successfully.</div>';
            return;
        }

        const topEntry = leaderboard[0];
        const topScore = topEntry.primary_score ?? topEntry.cv_mean ?? topEntry.cv_score;
        const metricName = topEntry.primary_metric || topEntry.metric || 'Score';
        const totalTime = leaderboard.reduce((s, m) => s + (m.fit_time || m.train_time || 0), 0);

        let html = '<div class="ml-train-summary">';
        html += `<div style="font-weight:600;font-size:0.9rem;margin-bottom:0.5rem;">✅ ${leaderboard.length} Model${leaderboard.length > 1 ? 's' : ''} Trained — ${trainingTime.toFixed(1)}s total</div>`;
        html += '<div class="ml-stats-grid">';
        html += `<div class="ml-stat-item"><span class="ml-stat-label">Best Model</span><span class="ml-stat-value improved">${this.escapeHtml(bestModel || '—')}</span></div>`;
        html += `<div class="ml-stat-item"><span class="ml-stat-label">${this.escapeHtml(metricName)}</span><span class="ml-stat-value improved">${this.formatScore(topScore)}</span></div>`;
        html += `<div class="ml-stat-item"><span class="ml-stat-label">CV Mean</span><span class="ml-stat-value">${this.formatScore(topEntry.cv_mean)}</span></div>`;
        html += `<div class="ml-stat-item"><span class="ml-stat-label">Training Time</span><span class="ml-stat-value">${trainingTime.toFixed(1)}s</span></div>`;
        html += '</div>';
        if (taskType) html += `<div style="font-size:0.82rem;color:#6B7280;margin-top:0.25rem;">Task: ${this.escapeHtml(taskType)}</div>`;
        html += '<div style="margin-top:0.5rem;font-size:0.82rem;">Go to <strong>Compare</strong> to see the full leaderboard and <strong>Results</strong> for charts.</div>';
        html += '</div>';
        container.innerHTML = html;
    },

    // ── Leaderboard ───────────────────────────────────

    renderLeaderboard() {
        const container = document.getElementById('mlLeaderboardBody');
        if (!container || !this.trainResults) return;

        // API leaderboard shape: {rank, model_name, primary_metric, primary_score, cv_mean, cv_std, metrics, fit_time}
        const entries = [...(this.trainResults.leaderboard || this.trainResults.results || this.trainResults.models || [])];

        // Normalise field names: support both old and new shape
        const normalise = e => ({
            rank: e.rank ?? 0,
            model_name: e.model_name || e.name || e.algorithm || 'Unknown',
            cv_mean: e.cv_mean ?? e.cv_score,
            cv_std: e.cv_std,
            primary_score: e.primary_score ?? e.test_score,
            primary_metric: e.primary_metric || e.metric || 'Score',
            fit_time: e.fit_time ?? e.train_time,
            metrics: e.metrics || {},
        });

        let rows = entries.map(normalise);

        // Sort
        const sortKey = this.sortColumn === 'cv_score' ? 'cv_mean' : this.sortColumn;
        rows.sort((a, b) => {
            let va = a[sortKey];
            let vb = b[sortKey];
            if (va === undefined || va === null) va = -Infinity;
            if (vb === undefined || vb === null) vb = -Infinity;
            return this.sortDir === 'asc' ? va - vb : vb - va;
        });

        // Update sort indicators
        document.querySelectorAll('[data-sort-column]').forEach(th => {
            const col = th.dataset.sortColumn;
            th.classList.toggle('sort-asc', col === this.sortColumn && this.sortDir === 'asc');
            th.classList.toggle('sort-desc', col === this.sortColumn && this.sortDir === 'desc');
        });

        if (rows.length === 0) {
            container.innerHTML = '<tr><td colspan="6" class="empty-state">No results yet. Train models first.</td></tr>';
            return;
        }

        let html = '';
        rows.forEach((row, idx) => {
            const isBest = row.rank === 1 && row.primary_score != null;
            html += `<tr class="${isBest ? 'ml-leaderboard-best' : ''}">`;
            html += `<td class="ml-rank ${isBest ? 'ml-rank-1' : ''}">${row.rank}</td>`;
            html += `<td><strong>${this.escapeHtml(row.model_name)}</strong>${isBest ? ' <span class="ml-badge badge-trained">Best</span>' : ''}</td>`;
            html += `<td>${this.formatScore(row.cv_mean)}${typeof row.cv_std === 'number' ? ` <span style="color:#9CA3AF;font-size:0.75rem;">±${row.cv_std.toFixed(3)}</span>` : ''}</td>`;
            html += `<td>${row.primary_score !== undefined && row.primary_score !== null ? this.formatScore(row.primary_score) : '—'}</td>`;
            html += `<td>${row.fit_time !== undefined && row.fit_time !== null ? row.fit_time.toFixed(2) + 's' : '—'}</td>`;
            html += '<td>';
            if (row.metrics && Object.keys(row.metrics).length > 0) {
                html += '<div class="ml-metrics-chips">';
                for (const [key, val] of Object.entries(row.metrics)) {
                    html += `<span class="ml-metric-chip">${this.escapeHtml(key)}: ${typeof val === 'number' ? val.toFixed(4) : val}</span>`;
                }
                html += '</div>';
            }
            html += '</td></tr>';
        });

        container.innerHTML = html;
    },

    // ── Hyperparameter Optimization ───────────────────────────────────

    async runOptimization() {
        const modelSelect = document.getElementById('mlOptimizeModel');
        const levelSelect = document.getElementById('mlOptimizeLevel');
        const container = document.getElementById('mlOptimizeResult');
        const btn = document.getElementById('mlOptimizeBtn');

        if (!modelSelect || !container || !btn) return;

        const model = modelSelect.value;
        if (!model) {
            this.showToast('Please select a model to optimize.', 'error');
            return;
        }

        const level = levelSelect?.value || 'light';

        container.innerHTML = '<div class="ml-loading">Optimizing hyperparameters...</div>';
        this.setButtonLoading(btn, true);

        try {
            const resp = await fetch(`${this.apiBase}/optimize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ model, level }),
            });
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.renderOptimizeResult(data);
            this.showToast('Optimization complete!', 'success');
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Optimization failed.</div>';
        } finally {
            this.setButtonLoading(btn, false);
        }
    },

    renderOptimizeResult(data) {
        const container = document.getElementById('mlOptimizeResult');
        if (!container) return;

        let html = '<div class="ml-analysis-card">';
        html += '<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.5rem;">Optimization Results</div>';

        if (data.best_score !== undefined) {
            html += '<div class="ml-stats-grid">';
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Best Score</span><span class="ml-stat-value improved">${this.formatScore(data.best_score)}</span></div>`;
            if (data.base_score !== undefined) {
                const diff = data.best_score - data.base_score;
                const diffClass = diff > 0 ? 'improved' : diff < 0 ? 'worsened' : '';
                html += `<div class="ml-stat-item"><span class="ml-stat-label">Improvement</span><span class="ml-stat-value ${diffClass}">${diff > 0 ? '+' : ''}${diff.toFixed(4)}</span></div>`;
            }
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Trials</span><span class="ml-stat-value">${data.trials || data.n_trials || '\u2014'}</span></div>`;
            if (data.time !== undefined) {
                html += `<div class="ml-stat-item"><span class="ml-stat-label">Time</span><span class="ml-stat-value">${data.time.toFixed(2)}s</span></div>`;
            }
            html += '</div>';
        }

        // Best parameters
        if (data.best_params) {
            html += '<div style="font-weight:600;font-size:0.85rem;margin:0.75rem 0 0.5rem;">Best Parameters</div>';
            html += '<div class="ml-params-grid">';
            for (const [key, val] of Object.entries(data.best_params)) {
                html += `<div class="ml-param-item"><span class="ml-param-key">${this.escapeHtml(key)}</span><span class="ml-param-val">${this.escapeHtml(String(val))}</span></div>`;
            }
            html += '</div>';
        }

        html += '</div>';
        container.innerHTML = html;
    },

    // ── Results Dashboard ───────────────────────────────────

    async loadExistingResults() {
        // Check if there are already results from a previous session
        try {
            const resp = await fetch(`${this.apiBase}/results`);
            if (!resp.ok) return;
            const data = await resp.json();
            // Accept both leaderboard (new) and results/models (old) shapes
            if (data && !data.error && (data.leaderboard || data.results || data.models)) {
                this.trainResults = data;
                this.currentResults = data;
                // Populate leaderboard immediately if we're on step 5
                if (this.currentStep === 5) this.renderLeaderboard();
            }
        } catch (e) {
            // No existing results, that's fine
        }
    },

    async loadResultsDashboard() {
        if (!this.trainResults) {
            this.showNoResults();
            return;
        }

        const taskType = this.trainResults.task_type || document.getElementById('problemType')?.value || '';

        // Show save & actions bar
        const actionsBar = document.getElementById('mlResultsActions');
        if (actionsBar) actionsBar.style.display = '';

        this.renderBestModelMetrics();

        // Classification-specific charts
        const cmCard = document.getElementById('mlConfusionMatrixCard');
        const rocCard = document.getElementById('mlRocCurveCard');
        const predCard = document.getElementById('mlPredictionsCard');
        const fiCard = document.getElementById('mlFeatureImportanceCard');

        if (taskType === 'classification') {
            if (cmCard) cmCard.style.display = '';
            if (rocCard) rocCard.style.display = '';
            if (predCard) predCard.style.display = 'none';
            await this.loadConfusionMatrix();
            await this.loadRocCurve();
        } else if (taskType === 'regression') {
            if (cmCard) cmCard.style.display = 'none';
            if (rocCard) rocCard.style.display = 'none';
            if (predCard) predCard.style.display = '';
            await this.loadPredictions();
        } else {
            // clustering or unknown
            if (cmCard) cmCard.style.display = 'none';
            if (rocCard) rocCard.style.display = 'none';
            if (predCard) predCard.style.display = 'none';
        }

        // Feature importance — always try
        if (fiCard) fiCard.style.display = '';
        await this.loadFeatureImportance();
    },

    showNoResults() {
        const el = document.getElementById('mlResultsContent');
        if (el) el.innerHTML = '<div class="empty-state"><p>No results yet. Complete the training step first.</p></div>';
    },

    renderBestModelMetrics() {
        const container = document.getElementById('mlBestModelMetrics');
        if (!container || !this.trainResults) return;

        // Leaderboard shape: [{rank, model_name, primary_metric, primary_score, cv_mean, cv_std, metrics, fit_time}]
        const leaderboard = this.trainResults.leaderboard || this.trainResults.results || this.trainResults.models || [];
        if (leaderboard.length === 0) {
            container.innerHTML = '<div class="ml-empty-state">No training results found.</div>';
            return;
        }

        const best = leaderboard[0];
        const bestName = this.trainResults.task_type === 'clustering' && best.primary_score == null
            ? 'No model has a valid silhouette score' : (best.model_name || best.name || best.algorithm || 'Best Model');
        const cvMean = best.cv_mean ?? best.cv_score;
        const cvStd = best.cv_std;
        const testScore = best.primary_score ?? best.test_score;
        const metricName = best.primary_metric || best.metric || 'Score';
        const fitTime = best.fit_time ?? best.train_time;
        const trainingTime = this.trainResults.training_time;

        let html = '<div class="ml-analysis-card">';
        html += `<div style="font-weight:700;font-size:1rem;margin-bottom:0.75rem;">🏆 Best Model: <span style="color:#6366F1;">${this.escapeHtml(bestName)}</span></div>`;

        html += '<div class="ml-stats-grid">';
        if (cvMean !== undefined && cvMean !== null) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">CV Score</span><span class="ml-stat-value improved">${this.formatScore(cvMean)}${cvStd !== undefined ? ` ±${cvStd.toFixed(3)}` : ''}</span></div>`;
        }
        if (testScore !== undefined && testScore !== null) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">${this.escapeHtml(metricName)}${this.trainResults.task_type === 'clustering' ? '' : ' (test)'}</span><span class="ml-stat-value improved">${this.formatScore(testScore)}</span></div>`;
        }
        if (fitTime !== undefined && fitTime !== null) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Train Time</span><span class="ml-stat-value">${fitTime.toFixed(2)}s</span></div>`;
        }
        if (trainingTime !== undefined && trainingTime !== null) {
            html += `<div class="ml-stat-item"><span class="ml-stat-label">Total Training</span><span class="ml-stat-value">${trainingTime.toFixed(1)}s</span></div>`;
        }
        html += '</div>';

        // All metrics from the best model
        if (best.metrics && Object.keys(best.metrics).length > 0) {
            html += '<div style="font-weight:600;font-size:0.85rem;margin:0.75rem 0 0.5rem;">Detailed Metrics</div>';
            html += '<div class="ml-metrics-detail-grid">';
            for (const [key, val] of Object.entries(best.metrics)) {
                const displayVal = typeof val === 'number' ? val.toFixed(4) : String(val);
                html += `<div class="ml-metric-detail"><span class="ml-metric-detail-label">${this.escapeHtml(key)}</span><span class="ml-metric-detail-value">${displayVal}</span></div>`;
            }
            html += '</div>';
        }

        // All models summary
        if (leaderboard.length > 1) {
            html += `<div style="margin-top:0.75rem;font-size:0.82rem;color:#6B7280;">${leaderboard.length} models trained. See <strong>Compare</strong> step for full leaderboard.</div>`;
        }

        html += '</div>';
        container.innerHTML = html;
    },

    renderClassificationReport(report) {
        if (!report) return '';

        // Handle string reports
        if (typeof report === 'string') {
            return `<pre style="font-size:0.78rem;background:#F9FAFB;padding:0.75rem;border-radius:8px;overflow-x:auto;white-space:pre-wrap;">${this.escapeHtml(report)}</pre>`;
        }

        // Handle structured reports
        let html = '<table class="data-table"><thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead><tbody>';

        for (const [cls, metrics] of Object.entries(report)) {
            if (typeof metrics !== 'object' || metrics === null) continue;
            html += '<tr>';
            html += `<td><strong>${this.escapeHtml(cls)}</strong></td>`;
            html += `<td>${(metrics.precision || 0).toFixed(4)}</td>`;
            html += `<td>${(metrics.recall || 0).toFixed(4)}</td>`;
            html += `<td>${(metrics['f1-score'] || metrics.f1 || 0).toFixed(4)}</td>`;
            html += `<td>${(metrics.support || 0).toLocaleString()}</td>`;
            html += '</tr>';
        }

        html += '</tbody></table>';
        return html;
    },

    async loadConfusionMatrix() {
        const canvas = document.getElementById('mlConfusionMatrixCanvas');
        if (!canvas) return;

        try {
            const resp = await fetch(`${this.apiBase}/confusion-matrix`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.error) {
                const wrapper = canvas.closest('.ml-card');
                if (wrapper) wrapper.querySelector('.ml-card-body').innerHTML = `<div class="ml-info">${this.escapeHtml(data.error)}</div>`;
                return;
            }
            this.drawConfusionMatrix(canvas, data);
        } catch (e) {
            console.error('Failed to load confusion matrix:', e);
        }
    },

    async loadRocCurve() {
        const canvas = document.getElementById('mlRocCurveCanvas');
        if (!canvas) return;

        try {
            const resp = await fetch(`${this.apiBase}/roc-curve`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data.error || !data.available) {
                const wrapper = canvas.closest('.ml-card');
                if (wrapper) {
                    const msg = data.error || data.message || 'ROC curve not available for this model.';
                    wrapper.querySelector('.ml-card-body').innerHTML = `<div class="ml-info">${this.escapeHtml(msg)}</div>`;
                }
                return;
            }
            this.drawRocCurve(canvas, data);
        } catch (e) {
            console.error('Failed to load ROC curve:', e);
        }
    },

    drawRocCurve(canvas, data) {
        const ctx = canvas.getContext('2d');
        const fpr = data.fpr || [];
        const tpr = data.tpr || [];
        const auc = data.auc || 0;
        if (fpr.length === 0) return;

        const padding = { top: 30, right: 30, bottom: 55, left: 60 };
        const containerWidth = canvas.parentElement.clientWidth - 20;
        const width = Math.max(320, Math.min(containerWidth, 500));
        const height = 340;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, width, height);

        const plotW = width - padding.left - padding.right;
        const plotH = height - padding.top - padding.bottom;
        const scaleX = v => padding.left + v * plotW;
        const scaleY = v => padding.top + (1 - v) * plotH;

        // Background
        ctx.fillStyle = '#F9FAFB';
        ctx.fillRect(padding.left, padding.top, plotW, plotH);

        // Grid
        ctx.strokeStyle = '#E5E7EB';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const v = i / 5;
            ctx.beginPath();
            ctx.moveTo(scaleX(v), padding.top);
            ctx.lineTo(scaleX(v), padding.top + plotH);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(padding.left, scaleY(v));
            ctx.lineTo(padding.left + plotW, scaleY(v));
            ctx.stroke();
        }

        // Diagonal (random classifier)
        ctx.strokeStyle = '#9CA3AF';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(scaleX(0), scaleY(0));
        ctx.lineTo(scaleX(1), scaleY(1));
        ctx.stroke();
        ctx.setLineDash([]);

        // ROC curve
        ctx.strokeStyle = '#6366F1';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(scaleX(fpr[0]), scaleY(tpr[0]));
        for (let i = 1; i < fpr.length; i++) {
            ctx.lineTo(scaleX(fpr[i]), scaleY(tpr[i]));
        }
        ctx.stroke();

        // Fill under curve
        ctx.fillStyle = 'rgba(99,102,241,0.08)';
        ctx.beginPath();
        ctx.moveTo(scaleX(fpr[0]), scaleY(tpr[0]));
        for (let i = 1; i < fpr.length; i++) ctx.lineTo(scaleX(fpr[i]), scaleY(tpr[i]));
        ctx.lineTo(scaleX(1), scaleY(0));
        ctx.lineTo(scaleX(0), scaleY(0));
        ctx.closePath();
        ctx.fill();

        // Axis tick labels
        ctx.fillStyle = '#6B7280';
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        for (let i = 0; i <= 5; i++) {
            const v = i / 5;
            ctx.fillText(v.toFixed(1), scaleX(v), padding.top + plotH + 16);
        }
        ctx.textAlign = 'right';
        for (let i = 0; i <= 5; i++) {
            const v = i / 5;
            ctx.fillText(v.toFixed(1), padding.left - 8, scaleY(v) + 4);
        }

        // Axis labels
        ctx.fillStyle = '#374151';
        ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('False Positive Rate (FPR)', padding.left + plotW / 2, height - 6);
        ctx.save();
        ctx.translate(14, padding.top + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('True Positive Rate (TPR)', 0, 0);
        ctx.restore();

        // AUC badge
        const badgeText = `AUC = ${auc.toFixed(4)}`;
        ctx.font = 'bold 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        const bw = ctx.measureText(badgeText).width + 20;
        const bh = 24;
        const bx = padding.left + plotW - bw - 8;
        const by = padding.top + 8;
        ctx.fillStyle = '#6366F1';
        ctx.beginPath();
        ctx.roundRect(bx, by, bw, bh, 4);
        ctx.fill();
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'center';
        ctx.fillText(badgeText, bx + bw / 2, by + 16);

        // Title
        ctx.fillStyle = '#374151';
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`ROC Curve — ${this.escapeHtml(data.model_name || 'Best Model')}`, width / 2, 18);
    },

    drawConfusionMatrix(canvas, data) {
        const ctx = canvas.getContext('2d');
        const matrix = data.matrix || data;
        const labels = data.labels || data.classes || [];
        const n = matrix.length;
        if (n === 0) return;

        // Size the canvas
        const padding = { top: 30, right: 20, bottom: 50, left: 70 };
        const cellSize = Math.min(60, Math.max(30, (canvas.parentElement.clientWidth - padding.left - padding.right) / n));
        const width = padding.left + cellSize * n + padding.right;
        const height = padding.top + cellSize * n + padding.bottom;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(dpr, dpr);

        // Clear
        ctx.clearRect(0, 0, width, height);

        // Find max value for color scaling
        let maxVal = 0;
        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n; j++) {
                maxVal = Math.max(maxVal, matrix[i][j] || 0);
            }
        }
        maxVal = Math.max(maxVal, 1);

        // Draw title
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = '#374151';
        ctx.textAlign = 'center';
        ctx.fillText('Confusion Matrix', width / 2, 18);

        // Draw cells
        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n; j++) {
                const val = matrix[i][j] || 0;
                const intensity = maxVal > 0 ? val / maxVal : 0;
                const x = padding.left + j * cellSize;
                const y = padding.top + i * cellSize;

                // Color: white to blue
                const r = Math.round(255 - intensity * 200);
                const g = Math.round(255 - intensity * 200);
                const b = Math.round(255 - intensity * 55);
                ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
                ctx.fillRect(x, y, cellSize, cellSize);

                // Border
                ctx.strokeStyle = '#E5E7EB';
                ctx.lineWidth = 0.5;
                ctx.strokeRect(x, y, cellSize, cellSize);

                // Value text
                const textColor = intensity > 0.5 ? '#FFFFFF' : '#374151';
                ctx.fillStyle = textColor;
                ctx.font = `${cellSize > 40 ? 12 : 10}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(val.toLocaleString(), x + cellSize / 2, y + cellSize / 2);
            }
        }

        // Labels
        ctx.fillStyle = '#6B7280';
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        for (let j = 0; j < n; j++) {
            ctx.fillText(
                this.truncateText(labels[j], 10),
                padding.left + j * cellSize + cellSize / 2,
                padding.top + n * cellSize + 8
            );
        }

        // Axis labels
        ctx.fillStyle = '#374151';
        ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Predicted', padding.left + (n * cellSize) / 2, height - 6);

        ctx.save();
        ctx.translate(12, padding.top + (n * cellSize) / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Actual', 0, 0);
        ctx.restore();
    },

    async loadPredictions() {
        const canvas = document.getElementById('mlPredictionsCanvas');
        if (!canvas) return;

        const problemType = document.getElementById('problemType')?.value || 'classification';
        if (problemType === 'clustering') {
            const wrapper = canvas.parentElement;
            if (wrapper) wrapper.innerHTML = '<div class="info-text">Predictions not available for clustering.</div>';
            return;
        }

        try {
            const resp = await fetch(`${this.apiBase}/predictions`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.error) return;

            if (problemType === 'regression') {
                this.drawActualVsPredicted(canvas, data);
            } else {
                this.drawClassificationPredictions(canvas, data);
            }
        } catch (e) {
            console.error('Failed to load predictions:', e);
        }
    },

    drawActualVsPredicted(canvas, data) {
        const ctx = canvas.getContext('2d');
        const actual = data.actual || [];
        const predicted = data.predicted || [];
        if (actual.length === 0) return;

        const padding = { top: 30, right: 30, bottom: 50, left: 60 };
        const containerWidth = canvas.parentElement.clientWidth - 20;
        const width = Math.max(300, containerWidth);
        const height = 300;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, width, height);

        const plotW = width - padding.left - padding.right;
        const plotH = height - padding.top - padding.bottom;

        // Compute range
        let allVals = [...actual, ...predicted];
        let minVal = Math.min(...allVals);
        let maxVal = Math.max(...allVals);
        const range = maxVal - minVal || 1;
        minVal -= range * 0.05;
        maxVal += range * 0.05;
        const valRange = maxVal - minVal;

        const scaleX = v => padding.left + ((v - minVal) / valRange) * plotW;
        const scaleY = v => padding.top + plotH - ((v - minVal) / valRange) * plotH;

        // Title
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = '#374151';
        ctx.textAlign = 'center';
        ctx.fillText('Actual vs Predicted', width / 2, 18);

        // Grid lines
        ctx.strokeStyle = '#F3F4F6';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const v = minVal + (valRange * i) / 5;
            const y = scaleY(v);
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();
        }

        // Diagonal line
        ctx.strokeStyle = '#D1D5DB';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(scaleX(minVal), scaleY(minVal));
        ctx.lineTo(scaleX(maxVal), scaleY(maxVal));
        ctx.stroke();
        ctx.setLineDash([]);

        // Data points
        ctx.fillStyle = 'rgba(99, 102, 241, 0.5)';
        for (let i = 0; i < actual.length; i++) {
            const x = scaleX(actual[i]);
            const y = scaleY(predicted[i]);
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fill();
        }

        // Axis labels
        ctx.fillStyle = '#6B7280';
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        for (let i = 0; i <= 5; i++) {
            const v = minVal + (valRange * i) / 5;
            const label = v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toFixed(1);
            ctx.fillText(label, scaleX(v), height - padding.bottom + 18);
            ctx.fillText(label, padding.left - 8, scaleY(v) + 4);
        }

        ctx.fillStyle = '#374151';
        ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Actual Values', width / 2, height - 4);

        ctx.save();
        ctx.translate(12, height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Predicted Values', 0, 0);
        ctx.restore();
    },

    drawClassificationPredictions(canvas, data) {
        // For classification, show a bar chart of correct vs incorrect per class
        const ctx = canvas.getContext('2d');
        const actual = data.actual || [];
        const predicted = data.predicted || [];
        if (actual.length === 0) return;

        // Compute per-class accuracy
        const classCounts = {};
        const correctCounts = {};
        const labels = data.labels || [...new Set(actual)].sort();

        for (const lbl of labels) {
            classCounts[lbl] = 0;
            correctCounts[lbl] = 0;
        }

        for (let i = 0; i < actual.length; i++) {
            classCounts[actual[i]] = (classCounts[actual[i]] || 0) + 1;
            if (actual[i] === predicted[i]) {
                correctCounts[actual[i]] = (correctCounts[actual[i]] || 0) + 1;
            }
        }

        const padding = { top: 30, right: 30, bottom: 50, left: 60 };
        const containerWidth = canvas.parentElement.clientWidth - 20;
        const width = Math.max(300, containerWidth);
        const height = 300;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, width, height);

        const plotW = width - padding.left - padding.right;
        const plotH = height - padding.top - padding.bottom;
        const n = labels.length;
        const barGroupWidth = plotW / n;
        const barWidth = barGroupWidth * 0.35;
        const maxCount = Math.max(...Object.values(classCounts), 1);

        const scaleY = v => padding.top + plotH - (v / maxCount) * plotH;

        // Title
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = '#374151';
        ctx.textAlign = 'center';
        ctx.fillText('Per-Class Accuracy', width / 2, 18);

        // Grid
        ctx.strokeStyle = '#F3F4F6';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const v = (maxCount * i) / 5;
            const y = scaleY(v);
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();

            ctx.fillStyle = '#9CA3AF';
            ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(Math.round(v).toString(), padding.left - 8, y + 3);
        }

        // Bars
        for (let i = 0; i < n; i++) {
            const lbl = labels[i];
            const total = classCounts[lbl] || 0;
            const correct = correctCounts[lbl] || 0;
            const incorrect = total - correct;
            const x = padding.left + i * barGroupWidth + barGroupWidth / 2;

            // Correct bar (green)
            ctx.fillStyle = '#059669';
            ctx.fillRect(x - barWidth - 1, scaleY(correct), barWidth, plotH - (plotH - scaleY(correct)));

            // Incorrect bar (red)
            ctx.fillStyle = '#DC2626';
            ctx.fillRect(x + 1, scaleY(incorrect), barWidth, plotH - (plotH - scaleY(incorrect)));

            // Label
            ctx.fillStyle = '#6B7280';
            ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(this.truncateText(String(lbl), 10), x, height - padding.bottom + 16);
        }

        // Legend
        const legendX = width - padding.right - 160;
        const legendY = padding.top + 10;
        ctx.fillStyle = '#059669';
        ctx.fillRect(legendX, legendY, 12, 12);
        ctx.fillStyle = '#374151';
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('Correct', legendX + 16, legendY + 10);

        ctx.fillStyle = '#DC2626';
        ctx.fillRect(legendX + 80, legendY, 12, 12);
        ctx.fillStyle = '#374151';
        ctx.fillText('Incorrect', legendX + 96, legendY + 10);
    },

    async loadFeatureImportance() {
        const canvas = document.getElementById('mlFeatureImportanceCanvas');
        if (!canvas) return;

        try {
            const resp = await fetch(`${this.apiBase}/feature-importance`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.error) {
                const wrapper = canvas.parentElement;
                if (wrapper) wrapper.innerHTML = `<div class="info-text">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.drawFeatureImportance(canvas, data);
        } catch (e) {
            console.error('Failed to load feature importance:', e);
        }
    },

    drawFeatureImportance(canvas, data) {
        const ctx = canvas.getContext('2d');
        const features = data.features || data.importance || data;
        if (!Array.isArray(features) || features.length === 0) return;

        // Sort by importance descending, take top 20
        const sorted = [...features]
            .sort((a, b) => (b.importance || b.value || 0) - (a.importance || a.value || 0))
            .slice(0, 20);

        const n = sorted.length;
        const padding = { top: 20, right: 60, bottom: 30, left: 120 };
        const containerWidth = canvas.parentElement.clientWidth - 20;
        const width = Math.max(400, containerWidth);
        const barHeight = Math.max(16, Math.min(28, 400 / n));
        const height = padding.top + n * barHeight + padding.bottom;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, width, height);

        const plotW = width - padding.left - padding.right;
        const maxImp = sorted[0].importance || sorted[0].value || 1;

        // Title
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = '#374151';
        ctx.textAlign = 'center';
        ctx.fillText('Feature Importance', width / 2, 14);

        // Draw bars
        for (let i = 0; i < n; i++) {
            const imp = sorted[i].importance || sorted[i].value || 0;
            const y = padding.top + i * barHeight;
            const barW = (imp / maxImp) * plotW;

            // Bar
            const gradient = ctx.createLinearGradient(padding.left, 0, padding.left + barW, 0);
            gradient.addColorStop(0, '#6366F1');
            gradient.addColorStop(1, '#818CF8');
            ctx.fillStyle = gradient;
            ctx.fillRect(padding.left, y + 2, barW, barHeight - 4);

            // Feature name
            ctx.fillStyle = '#374151';
            ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            ctx.fillText(
                this.truncateText(sorted[i].name || sorted[i].feature || `Feature ${i + 1}`, 18),
                padding.left - 8,
                y + barHeight / 2
            );

            // Value
            ctx.fillStyle = '#6B7280';
            ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(imp.toFixed(4), padding.left + barW + 6, y + barHeight / 2);
        }
    },

    // ── Model Saving ───────────────────────────────────

    showSaveModelDialog() {
        if (!this.trainResults) {
            this.showToast('No trained model to save.', 'error');
            return;
        }

        const nameInput = document.getElementById('mlModelName');
        const descInput = document.getElementById('mlModelDescription');
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';

        // Auto-fill model name
        const models = this.trainResults.results || this.trainResults.models || [];
        if (models.length > 0 && nameInput) {
            const best = models[0];
            nameInput.value = best.name || best.algorithm || 'my-model';
        }

        if (typeof openModal === 'function') {
            openModal('mlSaveModal');
        } else {
            const modal = document.getElementById('mlSaveModal');
            if (modal) modal.style.display = 'flex';
        }
    },

    async saveModel() {
        const name = document.getElementById('mlModelName')?.value?.trim();
        const description = document.getElementById('mlModelDescription')?.value?.trim();

        if (!name) {
            this.showToast('Please enter a model name.', 'error');
            return;
        }

        const btn = document.getElementById('mlConfirmSaveModelBtn');
        this.setButtonLoading(btn, true);

        try {
            const resp = await fetch(`${this.apiBase}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ name, description }),
            });
            const data = await resp.json();

            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }

            this.showToast('Model saved successfully!', 'success');
            if (typeof closeModal === 'function') {
                closeModal('mlSaveModal');
            } else {
                const modal = document.getElementById('mlSaveModal');
                if (modal) modal.style.display = 'none';
            }
        } catch (e) {
            this.showToast('Failed to save model.', 'error');
        } finally {
            this.setButtonLoading(btn, false);
        }
    },

    // ── Clear Results ───────────────────────────────────

    async clearResults() {
        try {
            const resp = await fetch(`${this.apiBase}/clear`, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } });
            const data = await resp.json();

            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }

            this.trainResults = null;
            this.currentResults = null;
            this.showToast('Results cleared.', 'success');

            // Reset UI
            const statusEl = document.getElementById('mlTrainStatus');
            if (statusEl) statusEl.innerHTML = '';

            const leaderboardBody = document.getElementById('mlLeaderboardBody');
            if (leaderboardBody) leaderboardBody.innerHTML = '<tr><td colspan="6" class="empty-state">No results yet. Train models first.</td></tr>';

            this.showNoResults();
        } catch (e) {
            this.showToast('Failed to clear results.', 'error');
        }
    },

    // ── Model Management (Models List Page) ───────────────────────────────────

    async loadModelsList() {
        const container = document.getElementById('mlModelsList');
        if (!container) return;

        container.innerHTML = '<div class="ml-loading">Loading models...</div>';

        try {
            const resp = await fetch(this.modelsApiBase);
            const data = await resp.json();

            if (data.error) {
                container.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(data.error)}</div>`;
                return;
            }

            this.renderModelsList(data.models || data || []);
        } catch (e) {
            container.innerHTML = '<div class="ml-inline-error">Failed to load models.</div>';
        }
    },

    renderModelsList(models) {
        const container = document.getElementById('mlModelsList');
        if (!container) return;

        if (!Array.isArray(models) || models.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No saved models yet.</p></div>';
            return;
        }

        let html = '<div class="ml-models-grid">';
        for (const model of models) {
            html += '<div class="ml-model-card">';
            html += '<div class="ml-model-card-header">';
            html += `<strong>${this.escapeHtml(model.model_name || model.name || 'Untitled Model')}</strong>`;
            html += `<span class="dtype-badge">${this.escapeHtml(model.problem_type || model.type || '\u2014')}</span>`;
            html += '</div>';

            if (model.description) {
                html += `<div style="font-size:0.82rem;color:#6B7280;margin:0.5rem 0;">${this.escapeHtml(model.description)}</div>`;
            }

            html += '<div class="ml-model-card-meta">';
            if (model.dataset_name) {
                html += `<span>Dataset: ${this.escapeHtml(model.dataset_name)}</span>`;
            }
            if (model.algorithm || model.model_type) {
                html += `<span>Algorithm: ${this.escapeHtml(model.algorithm || model.model_type)}</span>`;
            }
            if (model.score !== undefined) {
                html += `<span>Score: ${this.formatScore(model.score)}</span>`;
            }
            if (model.created_at) {
                html += `<span>${this.escapeHtml(model.created_at)}</span>`;
            }
            html += '</div>';

            html += '<div class="ml-model-card-actions">';
            html += `<a class="btn btn-sm btn-primary" href="/models/${model.id}/predict">Predict new data</a>`;
            html += `<button class="btn btn-sm" data-model-view="${model.id}" title="View details">View</button>`;
            html += `<button class="btn btn-sm" data-model-download="${model.id}" title="Download model">Download</button>`;
            html += `<a href="/models/${model.id}/explain" class="btn btn-sm" style="background:#6366F1;color:#fff;text-decoration:none;" title="Explain model with XAI">Explain</a>`;
            html += `<button class="btn btn-sm" style="color:#DC2626;" data-model-delete="${model.id}" title="Delete model">Delete</button>`;
            html += '</div>';

            html += '</div>';
        }
        html += '</div>';

        container.innerHTML = html;

        // Rebind model management events
        this.bindModelManagementEvents();
    },

    async deleteModel(modelId) {
        try {
            const resp = await fetch(`${this.modelsApiBase}/${modelId}/delete`, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } });
            const data = await resp.json();

            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }

            this.showToast('Model deleted.', 'success');
            await this.loadModelsList();
        } catch (e) {
            this.showToast('Failed to delete model.', 'error');
        }
    },

    downloadModel(modelId) {
        window.open(`${this.modelsApiBase}/${modelId}/download`, '_blank');
    },

    async viewModel(modelId) {
        try {
            const resp = await fetch(`${this.modelsApiBase}/${modelId}`);
            const data = await resp.json();

            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }

            // Show model details in a modal or inline
            const modalBody = document.getElementById('mlModelDetailBody');
            if (modalBody) {
                let html = '<div class="ml-analysis-card">';
                const fields = ['name', 'algorithm', 'problem_type', 'dataset_name', 'score', 'description', 'created_at', 'metrics', 'features'];
                for (const field of fields) {
                    if (data[field] !== undefined && data[field] !== null) {
                        const label = field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                        let val = data[field];
                        if (typeof val === 'object') val = JSON.stringify(val, null, 2);
                        html += `<div class="ml-analysis-row"><span class="ml-analysis-label">${label}:</span><span>${this.escapeHtml(String(val))}</span></div>`;
                    }
                }
                html += '</div>';
                modalBody.innerHTML = html;

                if (typeof openModal === 'function') {
                    openModal('mlModelDetailModal');
                } else {
                    const modal = document.getElementById('mlModelDetailModal');
                    if (modal) modal.style.display = 'flex';
                }
            }
        } catch (e) {
            this.showToast('Failed to load model details.', 'error');
        }
    },

    // ── Error Handling ───────────────────────────────────

    showError(containerId, message) {
        const el = document.getElementById(containerId);
        if (el) {
            el.innerHTML = `<div class="ml-inline-error">${this.escapeHtml(message)}</div>`;
            el.style.display = 'block';
        }
    },

    clearError(containerId) {
        const el = document.getElementById(containerId);
        if (el) {
            el.innerHTML = '';
            el.style.display = '';
        }
    },

    // ── Toast Notification ───────────────────────────────────

    showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = 'ml-toast ml-toast-' + (type || 'info');
        toast.textContent = message;
        document.body.appendChild(toast);
        // Trigger reflow then add visible class
        requestAnimationFrame(() => {
            toast.classList.add('ml-toast-visible');
        });
        setTimeout(() => {
            toast.classList.remove('ml-toast-visible');
            setTimeout(() => toast.remove(), 350);
        }, 3500);
    },

    // ── Confirm Action ───────────────────────────────────

    confirmAction(title, message, callback) {
        const titleEl = document.getElementById('mlConfirmTitle');
        const msgEl = document.getElementById('mlConfirmMessage');
        const btnEl = document.getElementById('mlConfirmActionBtn');

        if (titleEl) titleEl.textContent = title;
        if (msgEl) msgEl.textContent = message;

        if (btnEl) {
            const newBtn = btnEl.cloneNode(true);
            btnEl.parentNode.replaceChild(newBtn, btnEl);
            newBtn.id = 'mlConfirmActionBtn';
            newBtn.addEventListener('click', () => {
                if (typeof closeModal === 'function') {
                    closeModal('mlConfirmModal');
                } else {
                    const modal = document.getElementById('mlConfirmModal');
                    if (modal) modal.style.display = 'none';
                }
                callback();
            });
        }

        if (typeof openModal === 'function') {
            openModal('mlConfirmModal');
        } else {
            const modal = document.getElementById('mlConfirmModal');
            if (modal) modal.style.display = 'flex';
        }
    },

    async saveWorkspace() {
        if (this.isTraining) return this.showToast('Wait for training to finish.', 'error');
        const name = document.getElementById('workspaceName').value.trim();
        if (!name) return this.showToast('Enter a workspace name.', 'error');
        if (!await this.saveConfiguration()) return;
        const ui = Array.from(document.querySelectorAll('.ml-studio input, .ml-studio select')).filter(el => el.id && !['file','password','hidden'].includes(el.type) && el.id !== 'workspaceName').map(el => ({id:el.id,value:el.value,checked:el.checked}));
        try {
            const response = await fetch(`/api/datasets/${this.datasetId}/workspaces`, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()},body:JSON.stringify({name,ui})});
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not save workspace.');
            this.showToast('Workspace saved. Find it under Projects → Saved analysis workspaces.', 'success');
        } catch (error) { this.showToast(error.message, 'error'); }
    },

    async restoreWorkspace() {
        const id = new URLSearchParams(location.search).get('workspace');
        if (!id) return;
        try {
            const response = await fetch(`/api/workspaces/${encodeURIComponent(id)}`);
            if (!response.ok) throw new Error('Workspace unavailable.');
            const saved = await response.json();
            if (String(saved.dataset_id) !== String(this.datasetId)) throw new Error('Workspace belongs to another dataset.');
            for (const field of saved.ui) {
                const el = document.getElementById(field.id);
                if (!el || !el.closest('.ml-studio') || !['INPUT','SELECT'].includes(el.tagName) || ['file','hidden','password'].includes(el.type)) continue;
                if (['checkbox','radio'].includes(el.type)) el.checked = !!field.checked;
                else el.value = field.value;
            }
            this.selectedFeatures = saved.config.feature_columns || [];
            this.selectedAlgorithms = saved.config.selected_algorithms || [];
            const controlMap = {targetColumn:'target_column',problemType:'problem_type',mlScaling:'scaling',mlEncoding:'encoding',mlImputation:'imputation',mlTestSize:'test_size',mlCVFolds:'cv_folds',cvStrategy:'cv_strategy',randomState:'random_state',optimizationLevel:'optimization_level'};
            for (const [control, key] of Object.entries(controlMap)) {
                const el = document.getElementById(control);
                if (el) {
                    const value = String(saved.config[key] ?? '');
                    if (control === 'mlCVFolds' && !Array.from(el.options).some(option => option.value === value)) {
                        el.add(new Option(`${value}-Fold`, value));
                    }
                    el.value = value;
                }
            }
            document.getElementById('problemType').dataset.userSet = 'true';
            document.getElementById('mlAutoMLToggle').checked = saved.config.auto_mode;
            await this.onAutoMLToggle();
            this.renderProblemTypeInfo(saved.config.problem_type);
            document.getElementById('mlTestSizeLabel').textContent = `${Math.round(saved.config.test_size * 100)}%`;
            document.querySelectorAll('.ml-feature-check').forEach(el => { el.checked = this.selectedFeatures.includes(el.value); });
            this.updateFeatureTypeInfo();
            document.querySelectorAll('.ml-algo-check').forEach(el => { el.checked = this.selectedAlgorithms.includes(el.value); });
            document.getElementById('workspaceName').value = saved.name;
            const result = await fetch(`${this.apiBase}/configure`, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()},body:JSON.stringify(saved.config)});
            if (!result.ok) throw new Error('Could not restore settings while training is active.');
            const notice = document.getElementById('workspaceNotice');
            notice.textContent = `Restored ${saved.name}. Prepare data to train again. `;
            saved.charts.forEach((chart,index) => {
                const link = document.createElement('a');
                link.textContent = `Open chart: ${chart.name} `;
                link.href = `/workspaces/${id}/charts/${index}`;
                notice.appendChild(link);
            });
        } catch (error) { this.showToast(error.message, 'error'); }
    },

    // ── Utilities ───────────────────────────────────

    setButtonLoading(btn, loading) {
        if (!btn) return;
        if (loading) {
            btn.dataset.originalText = btn.textContent;
            btn.textContent = 'Loading...';
            btn.classList.add('btn-loading');
            btn.disabled = true;
        } else {
            btn.textContent = btn.dataset.originalText || btn.textContent;
            btn.classList.remove('btn-loading');
            btn.disabled = false;
        }
    },

    formatScore(score) {
        if (score === undefined || score === null) return '\u2014';
        if (typeof score === 'string') return score;
        return score.toFixed(4);
    },

    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        const s = String(str);
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    },

    truncateText(text, maxLen) {
        if (!text) return '';
        const s = String(text);
        return s.length > maxLen ? s.slice(0, maxLen - 1) + '\u2026' : s;
    },
};

// ── ML Models List Page Controller ─────────────────────────────

const ModelsPage = {
    async init() {
        await MLStudio.loadModelsList();
    },
};

// ── Initialization ───────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Determine which page we're on
    const isMLStudio = document.getElementById('mlStepBar') || document.querySelector('.ml-step-panel');
    const isModelsList = document.getElementById('mlModelsList');

    if (isModelsList) {
        ModelsPage.init();
    } else if (isMLStudio) {
        MLStudio.setupProblemTypeUI();
        MLStudio.init();
    }
});

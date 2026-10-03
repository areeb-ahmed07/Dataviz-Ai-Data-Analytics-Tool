/**
 * DataViz Pro — Cleaning Studio JavaScript
 * Handles all cleaning operations, preview, and UI interactions.
 */

// CSRF token helper
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return null;
}

const CleaningApp = {
    datasetId: DATASET_ID,
    apiBase: API_BASE,
    detectionData: null,
    columnInfo: null,
    currentTool: null,

    // ── Initialization ────────────────────────────────────────────

    async init() {
        await this.detectProblems();
        await this.loadPreviewData();
        await this.loadHistory();
        this.bindEvents();
    },

    bindEvents() {
        // Tool section toggles
        document.querySelectorAll('.tool-section-header').forEach(header => {
            header.addEventListener('click', () => {
                const tool = header.dataset.tool;
                this.toggleTool(tool);
            });
        });

        // Reset button
        document.getElementById('btnResetAll').addEventListener('click', () => {
            this.confirmAction('Reset All Changes?', 'All cleaning operations will be undone and the dataset will return to its original state.', () => {
                this.reset();
            });
        });

        // Save button
        document.getElementById('btnSaveDataset').addEventListener('click', () => {
            this.showSaveModal();
        });
    },

    toggleTool(tool) {
        const header = document.querySelector(`[data-tool="${tool}"]`);
        const bodyId = 'toolBody' + tool.charAt(0).toUpperCase() + tool.slice(1);
        const body = document.getElementById(bodyId);
        if (!header || !body) return;

        const isActive = header.classList.contains('active');

        // Close all
        document.querySelectorAll('.tool-section-header').forEach(h => h.classList.remove('active'));
        document.querySelectorAll('.tool-section-body').forEach(b => b.style.display = 'none');

        if (!isActive) {
            header.classList.add('active');
            body.style.display = 'block';
            this.currentTool = tool;
            this.loadToolConfig(tool);
        } else {
            this.currentTool = null;
        }
    },

    // ── Detection ─────────────────────────────────────────────────

    async detectProblems() {
        try {
            const resp = await fetch(`${this.apiBase}/detect`);
            this.detectionData = await resp.json();

            if (this.detectionData.error) {
                document.getElementById('cleaningDatasetInfo').textContent = 'Error loading';
                return;
            }

            // Update header info
            document.getElementById('cleaningDatasetInfo').textContent =
                `${this.detectionData.rows.toLocaleString()} rows \u2022 ${this.detectionData.columns} columns`;

            // Update quality bar (original values)
            this.updateQualityBar(
                this.detectionData.rows,
                this.detectionData.columns,
                this.detectionData.missing.missing_cells,
                this.detectionData.duplicates.duplicate_count,
                null, null, null, null
            );

            // Update badges
            const missingCols = Object.keys(this.detectionData.missing.columns_summary || {}).length;
            this.setBadge('badgeMissing', missingCols, missingCols > 0 ? 'problems' : 'zero');
            this.setBadge('badgeDuplicates', this.detectionData.duplicates.duplicate_count, this.detectionData.duplicates.duplicate_count > 0 ? 'problems' : 'zero');

            const totalOutliers = Object.values(this.detectionData.outliers || {}).reduce((sum, o) => sum + o.outlier_count, 0);
            this.setBadge('badgeOutliers', totalOutliers, totalOutliers > 0 ? 'problems' : 'zero');

        } catch (e) {
            console.error('Detection failed:', e);
        }
    },

    updateQualityBar(rowsO, colsO, missO, dupO, rowsC, colsC, missC, dupC) {
        this._setQS('qsRowsOriginal', rowsO);
        this._setQS('qsColumnsOriginal', colsO);
        this._setQS('qsMissingOriginal', missO);
        this._setQS('qsDuplicatesOriginal', dupO);

        if (rowsC !== null) {
            this._setQS('qsRowsCurrent', rowsC);
            this._setQS('qsColumnsCurrent', colsC);
            this._setQS('qsMissingCurrent', missC);
            this._setQS('qsDuplicatesCurrent', dupC);

            this._showArrow('qsRowsArrow', rowsO !== rowsC);
            this._showArrow('qsColumnsArrow', colsO !== colsC);
            this._showArrow('qsMissingArrow', missO !== missC);
            this._showArrow('qsDuplicatesArrow', dupO !== dupC);

            this._colorChange('qsRowsCurrent', rowsC, rowsO, true);
            this._colorChange('qsColumnsCurrent', colsC, colsO, false);
            this._colorChange('qsMissingCurrent', missC, missO, false);
            this._colorChange('qsDuplicatesCurrent', dupC, dupO, false);
        } else {
            document.querySelectorAll('.qs-arrow').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.qs-current').forEach(el => el.style.display = 'none');
        }
    },

    _setQS(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val !== null ? val.toLocaleString() : '—';
    },

    _showArrow(id, show) {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? 'inline' : 'none';
    },

    _colorChange(id, current, original, lowerIsBetter) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove('qs-improved', 'qs-worsened', 'qs-changed');
        if (current < original && lowerIsBetter) el.classList.add('qs-improved');
        else if (current > original && lowerIsBetter) el.classList.add('qs-worsened');
        else if (current !== original) el.classList.add('qs-changed');
    },

    setBadge(id, value, type) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = typeof value === 'number' ? value.toLocaleString() : value;
            el.className = 'tool-badge ' + (type || '');
        }
    },

    // ── Tool Config Loading ──────────────────────────────────────

    async loadToolConfig(tool) {
        if (!this.detectionData) return;

        switch (tool) {
            case 'missing': this.renderMissingConfig(); break;
            case 'duplicates': this.renderDuplicatesConfig(); break;
            case 'outliers': this.renderOutliersConfig(); break;
            case 'datatypes': this.renderDataTypesConfig(); break;
            case 'columns': await this.renderColumnsConfig(); break;
            case 'encoding': await this.renderEncodingConfig(); break;
            case 'scaling': await this.renderScalingConfig(); break;
            case 'transform': await this.renderTransformConfig(); break;
            case 'features': await this.renderFeaturesConfig(); break;
        }
    },

    renderMissingConfig() {
        const d = this.detectionData;
        const missing = d.missing.columns_summary || {};
        const colTypes = d.column_types || [];

        if (Object.keys(missing).length === 0) {
            document.getElementById('missingConfig').innerHTML = '<div class="info-text">No missing values found in this dataset.</div>';
            return;
        }

        let html = '<table><thead><tr><th>Column</th><th>Missing</th><th>%</th><th>Type</th><th>Strategy</th></tr></thead><tbody>';
        for (const [col, info] of Object.entries(missing)) {
            const colType = colTypes.find(c => c.name === col);
            const dtype = colType ? colType.inferred_type : 'unknown';
            const strategies = dtype === 'numeric'
                ? '<option value="median">Median</option><option value="mean">Mean</option><option value="constant">Constant</option>'
                : '<option value="mode">Mode</option><option value="constant">Constant</option>';
            html += `<tr>
                <td><strong>${col}</strong></td>
                <td>${info.missing_count.toLocaleString()}</td>
                <td>${info.missing_percentage}%</td>
                <td><span class="dtype-badge">${dtype}</span></td>
                <td><select id="missing_${col}" class="missing-strategy">${strategies}<option value="drop">Drop rows</option></select>
                    <input type="text" id="missing_const_${col}" placeholder="Value" class="missing-const" style="display:none;width:80px;margin-top:4px;">
                </td>
            </tr>`;
        }
        html += '</tbody></table>';
        html += '<div class="info-text">Different strategies can be selected per column. Preview before applying.</div>';

        document.getElementById('missingConfig').innerHTML = html;

        // Show constant input when strategy is "constant"
        document.querySelectorAll('.missing-strategy').forEach(sel => {
            sel.addEventListener('change', function() {
                const col = this.id.replace('missing_', '');
                const constInput = document.getElementById('missing_const_' + col);
                if (constInput) constInput.style.display = this.value === 'constant' ? 'block' : 'none';
            });
        });
    },

    renderDuplicatesConfig() {
        const d = this.detectionData;
        const dupCount = d.duplicates.duplicate_count;
        const dupPct = d.duplicates.duplicate_percentage;

        let html = `<div style="margin:0.75rem 0;">
            <div class="preview-metrics">
                <div class="preview-metric"><div class="preview-metric-label">Duplicate Rows</div><div class="preview-metric-value worsened">${dupCount.toLocaleString()}</div></div>
                <div class="preview-metric"><div class="preview-metric-label">Percentage</div><div class="preview-metric-value worsened">${dupPct}%</div></div>
            </div>
            <p>${dupCount > 0
                ? `<strong>${dupCount.toLocaleString()}</strong> duplicate rows will be removed. Rows: ${d.rows.toLocaleString()} → ${(d.rows - dupCount).toLocaleString()}`
                : 'No duplicate rows found.'}</p>
        </div>`;

        document.getElementById('duplicatesConfig').innerHTML = html;
    },

    renderOutliersConfig() {
        const d = this.detectionData;
        const outliers = d.outliers || {};
        const entries = Object.entries(outliers).filter(([_, v]) => v.outlier_count > 0);

        if (entries.length === 0) {
            document.getElementById('outliersConfig').innerHTML = '<div class="info-text">No outliers detected using IQR method.</div>';
            return;
        }

        let html = '<table><thead><tr><th>Column</th><th>Outliers</th><th>%</th><th>Select</th></tr></thead><tbody>';
        for (const [col, info] of entries) {
            html += `<tr>
                <td><strong>${col}</strong></td>
                <td>${info.outlier_count.toLocaleString()}</td>
                <td>${info.outlier_percentage}%</td>
                <td><input type="checkbox" class="outlier-col" value="${col}" checked></td>
            </tr>`;
        }
        html += '</tbody></table>';
        html += '<div style="margin-top:0.5rem;">';
        html += '<label style="font-size:0.82rem;font-weight:600;">Action:</label> ';
        html += '<select id="outlierAction" style="padding:0.25rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        html += '<option value="cap">Cap / Winsorize</option>';
        html += '<option value="drop">Remove rows</option>';
        html += '</select></div>';
        html += '<div class="info-text">Statistical outliers are not necessarily data errors. Review affected rows before removing.</div>';

        document.getElementById('outliersConfig').innerHTML = html;
    },

    renderDataTypesConfig() {
        const d = this.detectionData;
        const colTypes = d.column_types || [];

        let html = '<table><thead><tr><th>Column</th><th>Current</th><th>Detected</th><th>Convert To</th></tr></thead><tbody>';
        for (const col of colTypes) {
            const needsConversion = col.current_type !== col.inferred_type &&
                !(col.current_type === 'object' && col.inferred_type === 'categorical');
            html += `<tr${needsConversion ? ' style="background:#FFFBEB;"' : ''}>
                <td><strong>${col.name}</strong></td>
                <td><span class="dtype-badge">${col.current_type}</span></td>
                <td><span class="dtype-badge">${col.inferred_type}</span></td>
                <td>
                    <select id="dtype_${col.name}" class="dtype-select">
                        <option value="">No change</option>
                        ${col.inferred_type === 'numeric' ? '<option value="float">Float</option><option value="int">Integer</option>' : ''}
                        ${col.inferred_type === 'datetime' ? '<option value="datetime">Datetime</option>' : ''}
                        ${col.inferred_type === 'categorical' ? '<option value="category">Category</option>' : ''}
                        <option value="str">String</option>
                    </select>
                </td>
            </tr>`;
        }
        html += '</tbody></table>';
        html += '<div class="tool-actions"><button class="btn btn-primary btn-sm" onclick="CleaningApp.previewDtypeConversion()">Preview</button>';
        html += '<button class="btn btn-sm" onclick="CleaningApp.applyDtypeConversions()">Apply</button></div>';

        document.getElementById('dataTypesConfig').innerHTML = html;
    },

    async renderColumnsConfig() {
        try {
            const resp = await fetch(`${this.apiBase}/columns`);
            this.columnInfo = await resp.json();
        } catch (e) { return; }

        if (!this.columnInfo || this.columnInfo.error) return;
        const cols = this.columnInfo.columns || [];

        let html = '<div style="margin-bottom:0.5rem;"><strong style="font-size:0.85rem;">Rename Column</strong></div>';
        html += '<div style="display:flex;gap:0.5rem;margin-bottom:1rem;">';
        html += '<select id="renameCol" style="flex:1;padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        for (const c of cols) html += `<option value="${c.name}">${c.name}</option>`;
        html += '</select>';
        html += '<input type="text" id="renameNew" placeholder="New name" style="flex:1;padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        html += '<button class="btn btn-primary btn-sm" onclick="CleaningApp.applyRename()">Rename</button>';
        html += '</div>';

        // Constant columns
        const constantCols = cols.filter(c => c.is_constant);
        if (constantCols.length > 0) {
            html += '<div style="margin-bottom:0.5rem;"><strong style="font-size:0.85rem;">Constant Columns</strong></div>';
            html += '<div class="warning-text">';
            for (const c of constantCols) {
                html += `${c.name}: All values are identical.<br>`;
            }
            html += '</div>';
            html += '<button class="btn btn-sm" onclick="CleaningApp.applyRemoveConstants()" style="margin-bottom:1rem;">Remove Constant Columns</button>';
        }

        // Remove columns
        html += '<div style="margin-bottom:0.5rem;"><strong style="font-size:0.85rem;">Remove Columns</strong></div>';
        html += '<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.5rem;">';
        for (const c of cols) {
            const isId = c.unique_count === this.columnInfo.total_rows && this.columnInfo.total_rows > 1;
            html += `<label class="checkbox-row" style="font-size:0.82rem;">
                <input type="checkbox" class="remove-col-check" value="${c.name}">
                ${c.name} ${isId ? '<span style="color:#D97706;font-size:0.72rem;">(ID)</span>' : ''}
            </label>`;
        }
        html += '</div>';
        html += '<button class="btn btn-sm" onclick="CleaningApp.applyRemoveColumns()" style="color:#DC2626;">Remove Selected</button>';

        document.getElementById('columnsConfig').innerHTML = html;
    },

    async renderEncodingConfig() {
        try {
            if (!this.columnInfo) {
                const resp = await fetch(`${this.apiBase}/columns`);
                this.columnInfo = await resp.json();
            }
        } catch (e) { return; }

        if (!this.columnInfo || this.columnInfo.error) return;
        const cols = (this.columnInfo.columns || []).filter(c => c.inferred_type === 'categorical');

        if (cols.length === 0) {
            document.getElementById('encodingConfig').innerHTML = '<div class="info-text">No categorical columns found.</div>';
            return;
        }

        let html = '<div style="margin-bottom:0.5rem;">';
        html += '<label style="font-size:0.82rem;font-weight:600;">Method:</label> ';
        html += '<select id="encodeMethod" style="padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        html += '<option value="onehot">One-Hot Encoding</option>';
        html += '<option value="ordinal">Label Encoding</option>';
        html += '</select></div>';

        html += '<table><thead><tr><th>Column</th><th>Unique</th><th>Select</th></tr></thead><tbody>';
        for (const c of cols) {
            const warning = c.unique_count > 20;
            html += `<tr${warning ? ' style="background:#FFFBEB;"' : ''}>
                <td><strong>${c.name}</strong>${warning ? '<br><span style="color:#D97706;font-size:0.72rem;">High cardinality!</span>' : ''}</td>
                <td>${c.unique_count.toLocaleString()}</td>
                <td><input type="checkbox" class="encode-col" value="${c.name}" ${!warning ? 'checked' : ''}></td>
            </tr>`;
        }
        html += '</tbody></table>';

        if (cols.some(c => c.unique_count > 20)) {
            html += '<div class="warning-text">High-cardinality columns may create many features with one-hot encoding.</div>';
        }

        document.getElementById('encodingConfig').innerHTML = html;
    },

    async renderScalingConfig() {
        try {
            if (!this.columnInfo) {
                const resp = await fetch(`${this.apiBase}/columns`);
                this.columnInfo = await resp.json();
            }
        } catch (e) { return; }

        if (!this.columnInfo || this.columnInfo.error) return;
        const cols = (this.columnInfo.columns || []).filter(c => c.inferred_type === 'numeric');

        if (cols.length === 0) {
            document.getElementById('scalingConfig').innerHTML = '<div class="info-text">No numeric columns found.</div>';
            return;
        }

        let html = '<div style="margin-bottom:0.5rem;">';
        html += '<label style="font-size:0.82rem;font-weight:600;">Method:</label> ';
        html += '<select id="scaleMethod" style="padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        html += '<option value="standard">Standardization (mean≈0, std≈1)</option>';
        html += '<option value="minmax">Min-Max Scaling (0-1)</option>';
        html += '<option value="robust">Robust Scaling</option>';
        html += '</select></div>';

        html += '<table><thead><tr><th>Column</th><th>Select</th></tr></thead><tbody>';
        for (const c of cols) {
            html += `<tr><td><strong>${c.name}</strong></td>
                <td><input type="checkbox" class="scale-col" value="${c.name}" checked></td></tr>`;
        }
        html += '</tbody></table>';

        document.getElementById('scalingConfig').innerHTML = html;
    },

    async renderTransformConfig() {
        try {
            if (!this.columnInfo) {
                const resp = await fetch(`${this.apiBase}/columns`);
                this.columnInfo = await resp.json();
            }
        } catch (e) { return; }

        if (!this.columnInfo || this.columnInfo.error) return;
        const cols = (this.columnInfo.columns || []).filter(c => c.inferred_type === 'numeric');

        if (cols.length === 0) {
            document.getElementById('transformConfig').innerHTML = '<div class="info-text">No numeric columns found.</div>';
            return;
        }

        let html = '<div style="margin-bottom:0.5rem;">';
        html += '<label style="font-size:0.82rem;font-weight:600;">Transform:</label> ';
        html += '<select id="transformMethod" style="padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        html += '<option value="log">Log Transform</option>';
        html += '<option value="sqrt">Square Root Transform</option>';
        html += '</select></div>';

        html += '<div style="margin-bottom:0.5rem;">';
        html += '<label style="font-size:0.82rem;font-weight:600;">Column:</label> ';
        html += '<select id="transformCol" style="flex:1;padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;">';
        for (const c of cols) html += `<option value="${c.name}">${c.name}</option>`;
        html += '</select></div>';

        document.getElementById('transformConfig').innerHTML = html;
    },

    async renderFeaturesConfig() {
        try {
            if (!this.columnInfo) {
                const resp = await fetch(`${this.apiBase}/columns`);
                this.columnInfo = await resp.json();
            }
        } catch (e) { return; }

        if (!this.columnInfo || this.columnInfo.error) return;
        const cols = this.columnInfo.columns || [];

        let html = '<div style="margin-bottom:0.5rem;"><strong style="font-size:0.85rem;">Target Column</strong></div>';
        html += '<select id="targetCol" style="width:100%;padding:0.3rem 0.5rem;border:1px solid #E5E7EB;border-radius:6px;font-size:0.82rem;margin-bottom:1rem;">';
        html += '<option value="">None</option>';
        for (const c of cols) html += `<option value="${c.name}">${c.name} (${c.inferred_type})</option>`;
        html += '</select>';

        html += '<div style="margin-bottom:0.5rem;"><strong style="font-size:0.85rem;">Feature Selection</strong></div>';
        html += '<div style="max-height:200px;overflow-y:auto;">';
        for (const c of cols) {
            html += `<label class="checkbox-row" style="font-size:0.82rem;">
                <input type="checkbox" class="feature-col-check" value="${c.name}" checked>
                ${c.name} <span style="color:#9CA3AF;">(${c.inferred_type})</span>
            </label>`;
        }
        html += '</div>';

        document.getElementById('featuresConfig').innerHTML = html;
    },

    // ── Preview / Apply Operations ────────────────────────────────

    async previewOperation(operation) {
        this.showPreviewLoading();
        try {
            const resp = await fetch(`${this.apiBase}/preview`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(operation)
            });
            const data = await resp.json();
            if (data.error) {
                this.showPreviewError(data.error);
                return;
            }
            this.renderPreview(data);
        } catch (e) {
            this.showPreviewError('Network error. Please try again.');
        }
    },

    async applyOperation(operation) {
        try {
            const resp = await fetch(`${this.apiBase}/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(operation)
            });
            const data = await resp.json();
            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }
            this.showToast(data.details || 'Operation applied.', 'success');
            await this.refreshAll();
        } catch (e) {
            this.showToast('Network error. Please try again.', 'error');
        }
    },

    // ── Missing Values ────────────────────────────────────────────

    getMissingOperation() {
        const colStrategies = {};
        document.querySelectorAll('.missing-strategy').forEach(sel => {
            const col = sel.id.replace('missing_', '');
            const strategy = sel.value;
            if (strategy === 'drop') return;
            colStrategies[col] = strategy;
        });
        return {
            type: 'impute',
            column_strategies: colStrategies,
            default_numeric_strategy: 'median',
            default_categorical_strategy: 'mode',
            constant_value: 'Missing',
        };
    },

    previewMissing() { this.previewOperation(this.getMissingOperation()); },
    applyMissing() { this.applyOperation(this.getMissingOperation()); },

    // ── Duplicates ────────────────────────────────────────────────

    previewDuplicates() { this.previewOperation({ type: 'remove_duplicates', keep: 'first' }); },
    applyDuplicates() { this.applyOperation({ type: 'remove_duplicates', keep: 'first' }); },

    // ── Outliers ──────────────────────────────────────────────────

    getOutlierOperation() {
        const cols = Array.from(document.querySelectorAll('.outlier-col:checked')).map(c => c.value);
        const action = document.getElementById('outlierAction')?.value || 'cap';
        return { type: 'handle_outliers', method: 'iqr', action, columns: cols };
    },

    previewOutliers() { this.previewOperation(this.getOutlierOperation()); },
    applyOutliers() { this.applyOperation(this.getOutlierOperation()); },

    // ── Data Types ───────────────────────────────────────────────

    previewDtypeConversion() {
        const sel = document.querySelector('.dtype-select');
        if (!sel || !sel.value) { this.showToast('Select a conversion first.', 'error'); return; }
        this.previewOperation({ type: 'convert_dtype', column: sel.id.replace('dtype_', ''), target_type: sel.value });
    },

    async applyDtypeConversions() {
        for (const sel of document.querySelectorAll('.dtype-select')) {
            if (sel.value) {
                await this.applyOperation({ type: 'convert_dtype', column: sel.id.replace('dtype_', ''), target_type: sel.value });
            }
        }
    },

    // ── Column Management ─────────────────────────────────────────

    applyRename() {
        const col = document.getElementById('renameCol')?.value;
        const newName = document.getElementById('renameNew')?.value;
        if (!col || !newName) { this.showToast('Select column and enter new name.', 'error'); return; }
        this.applyOperation({ type: 'rename_column', column: col, new_name: newName });
    },

    applyRemoveColumns() {
        const cols = Array.from(document.querySelectorAll('.remove-col-check:checked')).map(c => c.value);
        if (!cols.length) { this.showToast('Select columns to remove.', 'error'); return; }
        this.confirmAction('Remove Columns?', `Remove ${cols.length} column(s)? This cannot be undone for applied operations.`, () => {
            this.applyOperation({ type: 'remove_columns', columns: cols });
        });
    },

    applyRemoveConstants() {
        this.applyOperation({ type: 'remove_constant_columns' });
    },

    applyKeepColumns() {
        const cols = Array.from(document.querySelectorAll('.feature-col-check:checked')).map(c => c.value);
        if (!cols.length) { this.showToast('Select at least one column.', 'error'); return; }
        this.applyOperation({ type: 'keep_columns', columns: cols });
    },

    // ── Encoding ─────────────────────────────────────────────────

    getEncodingOperation() {
        const cols = Array.from(document.querySelectorAll('.encode-col:checked')).map(c => c.value);
        const strategy = document.getElementById('encodeMethod')?.value || 'onehot';
        return { type: 'encode', strategy, columns: cols, drop_first: true };
    },

    previewEncoding() { this.previewOperation(this.getEncodingOperation()); },
    applyEncoding() { this.applyOperation(this.getEncodingOperation()); },

    // ── Scaling ───────────────────────────────────────────────────

    getScalingOperation() {
        const cols = Array.from(document.querySelectorAll('.scale-col:checked')).map(c => c.value);
        const strategy = document.getElementById('scaleMethod')?.value || 'standard';
        return { type: 'scale', strategy, columns: cols };
    },

    previewScaling() { this.previewOperation(this.getScalingOperation()); },
    applyScaling() { this.applyOperation(this.getScalingOperation()); },

    // ── Transform ─────────────────────────────────────────────────

    getTransformOperation() {
        const col = document.getElementById('transformCol')?.value;
        const method = document.getElementById('transformMethod')?.value || 'log';
        return { type: 'transform', column: col, method };
    },

    previewTransform() { this.previewOperation(this.getTransformOperation()); },
    applyTransform() { this.applyOperation(this.getTransformOperation()); },

    // ── Undo / Reset ─────────────────────────────────────────────

    async undoLast() {
        try {
            const resp = await fetch(`${this.apiBase}/undo`, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } });
            const data = await resp.json();
            if (data.error) { this.showToast(data.error, 'error'); return; }
            this.showToast(data.message, 'success');
            await this.refreshAll();
        } catch (e) {
            this.showToast('Network error.', 'error');
        }
    },

    async reset() {
        try {
            const resp = await fetch(`${this.apiBase}/reset`, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } });
            const data = await resp.json();
            if (data.error) { this.showToast(data.error, 'error'); return; }
            this.showToast(data.message, 'success');
            await this.refreshAll();
        } catch (e) {
            this.showToast('Network error.', 'error');
        }
    },

    // ── History ────────────────────────────────────────────────────

    async loadHistory() {
        try {
            const resp = await fetch(`${this.apiBase}/history`);
            const data = await resp.json();
            const container = document.getElementById('historyContent');

            if (!data || data.length === 0) {
                container.innerHTML = '<div class="empty-state compact"><p>No operations applied yet.</p></div>';
                return;
            }

            let html = '';
            for (const entry of data) {
                html += `<div class="history-item">
                    <div class="history-step">${entry.step}</div>
                    <div class="history-detail">
                        <div class="history-operation">${entry.operation}</div>
                        <div class="history-desc">${entry.details}</div>
                        <div class="history-meta">${entry.rows_before} → ${entry.rows_after} rows &bull; ${entry.timestamp}</div>
                    </div>
                </div>`;
            }
            container.innerHTML = html;
        } catch (e) {
            console.error('History load failed:', e);
        }
    },

    // ── Preview Data ──────────────────────────────────────────────

    async loadPreviewData() {
        try {
            const resp = await fetch(`${this.apiBase}/preview-data`);
            const data = await resp.json();
            if (data.error) return;

            const container = document.getElementById('dataPreviewTable');
            const cols = data.columns || [];
            const rows = data.rows || [];

            if (cols.length === 0) {
                container.innerHTML = '<div class="empty-state compact"><p>No data to display.</p></div>';
                return;
            }

            let html = '<table class="data-table"><thead><tr><th>#</th>';
            for (const c of cols) html += `<th>${c}</th>`;
            html += '</tr></thead><tbody>';
            for (let i = 0; i < rows.length; i++) {
                html += `<tr><td style="color:#9CA3AF;">${i}</td>`;
                for (const c of cols) {
                    const val = rows[i][c];
                    html += val === null || val === undefined
                        ? '<td class="null-cell">NaN</td>'
                        : `<td title="${String(val).replace(/"/g, '&quot;')}">${val}</td>`;
                }
                html += '</tr>';
            }
            html += '</tbody></table>';
            html += `<div style="padding:0.5rem;font-size:0.78rem;color:#9CA3AF;">Showing ${rows.length} of ${data.total_rows.toLocaleString()} rows</div>`;

            container.innerHTML = html;
        } catch (e) {
            console.error('Preview data load failed:', e);
        }
    },

    // ── Preview Rendering ─────────────────────────────────────────

    showPreviewLoading() {
        document.getElementById('previewContent').innerHTML = '<div style="padding:2rem;text-align:center;color:#9CA3AF;"><p>Loading preview...</p></div>';
    },

    showPreviewError(msg) {
        document.getElementById('previewContent').innerHTML = `<div style="padding:1rem;background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;color:#DC2626;font-size:0.85rem;">${msg}</div>`;
    },

    renderPreview(data) {
        const container = document.getElementById('previewContent');
        let html = '';

        // Metrics
        html += '<div class="preview-metrics">';
        html += `<div class="preview-metric"><div class="preview-metric-label">Rows</div><div class="preview-metric-value ${data.rows_before !== data.rows_after ? (data.rows_after < data.rows_before ? 'improved' : 'worsened') : ''}">${data.rows_before.toLocaleString()} → ${data.rows_after.toLocaleString()}</div></div>`;
        html += `<div class="preview-metric"><div class="preview-metric-label">Columns</div><div class="preview-metric-value">${data.columns_before} → ${data.columns_after}</div></div>`;
        html += `<div class="preview-metric"><div class="preview-metric-label">Missing</div><div class="preview-metric-value ${data.missing_after < data.missing_before ? 'improved' : ''}">${data.missing_before.toLocaleString()} → ${data.missing_after.toLocaleString()}</div></div>`;
        html += `<div class="preview-metric"><div class="preview-metric-label">Duplicates</div><div class="preview-metric-value ${data.duplicates_after < data.duplicates_before ? 'improved' : ''}">${data.duplicates_before.toLocaleString()} → ${data.duplicates_after.toLocaleString()}</div></div>`;
        html += '</div>';

        // Sample
        if (data.sample && data.sample.length > 0) {
            html += '<table class="preview-sample-table"><thead><tr><th>Row</th><th>Column</th><th>Before</th><th>After</th></tr></thead><tbody>';
            for (const s of data.sample) {
                const beforeVal = s.before === null ? '<span class="null-val">NaN</span>' : s.before;
                const afterVal = s.after === null ? '<span class="null-val">NaN</span>' : s.after;
                html += `<tr><td>${s.index}</td><td>${s.column}</td><td class="before-val">${beforeVal}</td><td class="after-val">${afterVal}</td></tr>`;
            }
            html += '</tbody></table>';
        }

        // Details
        if (data.details) {
            html += `<div style="margin-top:0.75rem;font-size:0.82rem;color:#6B7280;">${data.details}</div>`;
        }

        container.innerHTML = html;
    },

    // ── Refresh ───────────────────────────────────────────────────

    async refreshPreview() {
        await this.loadPreviewData();
    },

    async refreshAll() {
        await this.detectProblems();
        await this.loadPreviewData();
        await this.loadHistory();
        // Reload current tool config
        if (this.currentTool) {
            this.columnInfo = null;
            this.loadToolConfig(this.currentTool);
        }
    },

    // ── Save ─────────────────────────────────────────────────────

    showSaveModal() {
        const summary = document.getElementById('saveSummary');
        summary.innerHTML = '<p>Loading summary...</p>';
        document.getElementById('saveDatasetName').value = '';

        fetch(`${this.apiBase}/history`).then(r => r.json()).then(history => {
            fetch(`${this.apiBase}/preview-data`).then(r => r.json()).then(data => {
                if (history.length === 0) {
                    summary.innerHTML = '<p class="warning-text">No cleaning operations have been applied yet.</p>';
                    return;
                }
                let html = '<div class="preview-metrics">';
                html += `<div class="preview-metric"><div class="preview-metric-label">Original</div><div class="preview-metric-value">${data.original_rows?.toLocaleString()} rows × ${data.original_columns} cols</div></div>`;
                html += `<div class="preview-metric"><div class="preview-metric-label">Cleaned</div><div class="preview-metric-value improved">${data.total_rows?.toLocaleString()} rows × ${data.total_columns} cols</div></div>`;
                html += `<div class="preview-metric"><div class="preview-metric-label">Operations</div><div class="preview-metric-value">${history.length}</div></div>`;
                html += '</div>';
                summary.innerHTML = html;
            });
        });

        openModal('saveModal');
    },

    async confirmSave() {
        const name = document.getElementById('saveDatasetName').value.trim();
        try {
            const resp = await fetch(`${this.apiBase}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ name: name || null })
            });
            const data = await resp.json();
            if (data.error) {
                this.showToast(data.error, 'error');
                return;
            }
            closeModal('saveModal');
            this.showToast(data.message, 'success');
            // Redirect to the new dataset
            if (data.id) {
                setTimeout(() => {
                    window.location.href = `/datasets/${data.id}`;
                }, 1000);
            }
        } catch (e) {
            this.showToast('Failed to save dataset.', 'error');
        }
    },

    // ── Utilities ─────────────────────────────────────────────────

    confirmAction(title, message, callback) {
        document.getElementById('confirmTitle').textContent = title;
        document.getElementById('confirmMessage').textContent = message;
        const btn = document.getElementById('btnConfirmAction');
        // Clone to remove old listeners
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        newBtn.addEventListener('click', () => {
            closeModal('confirmModal');
            callback();
        });
        openModal('confirmModal');
    },

    showToast(message, type) {
        // Use flash-style toast
        const toast = document.createElement('div');
        toast.style.cssText = `position:fixed;top:1rem;right:1rem;z-index:9999;padding:0.75rem 1.25rem;border-radius:8px;font-size:0.875rem;font-weight:500;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;max-width:400px;`;
        toast.style.background = type === 'error' ? '#DC2626' : type === 'success' ? '#059669' : '#6366F1';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3500);
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    CleaningApp.init();
});

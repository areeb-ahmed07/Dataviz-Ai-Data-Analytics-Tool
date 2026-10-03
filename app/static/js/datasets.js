/**
 * DataViz Pro — Datasets JavaScript (Phase 4)
 *
 * Upload drag & drop, file selection, search filtering,
 * tab switching, delete confirmation, table sorting.
 */

(function () {
    'use strict';

    // ── Upload Zone: Drag & Drop ─────────────────────────────────
    var uploadZone = document.getElementById('uploadZone');
    var fileInput = document.getElementById('fileInput');
    var fileInfo = document.getElementById('fileInfo');
    var fileName = document.getElementById('fileName');
    var removeFileBtn = document.getElementById('removeFile');
    var uploadActions = document.getElementById('uploadActions');
    var uploadForm = document.getElementById('uploadForm');
    var uploadBtn = document.getElementById('uploadBtn');
    var uploadLoading = document.getElementById('uploadLoading');

    if (uploadZone && fileInput) {
        // Drag events
        ['dragenter', 'dragover'].forEach(function (evt) {
            uploadZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                uploadZone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(function (evt) {
            uploadZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                uploadZone.classList.remove('drag-over');
            });
        });

        uploadZone.addEventListener('drop', function (e) {
            var files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelected(files[0]);
            }
        });

        fileInput.addEventListener('change', function () {
            if (fileInput.files.length > 0) {
                handleFileSelected(fileInput.files[0]);
            }
        });
    }

    function handleFileSelected(file) {
        if (!file) return;
        fileName.textContent = file.name;
        fileInfo.style.display = '';
        uploadActions.style.display = '';
        uploadZone.style.display = 'none';
    }

    if (removeFileBtn) {
        removeFileBtn.addEventListener('click', function () {
            if (fileInput) fileInput.value = '';
            fileInfo.style.display = 'none';
            uploadActions.style.display = 'none';
            uploadZone.style.display = '';
        });
    }

    // Upload form submit — show loading steps
    if (uploadForm && uploadBtn && uploadLoading) {
        uploadForm.addEventListener('submit', function () {
            // Disable button and show loading
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.6';
            uploadActions.style.display = 'none';
            fileInfo.style.display = 'none';
            uploadLoading.style.display = '';

            // Animate through steps
            var steps = ['step-validate', 'step-load', 'step-profile', 'step-save'];
            var stepEls = steps.map(function (id) { return document.getElementById(id); });

            function activateStep(index) {
                stepEls.forEach(function (el, i) {
                    if (!el) return;
                    el.classList.remove('active', 'done');
                    if (i < index) el.classList.add('done');
                    if (i === index) el.classList.add('active');
                });
            }

            activateStep(0);
            setTimeout(function () { activateStep(1); }, 800);
            setTimeout(function () { activateStep(2); }, 1600);
            setTimeout(function () { activateStep(3); }, 2400);
        });
    }

    // ── Dataset Search (client-side filtering) ────────────────────
    var searchInput = document.getElementById('datasetSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            var query = this.value.toLowerCase().trim();
            var cards = document.querySelectorAll('.dataset-card');
            var visibleCount = 0;

            cards.forEach(function (card) {
                var name = (card.getAttribute('data-name') || '').toLowerCase();
                var format = (card.getAttribute('data-format') || '').toLowerCase();
                if (!query || name.indexOf(query) !== -1 || format.indexOf(query) !== -1) {
                    card.style.display = '';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            // Update count display
            var countEl = document.querySelector('.dataset-count');
            if (countEl) {
                countEl.textContent = visibleCount + ' dataset' + (visibleCount !== 1 ? 's' : '');
            }
        });
    }

    // ── Delete Confirmation Modal ────────────────────────────────
    var deleteModal = document.getElementById('deleteModal');
    var deleteDatasetName = document.getElementById('deleteDatasetName');
    var deleteDatasetId = document.getElementById('deleteDatasetId');

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.btn-delete-ds');
        if (btn && deleteModal && deleteDatasetName) {
            var dsName = btn.getAttribute('data-name') || 'this dataset';
            var dsId = btn.getAttribute('data-id');

            deleteDatasetName.textContent = dsName;

            // Find the hidden form and set the action
            var form = deleteModal.querySelector('form');
            if (form && dsId) {
                form.action = '/datasets/' + dsId + '/delete';
            }

            openModal('deleteModal');
        }
    });

    // ── Detail Page Tab Switching ─────────────────────────────────
    var tabLinks = document.querySelectorAll('.detail-tab[data-tab]');
    tabLinks.forEach(function (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            var tabId = this.getAttribute('data-tab');

            // Hide all tab contents
            document.querySelectorAll('.detail-tab-content').forEach(function (content) {
                content.style.display = 'none';
            });

            // Show selected tab content
            var tabContent = document.getElementById('tab-' + tabId);
            if (tabContent) {
                tabContent.style.display = '';
            }

            // Update active tab
            tabLinks.forEach(function (l) { l.classList.remove('active'); });
            this.classList.add('active');
        });
    });

    // ── Preview Table Sort (client-side) ──────────────────────────
    var sortBtns = document.querySelectorAll('.col-sort-btn');
    sortBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var colName = this.getAttribute('data-col');
            var table = document.getElementById('previewTable');
            if (!table) return;

            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var headers = Array.from(table.querySelectorAll('thead th'));
            var colIndex = headers.findIndex(function (th) {
                return th.textContent.trim().startsWith(colName);
            });
            if (colIndex === -1) return;

            // Determine sort direction
            var isAsc = this.classList.toggle('sort-asc');
            this.classList.toggle('sort-desc', !isAsc);

            rows.sort(function (a, b) {
                var aText = a.cells[colIndex].textContent.trim();
                var bText = b.cells[colIndex].textContent.trim();

                // Try numeric sort
                var aNum = parseFloat(aText.replace(/,/g, ''));
                var bNum = parseFloat(bText.replace(/,/g, ''));
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return isAsc ? aNum - bNum : bNum - aNum;
                }

                // String sort
                return isAsc ? aText.localeCompare(bText) : bText.localeCompare(aText);
            });

            rows.forEach(function (row) { tbody.appendChild(row); });
        });
    });

    // ── Breadcrumb Update ─────────────────────────────────────────
    var breadcrumb = document.getElementById('topbarBreadcrumb');
    if (breadcrumb) {
        var currentPath = window.location.pathname;
        if (currentPath.indexOf('/datasets/upload') !== -1) {
            breadcrumb.innerHTML = '<span class="breadcrumb-item"><a href="' + window.location.origin + '/datasets" style="color:var(--color-text);text-decoration:none;">Datasets</a></span><span class="breadcrumb-sep">/</span><span class="breadcrumb-item">Upload</span>';
        } else if (currentPath.indexOf('/datasets/') !== -1) {
            var parts = currentPath.split('/').filter(Boolean);
            var dsId = parts[parts.length - 1];
            if (currentPath.indexOf('/preview') !== -1) {
                breadcrumb.innerHTML = '<span class="breadcrumb-item"><a href="' + window.location.origin + '/datasets" style="color:var(--color-text);text-decoration:none;">Datasets</a></span><span class="breadcrumb-sep">/</span><span class="breadcrumb-item">Preview</span>';
            }
        }
    }

})();

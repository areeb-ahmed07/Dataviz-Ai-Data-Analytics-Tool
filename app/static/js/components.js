/**
 * DataViz Pro — Components JavaScript (Phase 15)
 *
 * Modal open/close, toast notifications, loading states,
 * dropdown menus, and reusable UI utilities.
 */

(function () {
    'use strict';

    // ── Toast Notification System ─────────────────────────────────
    var Toast = {
        container: null,
        icons: {
            success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
            info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
        },

        init: function () {
            this.container = document.getElementById('toastContainer');
        },

        show: function (type, title, message, duration) {
            if (!this.container) this.init();
            if (!this.container) return;

            type = type || 'info';
            duration = duration || 5000;

            var toast = document.createElement('div');
            toast.className = 'toast toast-' + type;

            var iconHtml = this.icons[type] || this.icons.info;
            var progressStyle = 'animation-duration: ' + duration + 'ms';

            toast.innerHTML =
                '<span class="toast-icon">' + iconHtml + '</span>' +
                '<div class="toast-body">' +
                    (title ? '<div class="toast-title">' + title + '</div>' : '') +
                    (message ? '<div class="toast-message">' + message + '</div>' : '') +
                '</div>' +
                '<button class="toast-close" aria-label="Close">&times;</button>' +
                '<div class="toast-progress" style="' + progressStyle + '"></div>';

            this.container.appendChild(toast);

            var self = this;
            var timer = setTimeout(function () {
                self.dismiss(toast);
            }, duration);

            toast._timer = timer;

            // Close button
            var closeBtn = toast.querySelector('.toast-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', function () {
                    clearTimeout(toast._timer);
                    self.dismiss(toast);
                });
            }

            return toast;
        },

        dismiss: function (toast) {
            if (!toast || !toast.parentNode) return;
            toast.classList.add('removing');
            setTimeout(function () {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 250);
        },

        success: function (title, message, duration) {
            return this.show('success', title, message, duration);
        },
        error: function (title, message, duration) {
            return this.show('error', title, message, duration);
        },
        warning: function (title, message, duration) {
            return this.show('warning', title, message, duration);
        },
        info: function (title, message, duration) {
            return this.show('info', title, message, duration);
        },

        // Auto-show from flash data (if injected by server)
        fromFlash: function () {
            var flashData = document.querySelectorAll('[data-flash-type]');
            flashData.forEach(function (el) {
                var type = el.getAttribute('data-flash-type');
                var msg = el.textContent.trim();
                if (msg) {
                    Toast.show(type, '', msg, 4000);
                }
                el.remove();
            });
        }
    };

    // Expose globally
    window.Toast = Toast;

    // Auto-init and process flash messages
    document.addEventListener('DOMContentLoaded', function () {
        Toast.init();
        Toast.fromFlash();
    });

    // ── Modal Management ──────────────────────────────────────────
    window.openModal = function (id) {
        var modal = document.getElementById(id);
        if (!modal) return;
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';

        // Focus first focusable element
        var focusable = modal.querySelector('button, [href], input, select, textarea');
        if (focusable) focusable.focus();
    };

    window.closeModal = function (id) {
        var modal = document.getElementById(id);
        if (!modal) return;
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    };

    function closeAllModals() {
        var modals = document.querySelectorAll('.modal-overlay.active');
        modals.forEach(function (m) {
            m.classList.remove('active');
            m.setAttribute('aria-hidden', 'true');
        });
        document.body.style.overflow = '';
    }

    // Close on overlay click
    document.addEventListener('click', function (e) {
        if (e.target.classList.contains('modal-overlay')) {
            e.target.classList.remove('active');
            e.target.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        }
    });

    // Close on modal close button
    document.addEventListener('click', function (e) {
        if (e.target.classList.contains('modal-close-btn')) {
            var modal = e.target.closest('.modal-overlay');
            if (modal) {
                modal.classList.remove('active');
                modal.setAttribute('aria-hidden', 'true');
                document.body.style.overflow = '';
            }
        }
    });

    // ── Button Loading State ──────────────────────────────────────
    window.setButtonLoading = function (btn, loading, text) {
        if (!btn) return;
        if (loading) {
            btn.dataset.originalText = btn.innerHTML;
            btn.disabled = true;
            btn.classList.add('btn-loading');
            var displayText = text || 'Loading...';
            btn.innerHTML = '<span class="loading-spinner loading-spinner-sm"></span> ' + displayText;
        } else {
            btn.disabled = false;
            btn.classList.remove('btn-loading');
            btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
        }
    };

    // ── Dropdown Toggle ───────────────────────────────────────────
    window.toggleDropdown = function (dropdownEl) {
        if (!dropdownEl) return;
        var isOpen = dropdownEl.classList.contains('open');
        // Close all dropdowns first
        document.querySelectorAll('.dropdown-menu.open').forEach(function (d) {
            d.classList.remove('open');
        });
        if (!isOpen) {
            dropdownEl.classList.add('open');
        }
    };

    // Close dropdowns on outside click
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.dropdown-menu') && !e.target.closest('[data-dropdown]')) {
            document.querySelectorAll('.dropdown-menu.open').forEach(function (d) {
                d.classList.remove('open');
            });
        }
    });

    // ── AJAX Helper (with toast feedback) ─────────────────────────
    window.apiRequest = function (options) {
        var method = (options.method || 'GET').toUpperCase();
        var url = options.url;
        var data = options.data;
        var btn = options.button;
        var loadingText = options.loadingText;
        var successMsg = options.successMessage;
        var errorMsg = options.errorMessage;
        var onSuccess = options.onSuccess;
        var onError = options.onError;

        if (btn) setButtonLoading(btn, true, loadingText);

        fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')
                    ? document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    : ''
            },
            body: data ? JSON.stringify(data) : undefined
        })
        .then(function (res) {
            if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
            return res.json();
        })
        .then(function (result) {
            if (btn) setButtonLoading(btn, false);
            if (successMsg) Toast.success(successMsg);
            if (onSuccess) onSuccess(result);
        })
        .catch(function (err) {
            if (btn) setButtonLoading(btn, false);
            var msg = errorMsg || 'Something went wrong. Please try again.';
            Toast.error('Error', msg);
            if (onError) onError(err);
        });
    };

    // ── Copy to Clipboard ─────────────────────────────────────────
    window.copyToClipboard = function (text, successMsg) {
        navigator.clipboard.writeText(text).then(function () {
            Toast.success('Copied', successMsg || 'Copied to clipboard.');
        }).catch(function () {
            Toast.error('Error', 'Failed to copy.');
        });
    };

})();

/**
 * DataViz Pro — Authentication JavaScript (Phase 2)
 *
 * Provides:
 * - Password visibility toggle
 * - Password strength meter
 * - Form double-submit prevention
 * - Enter-to-submit support
 * - Client-side validation hints
 */

(function () {
    'use strict';

    // ── Password Visibility Toggle ───────────────────────────────
    window.togglePassword = function (inputId, btn) {
        var input = document.getElementById(inputId);
        if (!input) return;

        var eyeOpen = btn.querySelector('.eye-open');
        var eyeClosed = btn.querySelector('.eye-closed');

        if (input.type === 'password') {
            input.type = 'text';
            if (eyeOpen) eyeOpen.style.display = 'none';
            if (eyeClosed) eyeClosed.style.display = 'block';
        } else {
            input.type = 'password';
            if (eyeOpen) eyeOpen.style.display = 'block';
            if (eyeClosed) eyeClosed.style.display = 'none';
        }
    };

    // ── Password Strength Meter ──────────────────────────────────
    function checkPasswordStrength(password) {
        var score = 0;

        if (password.length >= 8) score++;
        if (password.length >= 12) score++;
        if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
        if (/\d/.test(password)) score++;
        if (/[^a-zA-Z0-9]/.test(password)) score++;

        if (score <= 1) return { level: 'weak', label: 'Weak' };
        if (score === 2) return { level: 'fair', label: 'Fair' };
        if (score === 3) return { level: 'good', label: 'Good' };
        return { level: 'strong', label: 'Strong' };
    }

    var passwordInput = document.getElementById('password');
    var strengthBar = document.getElementById('strengthBar');
    var strengthText = document.getElementById('strengthText');

    if (passwordInput && strengthBar && strengthText) {
        passwordInput.addEventListener('input', function () {
            var pwd = this.value;

            if (pwd.length === 0) {
                strengthBar.style.width = '0%';
                strengthBar.className = 'strength-bar';
                strengthText.textContent = '';
                strengthText.className = 'strength-text';
                return;
            }

            var result = checkPasswordStrength(pwd);
            var widths = { weak: '25%', fair: '50%', good: '75%', strong: '100%' };

            strengthBar.style.width = widths[result.level];
            strengthBar.className = 'strength-bar strength-' + result.level;
            strengthText.textContent = result.label;
            strengthText.className = 'strength-text strength-' + result.level + '-text';
        });
    }

    // ── Confirm Password Match Check ──────────────────────────────
    var confirmPassword = document.getElementById('confirm_password');
    if (passwordInput && confirmPassword) {
        confirmPassword.addEventListener('input', function () {
            if (this.value && this.value !== passwordInput.value) {
                this.style.borderColor = '#EF4444';
            } else {
                this.style.borderColor = '';
            }
        });
    }

    // ── Form Double-Submit Prevention ────────────────────────────
    var forms = document.querySelectorAll('.auth-form');
    forms.forEach(function (form) {
        form.addEventListener('submit', function () {
            var btn = form.querySelector('button[type="submit"]');
            if (!btn || btn.disabled) return;

            var textEl = btn.querySelector('.btn-text');
            var loadEl = btn.querySelector('.btn-loading');

            btn.disabled = true;
            if (textEl) textEl.style.display = 'none';
            if (loadEl) loadEl.style.display = 'inline-flex';
        });
    });

    // ── Enter Key on Inputs Triggers Submit ───────────────────────
    document.querySelectorAll('.auth-form input').forEach(function (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                var form = this.closest('form');
                if (form) {
                    var btn = form.querySelector('button[type="submit"]');
                    if (btn) btn.click();
                }
            }
        });
    });

})();

/**
 * DataViz Pro — Dashboard JavaScript (Phase 15)
 *
 * Sidebar toggle, mobile navigation, user menu dropdown,
 * flash message dismissal, search, breadcrumb updates.
 */

(function () {
    'use strict';

    var sidebar = document.getElementById('dashSidebar');
    var overlay = document.getElementById('sidebarOverlay');
    var toggleBtn = document.getElementById('sidebarToggleBtn');
    var closeBtn = document.getElementById('sidebarCloseBtn');

    // ── Sidebar Toggle ────────────────────────────────────────────
    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('open');
        if (overlay) overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function () {
            if (sidebar.classList.contains('open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeSidebar);
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    // Close sidebar on ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeSidebar();
            closeUserMenu();
            closeAllModals();
        }
    });

    // ── User Menu Dropdown ─────────────────────────────────────────
    var menuTrigger = document.getElementById('userMenuTrigger');
    var menuDropdown = document.getElementById('userMenuDropdown');

    function openUserMenu() {
        if (!menuDropdown) return;
        menuDropdown.classList.add('open');
        if (menuTrigger) menuTrigger.setAttribute('aria-expanded', 'true');
    }

    function closeUserMenu() {
        if (!menuDropdown) return;
        menuDropdown.classList.remove('open');
        if (menuTrigger) menuTrigger.setAttribute('aria-expanded', 'false');
    }

    if (menuTrigger) {
        menuTrigger.addEventListener('click', function (e) {
            e.stopPropagation();
            if (menuDropdown.classList.contains('open')) {
                closeUserMenu();
            } else {
                openUserMenu();
            }
        });
    }

    // Close user menu when clicking outside
    document.addEventListener('click', function (e) {
        if (menuDropdown && !menuDropdown.contains(e.target) && e.target !== menuTrigger) {
            closeUserMenu();
        }
    });

    // ── Flash Message Dismissal ────────────────────────────────────
    document.addEventListener('click', function (e) {
        if (e.target.classList.contains('flash-dismiss')) {
            var item = e.target.closest('.flash-item');
            if (item) {
                item.style.opacity = '0';
                item.style.transform = 'translateY(-8px) scale(0.96)';
                item.style.transition = 'all 0.25s ease';
                setTimeout(function () {
                    item.remove();
                }, 250);
            }
        }
    });

    // Auto-dismiss success messages after 5 seconds
    var flashItems = document.querySelectorAll('.flash-item-success');
    flashItems.forEach(function (item) {
        setTimeout(function () {
            if (item.parentNode) {
                item.style.opacity = '0';
                item.style.transform = 'translateY(-8px) scale(0.96)';
                item.style.transition = 'all 0.3s ease';
                setTimeout(function () { item.remove(); }, 300);
            }
        }, 5000);
    });

    // ── Active Sidebar Link Highlight ────────────────────────────
    var currentPath = window.location.pathname;
    var navItems = document.querySelectorAll('.nav-item[data-page]');
    navItems.forEach(function (item) {
        var page = item.getAttribute('data-page');
        if (page && currentPath.indexOf(page) !== -1) {
            item.classList.add('active');
        }
    });

    // ── Keyboard Navigation ───────────────────────────────────────
    // Tab through sidebar nav items
    var sidebarLinks = document.querySelectorAll('.nav-item');
    sidebarLinks.forEach(function (link, index) {
        link.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                var next = sidebarLinks[index + 1];
                if (next) next.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                var prev = sidebarLinks[index - 1];
                if (prev) prev.focus();
            }
        });
    });

    // ── Responsive: close sidebar on resize to desktop ───────────
    var mql = window.matchMedia('(min-width: 1025px)');
    function handleResize(e) {
        if (e.matches) {
            closeSidebar();
        }
    }
    if (mql) {
        mql.addEventListener('change', handleResize);
    }

})();
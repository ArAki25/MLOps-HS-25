/* ═══════════════════════════════════════════════
   SAJF Strategies — Core UI Logic
   Theme toggle, menus, navigation
   ═══════════════════════════════════════════════ */

function toggleTheme() {
    var next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('sajf-theme', next);
}

function toggleMenu() {
    var nav = document.getElementById('nav');
    nav.classList.toggle('open');
}

/* ── User Menu ── */
function toggleUserMenu(evt) {
    if (evt) evt.stopPropagation();
    var menu = document.getElementById('user-menu');
    if (!menu) return;
    var willOpen = !menu.classList.contains('open');
    menu.classList.toggle('open', willOpen);
    var btn = menu.querySelector('.user-menu-btn');
    if (btn) btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}

document.addEventListener('click', function (e) {
    var menu = document.getElementById('user-menu');
    if (!menu || !menu.classList.contains('open')) return;
    if (!menu.contains(e.target)) {
        menu.classList.remove('open');
        var btn = menu.querySelector('.user-menu-btn');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var menu = document.getElementById('user-menu');
    if (menu && menu.classList.contains('open')) {
        menu.classList.remove('open');
        var btn = menu.querySelector('.user-menu-btn');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }
    document.querySelectorAll('.nav-dropdown.open').forEach(function(d) { d.classList.remove('open'); });
    var langMenu = document.getElementById('lang-menu');
    if (langMenu) langMenu.classList.remove('open');
});

/* ── Nav Dropdown ── */
function toggleNavDropdown(evt, id) {
    if (evt) evt.stopPropagation();
    var dd = document.getElementById(id);
    if (!dd) return;
    dd.classList.toggle('open');
}

document.addEventListener('click', function(e) {
    document.querySelectorAll('.nav-dropdown.open').forEach(function(dd) {
        if (!dd.contains(e.target)) dd.classList.remove('open');
    });
});

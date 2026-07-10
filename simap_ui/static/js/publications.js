// ==========================================
// STATE
// ==========================================
var currentPage = 1, perPage = 30, totalResults = 0, totalPages = 0;
var searchQuery = '', sortBy = 'newest', openFilter = null;
var favoriteIds = new Set();
var activeFilters = { canton: [], order_type: [], process_type: [], pub_type: [], cpv: [] };
var filterOptions = { canton: [], order_type: [], process_type: [], pub_type: [] };
var bewLoaded = false, recLoaded = false, profLoaded = false, marktLoaded = false, recDisplayCount = 20;
var userRatings = {};

var SUBTYPE_LABELS = { 'construction':'Bauleistung', 'supply':'Lieferung', 'service':'Dienstleistung' };
var KANTON_NAMES = {'AG':'Aargau','AI':'Appenzell IR','AR':'Appenzell AR','BE':'Bern','BL':'Basel-Land','BS':'Basel-Stadt','FR':'Freiburg','GE':'Genf','GL':'Glarus','GR':'Graubünden','JU':'Jura','LU':'Luzern','NE':'Neuenburg','NW':'Nidwalden','OW':'Obwalden','SG':'St. Gallen','SH':'Schaffhausen','SO':'Solothurn','SZ':'Schwyz','TG':'Thurgau','TI':'Tessin','UR':'Uri','VD':'Waadt','VS':'Wallis','ZG':'Zug','ZH':'Zürich'};
var starFilled = '<svg width="16" height="16" fill="#ca8a04" stroke="#ca8a04" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
var starEmpty = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';

// ==========================================
// INIT
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    loadFilterOptions();
    loadFavorites();
    loadFeedRatings();
    loadPage(1);
    setupEventListeners();
    loadProfileCompleteness();
});

function loadProfileCompleteness() {
    fetch('/api/profile/data').then(function(r) { return r.json(); }).then(function(p) {
        var score = 0;
        if (p.company_name)      score++;
        if (p.project_subtype)   score++;
        if (p.preferred_cantons && p.preferred_cantons.length > 0) score++;
        if (p.award_amount_min != null || p.award_amount_max != null) score++;
        var pct = Math.round((score / 4) * 100);
        var fill = document.getElementById('comp-fill');
        var lbl  = document.getElementById('comp-pct');
        if (fill) fill.style.width = pct + '%';
        if (lbl)  lbl.textContent = pct + '%';
    }).catch(function() {});
}

function setupEventListeners() {
    document.getElementById('search-input').addEventListener('keypress', function(e) { if (e.key === 'Enter') performSearch(); });
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.filter-chip') && !e.target.closest('.filter-dropdown')) closeAllDropdowns();
        if (!e.target.closest('.user-avatar') && !e.target.closest('.user-dropdown')) document.getElementById('user-dropdown').classList.remove('show');
    });
}

// ==========================================
// TAB SWITCHING
// ==========================================
function switchTab(name) {
    var tabs = ['ausschreibungen', 'bewertungen', 'empfehlungen', 'markt', 'profil'];
    var titles = {
        ausschreibungen: 'Ausschreibungen',
        bewertungen:     'Meine Bewertungen',
        empfehlungen:    'Empfehlungen',
        markt:           'Marktübersicht',
        profil:          'Mein Profil'
    };
    var subtitles = {
        ausschreibungen: 'Öffentliche Aufträge der Schweiz durchsuchen',
        bewertungen:     'Ihre bewerteten Ausschreibungen verwalten',
        empfehlungen:    'Basierend auf Ihren Bewertungen',
        markt:           'Aktuelle Ausschreibungen nach Kanton und Branche',
        profil:          'Firmendaten und Präferenzen bearbeiten'
    };

    tabs.forEach(function(t) {
        document.getElementById('panel-' + t).classList.toggle('active', t === name);
        document.getElementById('tab-' + t).classList.toggle('active', t === name);
        var nav = document.getElementById('nav-' + t);
        if (nav) nav.classList.toggle('active', t === name);
    });

    document.getElementById('page-title').textContent = titles[name];
    document.getElementById('page-subtitle').textContent = subtitles[name];

    if (name === 'bewertungen' && !bewLoaded) loadBewertungen();
    if (name === 'empfehlungen' && !recLoaded) loadEmpfehlungen();
    if (name === 'markt' && !marktLoaded) loadMarkt();
    if (name === 'profil' && !profLoaded) initProfil();
}

// ==========================================
// BEWERTUNGEN TAB
// ==========================================
function loadBewertungen() {
    bewLoaded = true;
    fetch('/api/user-ratings')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var items = data.ratings || [];
            if (items.length === 0) {
                document.getElementById('bew-content').innerHTML = '<div class="empty-state" style="padding:3rem 1rem;text-align:center;">'
                    + '<svg width="40" height="40" fill="none" stroke="var(--text-muted)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 0.75rem;display:block;opacity:0.4"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>'
                    + '<p style="font-weight:600;font-size:0.9rem;margin-bottom:0.4rem;">Noch keine Bewertungen</p>'
                    + '<p style="color:var(--text-muted);font-size:0.8125rem;max-width:300px;margin:0 auto 1rem;">Öffnen Sie den Tab <strong>Ausschreibungen</strong> und markieren Sie relevante Einträge.</p>'
                    + '<a onclick="switchTab(\'ausschreibungen\')" style="display:inline-flex;align-items:center;gap:0.3rem;padding:0.5rem 1rem;background:var(--accent);color:white;font-weight:600;font-size:0.8125rem;border-radius:var(--radius);cursor:pointer;text-decoration:none;">Zu den Ausschreibungen</a>'
                    + '</div>';
                return;
            }
            document.getElementById('bew-count').textContent = items.length;
            document.getElementById('bew-count').style.display = 'inline';
            renderBewertungen(items);
        })
        .catch(function() {
            document.getElementById('bew-content').innerHTML = '<div class="empty-state">Fehler beim Laden.</div>';
        });
}

function renderBewertungen(items) {
    var html = '';
    items.forEach(function(item) {
        var canton = item.canton ? (KANTON_NAMES[item.canton] || item.canton) : '';
        var subtype = item.project_subtype ? (SUBTYPE_LABELS[item.project_subtype] || item.project_subtype) : '';
        var amount = item.award_amount ? 'CHF ' + Number(item.award_amount).toLocaleString('de-CH') : '';
        var source = item.source || 'project';

        html += '<div class="bew-card rated-yes" id="bew-' + item.tender_id + '">' +
            '<div class="bew-content">' +
                '<div class="bew-title">' + escapeHtml(item.title_de || 'Ohne Titel') + '</div>' +
                '<div class="bew-meta">' +
                    (canton ? '<span class="bew-tag">' + canton + '</span>' : '') +
                    (subtype ? '<span class="bew-tag">' + subtype + '</span>' : '') +
                    (amount ? '<span class="bew-tag">' + amount + '</span>' : '') +
                '</div>' +
            '</div>' +
            '<div class="bew-btns">' +
                '<button class="bew-btn bew-btn-remove" onclick="removeLike(\'' + item.tender_id + '\', \'' + source + '\')">' +
                    '<svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Entfernen' +
                '</button>' +
            '</div>' +
        '</div>';
    });
    document.getElementById('bew-content').innerHTML = html;
}

function removeLike(tenderId, source) {
    fetch('/api/remove-rating', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tender_id: tenderId, source: source || 'project'})
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.success) {
            bewLoaded = false;
            recLoaded = false;
            if (userRatings[tenderId]) delete userRatings[tenderId];
            updateRateButtons(tenderId, 0);
            loadBewertungen();
        }
    }).catch(function(e) { console.error(e); });
}

// ==========================================
// EMPFEHLUNGEN TAB
// ==========================================
function loadEmpfehlungen(count) {
    recLoaded = true;
    count = count || recDisplayCount;
    document.getElementById('rec-content').innerHTML = '<div class="loading-state"><div class="spinner"></div>Empfehlungen werden berechnet...</div>';
    document.getElementById('rec-loaded-info').textContent = '';
    fetch('/api/recommendations?count=' + count)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var recs = data.recommendations || [];
            if (recs.length === 0) {
                var hint = data.hint || 'no_results';
                var msg = '';
                if (hint === 'no_ratings') {
                    msg = '<p style="font-weight:600;">Noch keine Empfehlungen</p><p style="margin-top:0.4rem;color:var(--text-muted);">Bewerten Sie im Tab <strong>Ausschreibungen</strong> mindestens eine Ausschreibung mit &ldquo;Relevant&rdquo;, damit der Algorithmus Ihr Interessenprofil aufbauen kann.</p>';
                } else if (hint === 'profile_too_narrow' || hint === 'cpv_too_narrow') {
                    msg = '<p style="font-weight:600;">Profil zu eng gefiltert</p><p style="margin-top:0.4rem;color:var(--text-muted);">Projekttyp oder Auftragsvolumen schränken die Treffer stark ein. Passen Sie Ihre Einstellungen in <a href="/profile" style="color:var(--accent);">Mein Profil</a> an.</p>';
                } else {
                    msg = '<p style="font-weight:600;">Keine passenden Ausschreibungen gefunden</p><p style="margin-top:0.4rem;color:var(--text-muted);">Aktuell sind keine neuen Projekte vorhanden, die Ihrem Profil entsprechen.</p>';
                }
                document.getElementById('rec-content').innerHTML = '<div class="empty-state">' + msg + '</div>';
                document.getElementById('rec-loaded-info').textContent = '';
                return;
            }
            document.getElementById('rec-loaded-info').textContent = recs.length + ' geladen';
            renderEmpfehlungen(recs);
        })
        .catch(function() {
            document.getElementById('rec-content').innerHTML = '<div class="empty-state">Fehler beim Laden der Empfehlungen.</div>';
        });
}

function applyRecCount() {
    var v = parseInt(document.getElementById('rec-count-input').value, 10);
    if (isNaN(v) || v < 1) v = 20;
    recDisplayCount = Math.min(v, 100);
    document.getElementById('rec-count-input').value = recDisplayCount;
    recLoaded = false;
    loadEmpfehlungen(recDisplayCount);
}

function showAllRecs() {
    recDisplayCount = 100;
    document.getElementById('rec-count-input').value = 100;
    recLoaded = false;
    loadEmpfehlungen(100);
}

function renderEmpfehlungen(recs) {
    var html = '';
    recs.forEach(function(r) {
        var score = Math.round((r.similarity || 0) * 100);
        var scoreClass = score >= 75 ? 'high' : (score >= 55 ? 'mid' : 'low');
        var desc = stripHtml(r.description_de || '');
        var canton = r.canton ? (KANTON_NAMES[r.canton] || r.canton) : '';
        var subtype = r.project_subtype ? (SUBTYPE_LABELS[r.project_subtype] || r.project_subtype) : '';
        var amount = r.award_amount ? 'CHF ' + Number(r.award_amount).toLocaleString('de-CH') : '';
        var pid = r.id || '';
        var isLiked = pid && userRatings[pid] === 1;
        var likedCls = isLiked ? ' is-liked' : '';
        var btnActive = isLiked ? ' active' : '';
        var btnLabel = isLiked ? 'Relevant' : 'Als relevant markieren';

        var chips = '';
        if (canton) chips += '<span class="rec-chip"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>' + escapeHtml(canton) + '</span>';
        if (subtype) chips += '<span class="rec-chip">' + escapeHtml(subtype) + '</span>';
        if (amount) chips += '<span class="rec-chip accent">' + amount + '</span>';

        html += '<div class="rec-card' + likedCls + '" data-rec-pid="' + pid + '">' +
            '<div class="rec-top">' +
                '<span class="rec-score ' + scoreClass + '">' +
                    '<svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> ' +
                    score + '% Match' +
                '</span>' +
                '<div class="rec-actions">' +
                    '<button class="rec-rate-btn' + btnActive + '" onclick="rateInFeed(\'' + pid + '\',1)" title="Als relevant bewerten" aria-pressed="' + (isLiked ? 'true' : 'false') + '">' +
                        '<span class="plus-icon"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg></span>' +
                        '<span class="check-icon"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>' +
                        '<span class="rec-rate-label">' + btnLabel + '</span>' +
                    '</button>' +
                '</div>' +
            '</div>' +
            '<div class="rec-title">' + escapeHtml(r.title_de || 'Ohne Titel') + '</div>' +
            (chips ? '<div class="rec-meta">' + chips + '</div>' : '') +
            '<div class="rec-desc">' + escapeHtml(desc) + '</div>' +
        '</div>';
    });
    document.getElementById('rec-content').innerHTML = html;
}

// ==========================================
// MARKTÜBERSICHT TAB
// ==========================================
var CANTON_NAMES_FULL = {'AG':'Aargau','AI':'Appenzell IR','AR':'Appenzell AR','BE':'Bern','BL':'Basel-Land','BS':'Basel-Stadt','FR':'Freiburg','GE':'Genf','GL':'Glarus','GR':'Graubünden','JU':'Jura','LU':'Luzern','NE':'Neuenburg','NW':'Nidwalden','OW':'Obwalden','SG':'St. Gallen','SH':'Schaffhausen','SO':'Solothurn','SZ':'Schwyz','TG':'Thurgau','TI':'Tessin','UR':'Uri','VD':'Waadt','VS':'Wallis','ZG':'Zug','ZH':'Zürich'};
var SUBTYPE_LABELS_FULL = {'construction':'Bauleistung','supply':'Lieferung','service':'Dienstleistung','other':'Sonstige'};
var ORDER_TYPE_LABELS = {'WORKS':'Bauleistung','SERVICES':'Dienstleistungen','SUPPLIES':'Lieferungen','OTHER':'Sonstige'};

function loadMarkt() {
    marktLoaded = true;
    fetch('/api/analytics')
        .then(function(r) { return r.json(); })
        .then(function(data) { renderMarkt(data); })
        .catch(function() {
            document.getElementById('markt-content').innerHTML = '<div class="empty-state">Fehler beim Laden der Marktdaten.</div>';
        });
}

function renderMarkt(data) {
    var cantonCounts = data.canton_counts || {};
    var subtypeCounts = data.subtype_counts || {};
    var orderTypeCounts = data.order_type_counts || {};

    var cantonEntries = Object.keys(cantonCounts).map(function(k) { return {abbr: k, count: cantonCounts[k]}; });
    cantonEntries.sort(function(a, b) { return b.count - a.count; });
    var maxCount = cantonEntries.length ? cantonEntries[0].count : 1;

    var ALL_CANTONS = ['ZH','BE','LU','UR','SZ','OW','NW','GL','ZG','FR','SO','BS','BL','SH','AR','AI','SG','GR','AG','TG','TI','VD','VS','NE','GE','JU'];
    var cantonHtml = ALL_CANTONS.map(function(abbr) {
        var count = cantonCounts[abbr] || 0;
        var ratio = maxCount > 0 ? count / maxCount : 0;
        var heat = ratio === 0 ? 0 : ratio < 0.15 ? 1 : ratio < 0.4 ? 2 : ratio < 0.7 ? 3 : 4;
        return '<div class="canton-tile heat-' + heat + '" title="' + (CANTON_NAMES_FULL[abbr] || abbr) + ': ' + count + ' Ausschreibungen">' +
            '<span class="canton-tile-abbr">' + abbr + '</span>' +
            '<span class="canton-tile-count">' + count + '</span>' +
        '</div>';
    }).join('');

    var subtypeEntries = Object.keys(subtypeCounts).map(function(k) { return {key: k, count: subtypeCounts[k]}; });
    subtypeEntries.sort(function(a, b) { return b.count - a.count; });
    var maxSub = subtypeEntries.length ? subtypeEntries[0].count : 1;
    var subtypeHtml = subtypeEntries.map(function(e) {
        var pct = Math.round((e.count / maxSub) * 100);
        var label = SUBTYPE_LABELS_FULL[e.key] || e.key;
        return '<div class="bar-item">' +
            '<span class="bar-label">' + label + '</span>' +
            '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
            '<span class="bar-count">' + e.count + '</span>' +
        '</div>';
    }).join('') || '<p style="color:var(--text-muted);font-size:0.8125rem;">Keine Daten</p>';

    var orderEntries = Object.keys(orderTypeCounts).map(function(k) { return {key: k, count: orderTypeCounts[k]}; });
    orderEntries.sort(function(a, b) { return b.count - a.count; });
    var maxOrder = orderEntries.length ? orderEntries[0].count : 1;
    var orderHtml = orderEntries.map(function(e) {
        var pct = Math.round((e.count / maxOrder) * 100);
        var label = ORDER_TYPE_LABELS[e.key] || e.key;
        return '<div class="bar-item">' +
            '<span class="bar-label">' + label + '</span>' +
            '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:var(--success)"></div></div>' +
            '<span class="bar-count">' + e.count + '</span>' +
        '</div>';
    }).join('') || '<p style="color:var(--text-muted);font-size:0.8125rem;">Keine Daten</p>';

    var top5Html = cantonEntries.slice(0, 5).map(function(e, i) {
        var pct = Math.round((e.count / maxCount) * 100);
        return '<div class="bar-item">' +
            '<span class="bar-label" style="min-width:100px;"><strong>' + e.abbr + '</strong> <span style="color:var(--text-muted);font-size:0.65rem;">' + (CANTON_NAMES_FULL[e.abbr] || '') + '</span></span>' +
            '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
            '<span class="bar-count">' + e.count + '</span>' +
        '</div>';
    }).join('');

    var html = '<div class="mkt-section">' +
        '<div class="mkt-section-title">Ausschreibungen nach Kanton</div>' +
        '<div class="canton-grid">' + cantonHtml + '</div>' +
    '</div>' +
    '<div class="mkt-cards">' +
        '<div class="mkt-card">' +
            '<div class="mkt-section-title">Top 5 Kantone</div>' +
            '<div class="bar-list">' + top5Html + '</div>' +
        '</div>' +
        '<div class="mkt-card">' +
            '<div class="mkt-section-title">Nach Auftragsart</div>' +
            '<div class="bar-list">' + orderHtml + '</div>' +
        '</div>' +
        '<div class="mkt-card">' +
            '<div class="mkt-section-title">Nach Projekttyp</div>' +
            '<div class="bar-list">' + subtypeHtml + '</div>' +
        '</div>' +
    '</div>';

    document.getElementById('markt-content').innerHTML = html;
}

// ==========================================
// AUSSCHREIBUNGEN TAB
// ==========================================
function buildApiUrl(page) {
    var params = ['page=' + page, 'per_page=' + perPage, 'sort=' + sortBy];
    if (searchQuery) params.push('search=' + encodeURIComponent(searchQuery));
    if (activeFilters.canton.length) params.push('cantons=' + encodeURIComponent(activeFilters.canton.join(',')));
    if (activeFilters.order_type.length) params.push('order_type=' + encodeURIComponent(activeFilters.order_type[0]));
    if (activeFilters.process_type.length) params.push('process_type=' + encodeURIComponent(activeFilters.process_type[0]));
    if (activeFilters.pub_type.length) params.push('pub_type=' + encodeURIComponent(activeFilters.pub_type[0]));
    if (activeFilters.cpv.length) params.push('cpv=' + encodeURIComponent(activeFilters.cpv.join(',')));
    return '/api/projects?' + params.join('&');
}

function loadPage(page) {
    currentPage = page;
    showLoading();
    fetch(buildApiUrl(page))
        .then(function(res) { return res.json(); })
        .then(function(result) {
            totalResults = result.total || 0;
            totalPages = result.pages || 0;
            currentPage = result.page || 1;
            renderProjects(result.data || []);
            renderPagination();
            updateCounts();
        })
        .catch(function(e) { console.error('Load error:', e); document.getElementById('pub-list').innerHTML = '<div class="empty-state">Fehler beim Laden.</div>'; });
}

function loadFilterOptions() {
    fetch('/api/filter-options').then(function(res) { return res.json(); }).then(function(opts) {
        filterOptions.canton = opts.cantons || []; filterOptions.order_type = opts.order_types || [];
        filterOptions.process_type = opts.process_types || []; filterOptions.pub_type = opts.pub_types || [];
    }).catch(function(e) { console.error('Filter error:', e); });
}

function loadFavorites() {
    fetch('/api/favorites').then(function(res) { return res.json(); }).then(function(data) { favoriteIds = new Set(data.favorites || []); }).catch(function() {});
}

function loadFeedRatings() {
    fetch('/api/feed-ratings').then(function(r) { return r.json(); }).then(function(data) {
        userRatings = data.ratings || {};
    }).catch(function() {});
}

function performSearch() { searchQuery = document.getElementById('search-input').value.trim(); loadPage(1); }
function sortProjects() { sortBy = document.getElementById('sort-select').value; loadPage(1); }

// Filters
function renderFilterOption(name, opt) {
    var isSelected = activeFilters[name].includes(opt);
    var safeOpt = opt.replace(/'/g, '');
    var checkSvg = isSelected ? '<svg width="10" height="10" fill="none" stroke="white" stroke-width="3" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : '';
    return '<div class="filter-option ' + (isSelected ? 'selected' : '') + '" onclick="selectFilter(\'' + name + '\', \'' + safeOpt + '\')"><div class="filter-option-check">' + checkSvg + '</div><span>' + opt + '</span></div>';
}

function toggleFilter(name) {
    if (openFilter === name) { closeAllDropdowns(); return; }
    closeAllDropdowns(); openFilter = name;
    document.querySelector('[data-filter="' + name + '"]').classList.add('open');
    var dropdown = document.getElementById('dropdown-' + name);
    var options = filterOptions[name] || [];
    dropdown.innerHTML = '<input type="text" class="filter-dropdown-search" placeholder="Suchen..." oninput="filterDropdownOptions(\'' + name + '\', this.value)"><div id="dropdown-options-' + name + '">' + options.map(function(opt) { return renderFilterOption(name, opt); }).join('') + '</div>';
    var chipRect = document.querySelector('[data-filter="' + name + '"]').getBoundingClientRect();
    var filtersRect = document.getElementById('filters-row').getBoundingClientRect();
    dropdown.style.left = (chipRect.left - filtersRect.left) + 'px';
    dropdown.classList.add('show');
}

function closeAllDropdowns() { openFilter = null; document.querySelectorAll('.filter-chip').forEach(function(c){c.classList.remove('open');}); document.querySelectorAll('.filter-dropdown').forEach(function(d){d.classList.remove('show');}); }

function filterDropdownOptions(name, query) {
    var container = document.getElementById('dropdown-options-' + name);
    var filtered = (filterOptions[name] || []).filter(function(o) { return o.toLowerCase().indexOf(query.toLowerCase()) >= 0; });
    container.innerHTML = filtered.map(function(opt) { return renderFilterOption(name, opt); }).join('');
}

function selectFilter(name, value) {
    var idx = activeFilters[name].indexOf(value);
    if (idx > -1) activeFilters[name].splice(idx, 1);
    else if (name === 'canton') activeFilters[name].push(value);
    else activeFilters[name] = [value];
    var chip = document.querySelector('[data-filter="' + name + '"]');
    if (activeFilters[name].length > 0) { chip.classList.add('active'); chip.querySelector('span').textContent = getFilterLabel(name) + ' (' + activeFilters[name].length + ')'; }
    else { chip.classList.remove('active'); chip.querySelector('span').textContent = getFilterLabel(name); }
    if (openFilter === name) { var s = document.querySelector('#dropdown-' + name + ' .filter-dropdown-search'); filterDropdownOptions(name, s ? s.value : ''); }
    renderActiveFilters(); loadPage(1);
}

function getFilterLabel(name) { return {canton:'Kanton',order_type:'Auftragsart',process_type:'Verfahrensart',pub_type:'Publikationsart',cpv:'CPV-Code'}[name] || name; }

function clearAllFilters() {
    Object.keys(activeFilters).forEach(function(k) {
        activeFilters[k] = [];
        var c = document.querySelector('[data-filter="'+k+'"]');
        if (c) { c.classList.remove('active'); c.querySelector('span').textContent = getFilterLabel(k); }
    });
    renderActiveFilters(); loadPage(1);
}

function removeFilter(name, value) {
    if (name === 'cpv') { removeCpvFilter(value); return; }
    selectFilter(name, value);
}

function renderActiveFilters() {
    var container = document.getElementById('active-filters'), btn = document.getElementById('filter-clear-btn');
    var all = [];
    Object.keys(activeFilters).forEach(function(k) {
        activeFilters[k].forEach(function(v) { all.push({key: k, value: v}); });
    });
    if (!all.length) { container.innerHTML = ''; btn.style.display = 'none'; return; }
    btn.style.display = 'inline-flex';
    container.innerHTML = all.map(function(i) {
        var label = i.key === 'cpv' ? 'CPV: ' + i.value : i.value;
        return '<span class="active-filter-tag">' + label + ' <button onclick="removeFilter(\'' + i.key + '\',\'' + i.value.replace(/'/g,'') + '\')">&times;</button></span>';
    }).join('');
}

// Render projects
function renderProjects(projects) {
    var container = document.getElementById('pub-list');
    if (!projects || !projects.length) { container.innerHTML = '<div class="empty-state">Keine Ausschreibungen gefunden.</div>'; return; }
    var html = '';
    projects.forEach(function(p, i) {
        var isFav = favoriteIds.has(p.id), isRecent = isWithin48h(p.publication_date);
        var loc = (p.city||'') + (p.city&&p.canton?', ':'') + (p.canton||'');
        var tags = '<span class="pub-tag">#' + (p.project_number||'-') + '</span>';
        if (p.pub_type) tags += '<span class="pub-tag ' + getPubTypeClass(p.pub_type) + '">' + capitalize(p.pub_type) + '</span>';
        if (p.order_type) tags += '<span class="pub-tag">' + capitalize(p.order_type) + '</span>';
        var rowId = 'row-' + i;

        var currentRating = userRatings[p.id] || 0;
        var upActive = currentRating === 1 ? ' active' : '';
        var rowLiked = currentRating === 1 ? ' is-liked' : '';

        var titleHtml = p.simap_id
            ? '<a href="/tender/' + encodeURIComponent(p.simap_id) + '" class="pub-title" onclick="event.stopPropagation()" style="text-decoration:none;">' + escapeHtml(p.title) + '</a>'
            : '<div class="pub-title">' + escapeHtml(p.title) + '</div>';
        var deadlineBadge = '';
        if (isFav && p.deadline && !isAwardType(p.pub_type)) {
            deadlineBadge = '<div class="pub-deadline-badge">'
                + '<svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
                + 'Frist: ' + formatDate(p.deadline) + '</div>';
        }
        html += '<div class="pub-row' + rowLiked + '" id="' + rowId + '" data-pub-pid="' + p.id + '" onclick="toggleDetail(\'' + rowId + '\')">' +
            '<div class="pub-title-col">' + titleHtml + '<div class="pub-location">' + loc + '</div><div class="pub-tags">' + tags + '</div>' + deadlineBadge + '</div>' +
            '<div class="pub-office">' + escapeHtml(p.organization||'-') + '</div>' +
            '<div class="pub-date-col"><div class="pub-time-ago ' + (isRecent?'':'old') + '">' + getTimeAgo(p.publication_date) + '</div><div class="pub-date-exact">' + formatDate(p.publication_date) + '</div></div>' +
            '<div class="pub-rate">' +
                '<button class="pub-rate-btn up' + upActive + '" data-rate-pid="' + p.id + '" data-rate-val="1" onclick="event.stopPropagation();rateInFeed(\'' + p.id + '\',1)" title="Relevant">' +
                    '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>' +
                '</button>' +
            '</div>' +
            '<div class="pub-actions"><button class="pub-fav-btn ' + (isFav?'favorited':'') + '" onclick="event.stopPropagation();toggleFavorite(\'' + p.id + '\',this)" title="' + (isFav?'Entfernen':'Merken') + '">' + (isFav?starFilled:starEmpty) + '</button></div>' +
        '</div>' +
        '<div class="pub-detail' + rowLiked + '" id="detail-' + rowId + '"><div class="pub-detail-inner"><div class="pub-detail-desc">' + escapeHtml(p.description||'') + '</div><div class="pub-detail-actions">' +
            (p.simap_id ? '<a href="/tender/' + encodeURIComponent(p.simap_id) + '" class="btn-simap" style="background:var(--surface-hover);color:var(--text-primary);border:1px solid var(--border);" onclick="event.stopPropagation()"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>Details</a>' : '') +
            '<a href="' + escapeHtml(p.simap_url||'#') + '" target="_blank" rel="noopener noreferrer" class="btn-simap" onclick="event.stopPropagation()"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>simap.ch</a>' +
            '<span class="pub-detail-meta">#' + (p.project_number||'-') + '</span></div></div></div>';
    });
    container.innerHTML = html;
}

function toggleDetail(rowId) {
    var row = document.getElementById(rowId), detail = document.getElementById('detail-' + rowId);
    if (!detail) return;
    var wasOpen = detail.classList.contains('open');
    document.querySelectorAll('.pub-detail.open').forEach(function(d){d.classList.remove('open');});
    document.querySelectorAll('.pub-row.expanded').forEach(function(r){r.classList.remove('expanded');});
    if (!wasOpen) { detail.classList.add('open'); row.classList.add('expanded'); }
}

function renderPagination() {
    if (totalPages <= 1) {
        document.getElementById('pagination').innerHTML = '';
        document.getElementById('pagination-top').innerHTML = '';
        return;
    }
    var html = '<button ' + (currentPage===1?'disabled':'') + ' onclick="goToPage(' + (currentPage-1) + ')">&#8249;</button>';
    for (var i = 1; i <= totalPages; i++) {
        if (i===1||i===totalPages||(i>=currentPage-2&&i<=currentPage+2)) html += '<button class="' + (i===currentPage?'active':'') + '" onclick="goToPage(' + i + ')">' + i + '</button>';
        else if (i===currentPage-3||i===currentPage+3) html += '<button disabled>&hellip;</button>';
    }
    html += '<button ' + (currentPage===totalPages?'disabled':'') + ' onclick="goToPage(' + (currentPage+1) + ')">&#8250;</button>';
    document.getElementById('pagination').innerHTML = html;
    document.getElementById('pagination-top').innerHTML = html;
}

function goToPage(page) { loadPage(page); window.scrollTo({top:0,behavior:'smooth'}); }
function updateCounts() { document.getElementById('results-count').innerHTML = '<strong>' + totalResults.toLocaleString('de-CH') + '</strong> Ergebnisse'; document.getElementById('sidebar-count').textContent = totalResults.toLocaleString('de-CH'); }

// Helpers
function getTimeAgo(d) { if(!d)return'-'; var ms=new Date()-new Date(d),m=Math.floor(ms/60000),h=Math.floor(ms/3600000),dy=Math.floor(ms/86400000); if(m<1)return'Gerade eben'; if(m<60)return'vor '+m+' Min.'; if(h<24)return'vor '+h+' Std.'; if(dy===1)return'Gestern'; if(dy<7)return'vor '+dy+' Tagen'; if(dy<30)return'vor '+Math.floor(dy/7)+' Wo.'; return formatDate(d); }
function isWithin48h(d) { return d && (new Date()-new Date(d))<172800000; }
function getPubTypeClass(t) { if(!t)return''; var l=t.toLowerCase(); if(l.indexOf('tender')>=0||l.indexOf('ausschreibung')>=0)return'type-tender'; if(l.indexOf('award')>=0||l.indexOf('zuschlag')>=0)return'type-award'; return''; }
function isAwardType(t) { if(!t)return false; var l=t.toLowerCase(); return l.indexOf('zuschlag')>=0||l.indexOf('award')>=0||l.indexOf('widerruf')>=0; }
function formatDate(d) { if(!d)return'-'; try{return new Date(d).toLocaleDateString('de-CH',{day:'2-digit',month:'2-digit',year:'numeric'});}catch(e){return d;} }
function capitalize(s) { return s ? s.charAt(0).toUpperCase()+s.slice(1) : ''; }
function escapeHtml(t) { if(!t)return''; var d=document.createElement('div'); d.textContent=t; return d.innerHTML; }
function stripHtml(t) { return t ? t.replace(/<[^>]+>/g,'').replace(/&nbsp;/g,' ').trim() : ''; }
function showLoading() { document.getElementById('pub-list').innerHTML = '<div class="loading-state"><div class="spinner"></div>Laden...</div>'; }
function toggleUserMenu() { document.getElementById('user-dropdown').classList.toggle('show'); }
function toggleTheme() {
    var next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('sajf-theme', next);
}

function openMobileSidebar() {
    document.body.classList.add('sidebar-mobile-open');
    document.getElementById('sidebar-overlay').classList.add('show');
}
function closeMobileSidebar() {
    document.body.classList.remove('sidebar-mobile-open');
    document.getElementById('sidebar-overlay').classList.remove('show');
}

function toggleSidebar() {
    document.body.classList.toggle('sidebar-hidden');
    localStorage.setItem('sajf-sidebar', document.body.classList.contains('sidebar-hidden') ? 'hidden' : 'visible');
}

// Feed-Rate: idempotent Like-Toggle
function rateInFeed(pid, value) {
    var prev = userRatings[pid] || 0;
    var next = (prev === 1) ? 0 : 1;
    userRatings[pid] = next;
    updateRateButtons(pid, next);
    bewLoaded = false;
    recLoaded = false;

    fetch('/api/feed-rate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tender_id: pid, rating: next, source: 'project' })
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (!res || !res.success) {
            userRatings[pid] = prev;
            updateRateButtons(pid, prev);
        }
    }).catch(function() {
        userRatings[pid] = prev;
        updateRateButtons(pid, prev);
    });
}

function updateRateButtons(pid, rating) {
    document.querySelectorAll('.pub-rate-btn[data-rate-pid="' + pid + '"]').forEach(function(btn) {
        if (rating === 1) btn.classList.add('active');
        else btn.classList.remove('active');
    });
    document.querySelectorAll('[data-pub-pid="' + pid + '"]').forEach(function(row) {
        if (rating === 1) row.classList.add('is-liked');
        else row.classList.remove('is-liked');
        if (row.id) {
            var detail = document.getElementById('detail-' + row.id);
            if (detail) {
                if (rating === 1) detail.classList.add('is-liked');
                else detail.classList.remove('is-liked');
            }
        }
    });
    document.querySelectorAll('[data-rec-pid="' + pid + '"]').forEach(function(card) {
        if (rating === 1) card.classList.add('is-liked');
        else card.classList.remove('is-liked');
        var recBtn = card.querySelector('.rec-rate-btn');
        if (recBtn) {
            if (rating === 1) recBtn.classList.add('active');
            else recBtn.classList.remove('active');
            var label = recBtn.querySelector('.rec-rate-label');
            if (label) label.textContent = rating === 1 ? 'Relevant' : 'Als relevant markieren';
        }
    });
}

// CPV Filter
function toggleCpvFilter() {
    if (openFilter === 'cpv') { closeAllDropdowns(); return; }
    closeAllDropdowns();
    openFilter = 'cpv';
    var chip = document.querySelector('[data-filter="cpv"]');
    chip.classList.add('open');
    var dropdown = document.getElementById('dropdown-cpv');
    var activeHtml = activeFilters.cpv.length
        ? '<div style="display:flex;flex-wrap:wrap;gap:0.2rem;margin-top:0.4rem;">' +
          activeFilters.cpv.map(function(c) {
              return '<span style="display:inline-flex;align-items:center;gap:0.2rem;padding:0.1rem 0.4rem;background:var(--accent-light);color:var(--accent);border-radius:var(--radius-sm);font-size:0.7rem;font-weight:600;font-family:JetBrains Mono,monospace;">' +
                  c + '<button onclick="removeCpvFilter(\'' + c + '\')" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:0.9rem;line-height:1;padding:0;margin-left:2px;">×</button></span>';
          }).join('') + '</div>'
        : '';
    dropdown.innerHTML =
        '<div style="padding:0.5rem;">' +
        '<div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:0.4rem;font-family:JetBrains Mono,monospace;">CPV-Präfix eingeben</div>' +
        '<div style="display:flex;gap:0.3rem;">' +
        '<input type="text" id="cpv-input" class="filter-dropdown-search" placeholder="z.B. 45262100" style="flex:1;margin-bottom:0;" onkeypress="if(event.key===\'Enter\')applyCpvFilter()">' +
        '<button onclick="applyCpvFilter()" style="padding:0.35rem 0.625rem;background:var(--accent);color:white;border:none;border-radius:var(--radius-sm);font-size:0.7rem;font-weight:600;cursor:pointer;white-space:nowrap;">+</button>' +
        '</div>' + activeHtml + '</div>';
    var chipRect = chip.getBoundingClientRect();
    var filtersRect = document.getElementById('filters-row').getBoundingClientRect();
    dropdown.style.left = (chipRect.left - filtersRect.left) + 'px';
    dropdown.classList.add('show');
    setTimeout(function() { var el = document.getElementById('cpv-input'); if (el) el.focus(); }, 50);
}

function applyCpvFilter() {
    var input = document.getElementById('cpv-input');
    if (!input) return;
    var val = input.value.trim().replace(/\s/g, '');
    if (!val) return;
    if (!activeFilters.cpv.includes(val)) activeFilters.cpv.push(val);
    var chip = document.querySelector('[data-filter="cpv"]');
    chip.classList.add('active');
    chip.querySelector('span').textContent = 'CPV (' + activeFilters.cpv.length + ')';
    closeAllDropdowns();
    renderActiveFilters();
    loadPage(1);
}

function removeCpvFilter(val) {
    var idx = activeFilters.cpv.indexOf(val);
    if (idx > -1) activeFilters.cpv.splice(idx, 1);
    var chip = document.querySelector('[data-filter="cpv"]');
    if (activeFilters.cpv.length) {
        chip.querySelector('span').textContent = 'CPV (' + activeFilters.cpv.length + ')';
    } else {
        chip.classList.remove('active');
        chip.querySelector('span').textContent = 'CPV-Code';
    }
    closeAllDropdowns();
    renderActiveFilters();
    loadPage(1);
}

// Favorites
function toggleFavorite(pid, btn) {
    var isFav = favoriteIds.has(pid);
    fetch('/api/favorites/' + (isFav?'remove':'add'), { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({project_id:pid}) })
        .then(function() { if(isFav){favoriteIds.delete(pid);btn.classList.remove('favorited');btn.innerHTML=starEmpty;} else{favoriteIds.add(pid);btn.classList.add('favorited');btn.innerHTML=starFilled;} })
        .catch(function(e){console.error(e);});
}

// ==========================================
// PROFIL TAB
// ==========================================
(function () {
    var SUBTYPE_LABELS_PF = {
        'construction': 'Bauleistung',
        'supply':       'Lieferung',
        'service':      'Dienstleistung'
    };

    function showPfToast(msg, type) {
        var toast = document.getElementById('pf-toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.remove('success', 'error');
        if (type) toast.classList.add(type);
        toast.classList.add('show');
        clearTimeout(showPfToast._t);
        showPfToast._t = setTimeout(function () { toast.classList.remove('show'); }, 2800);
    }

    function loadSubtypes() {
        var sel = document.getElementById('pf-subtype');
        if (!sel) return;
        var current = sel.dataset.current || '';
        fetch('/api/onboarding/filter-options')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var allowed = ['construction', 'supply', 'service'];
                var opts = (data.subtypes || []).filter(function (s) { return allowed.indexOf(s) !== -1; });
                if (opts.length === 0) opts = allowed;
                sel.innerHTML = '<option value="">Bitte wählen</option>';
                opts.forEach(function (s) {
                    var o = document.createElement('option');
                    o.value = s;
                    o.textContent = SUBTYPE_LABELS_PF[s] || s;
                    if (s === current) o.selected = true;
                    sel.appendChild(o);
                });
            })
            .catch(function () {
                if (sel) sel.innerHTML = '<option value="">Fehler beim Laden</option>';
            });
    }

    function readCantons() {
        var hidden = document.getElementById('cs-hidden');
        if (!hidden) return [];
        var raw = (hidden.value || '').trim();
        if (!raw) return [];
        return raw.split(',').map(function (s) { return s.trim().toUpperCase(); })
                  .filter(function (s) { return s.length > 0; });
    }

    function toIntOrNull(v) {
        if (v === '' || v === null || v === undefined) return null;
        var n = parseInt(v, 10);
        return isNaN(n) ? null : n;
    }

    window.initProfil = function () {
        profLoaded = true;
        loadSubtypes();
    };

    var form = document.getElementById('pf-form');
    if (form) {
        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var saveBtn = document.getElementById('pf-save');
            var min = toIntOrNull(document.getElementById('pf-amount-min').value);
            var max = toIntOrNull(document.getElementById('pf-amount-max').value);

            if (min !== null && max !== null && max < min) {
                showPfToast('Der Höchstbetrag darf nicht kleiner als der Mindestbetrag sein.', 'error');
                return;
            }

            var payload = {
                company_name:      (document.getElementById('pf-company').value || '').trim() || null,
                employee_count:    toIntOrNull(document.getElementById('pf-employees').value),
                headquarters:      (document.getElementById('pf-hq').value || '').trim() || null,
                project_subtype:   (document.getElementById('pf-subtype').value) || null,
                award_amount_min:  min,
                award_amount_max:  max,
                preferred_cantons: readCantons()
            };

            if (saveBtn) saveBtn.disabled = true;
            fetch('/api/profile/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (saveBtn) saveBtn.disabled = false;
                if (res.success) {
                    showPfToast('Profil gespeichert.', 'success');
                    recLoaded = false;
                } else {
                    showPfToast(res.error || 'Fehler beim Speichern.', 'error');
                }
            })
            .catch(function () {
                if (saveBtn) saveBtn.disabled = false;
                showPfToast('Netzwerkfehler. Bitte erneut versuchen.', 'error');
            });
        });
    }
})();

var currentStep = 1;
var selectedChoice = '';
var selectedVolume = '';
var ratingTenders = [];
var ratings = {};
var RATING_TARGET = 20;

var VOLUME_MAP = {
    'low':  { min: 0,      max: 100000 },
    'mid':  { min: 100000, max: 500000 },
    'high': { min: 500000, max: null   }
};

var KANTON_NAMES = {
    'AG':'Aargau','AI':'Appenzell Innerrhoden','AR':'Appenzell Ausserrhoden','BE':'Bern',
    'BL':'Basel-Landschaft','BS':'Basel-Stadt','FR':'Freiburg','GE':'Genf','GL':'Glarus',
    'GR':'Graubünden','JU':'Jura','LU':'Luzern','NE':'Neuenburg','NW':'Nidwalden',
    'OW':'Obwalden','SG':'St. Gallen','SH':'Schaffhausen','SO':'Solothurn','SZ':'Schwyz',
    'TG':'Thurgau','TI':'Tessin','UR':'Uri','VD':'Waadt','VS':'Wallis','ZG':'Zug','ZH':'Zürich'
};
var SUBTYPE_LABELS = { 'construction':'Bauleistung', 'supply':'Lieferung', 'service':'Dienstleistung' };
var VOLUME_LABELS = { 'low':"Bis 100'000 CHF", 'mid':"100'000 – 500'000 CHF", 'high':"Über 500'000 CHF" };

document.addEventListener('DOMContentLoaded', function() {
    loadSubtypes();
    ['company-name', 'project-subtype'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.addEventListener('input', validateProfile);
        if (el) el.addEventListener('change', validateProfile);
    });
    document.addEventListener('canton-selection-changed', validateProfile);
    var idsArea = document.getElementById('simap-ids');
    if (idsArea) {
        idsArea.addEventListener('input', function() {
            var ids = parseIds(this.value);
            var el = document.getElementById('ids-count');
            el.textContent = ids.length > 0 ? (ids.length + ' ID' + (ids.length > 1 ? 's' : '') + ' erkannt') : '';
        });
    }
});

function loadSubtypes() {
    var ALLOWED = ['construction', 'supply', 'service'];
    fetch('/api/onboarding/filter-options')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var sel = document.getElementById('project-subtype');
            sel.innerHTML = '<option value="">Bitte wählen</option>';
            (data.subtypes || []).forEach(function(s) {
                if (ALLOWED.indexOf(s) === -1) return;
                var opt = document.createElement('option');
                opt.value = s;
                opt.textContent = SUBTYPE_LABELS[s] || s;
                sel.appendChild(opt);
            });
        })
        .catch(function() { document.getElementById('project-subtype').innerHTML = '<option value="">Fehler beim Laden</option>'; });
}

function selectVolume(vol) {
    selectedVolume = vol;
    document.querySelectorAll('.onb-volume-option').forEach(function(el) {
        el.classList.toggle('selected', el.dataset.volume === vol);
    });
    validateProfile();
}

function getSelectedCantons() {
    var el = document.getElementById('cs-hidden');
    if (!el || !el.value) return [];
    return el.value.split(',').map(function(s) { return s.trim().toUpperCase(); })
                  .filter(function(s) { return s.length > 0; });
}

function validateProfile() {
    var ok = document.getElementById('company-name').value.trim() &&
             getSelectedCantons().length > 0 &&
             document.getElementById('project-subtype').value &&
             selectedVolume;
    document.getElementById('btn-step1').disabled = !ok;
}

function submitProfile() {
    var vol = VOLUME_MAP[selectedVolume];
    var cantons = getSelectedCantons();
    var cpvRaw = document.getElementById('cpv-codes').value.trim();
    var cpvCodes = cpvRaw
        ? cpvRaw.split(',').map(function(s) { return s.trim(); }).filter(function(s) { return s.length > 0; })
        : [];
    var payload = {
        company_name: document.getElementById('company-name').value.trim(),
        employee_count: parseInt(document.getElementById('employee-count').value) || null,
        headquarters: document.getElementById('headquarters').value.trim() || null,
        preferred_cantons: cantons,
        project_subtype: document.getElementById('project-subtype').value,
        award_amount_min: vol.min,
        award_amount_max: vol.max,
        cpv_codes: cpvCodes.length > 0 ? cpvCodes : null
    };
    fetch('/api/onboarding/profile', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.success) goToStep(2);
        else showMsg(res.error || 'Fehler beim Speichern.');
    }).catch(function() { showMsg('Verbindungsfehler.'); });
}

function goToStep(step) {
    document.querySelectorAll('.onb-step').forEach(function(s) { s.classList.remove('active'); });
    var stepId = 'step-' + step;
    if (step === 3) {
        if (selectedChoice === 'ids') stepId = 'step-3a';
        else stepId = 'step-3c';
    }
    document.getElementById(stepId).classList.add('active');
    for (var d = 1; d <= 4; d++) {
        var dot = document.getElementById('dot-' + d);
        dot.classList.remove('active', 'done');
        if (d < step) dot.classList.add('done');
        if (d === step) dot.classList.add('active');
    }
    for (var l = 1; l <= 3; l++) {
        document.getElementById('line-' + l).classList.toggle('done', l < step);
    }
    currentStep = step;
    clearMsg();
    window.scrollTo({top: 0, behavior: 'smooth'});
}

function selectChoice(choice) {
    selectedChoice = choice;
    document.getElementById('choice-ids').classList.toggle('selected', choice === 'ids');
    document.getElementById('choice-rate').classList.toggle('selected', choice === 'rate');
    document.getElementById('btn-step2').disabled = false;
}

function submitChoice() {
    if (!selectedChoice) return;
    goToStep(3);
    if (selectedChoice === 'rate') showFilterPreview();
}

function showFilterPreview() {
    var cantons = getSelectedCantons();
    var cantonLabel = cantons.length === 0
        ? '—'
        : cantons.map(function(c) { return KANTON_NAMES[c] || c; }).join(', ');
    var subtypeCode = document.getElementById('project-subtype').value;
    document.getElementById('filter-preview-canton').textContent = cantonLabel;
    document.getElementById('filter-preview-subtype').textContent = SUBTYPE_LABELS[subtypeCode] || subtypeCode;
    document.getElementById('filter-preview-volume').textContent = VOLUME_LABELS[selectedVolume] || '—';
}

function goToRating() {
    document.getElementById('step-3c').classList.remove('active');
    document.getElementById('step-3b').classList.add('active');
    loadRatingTenders();
    window.scrollTo({top: 0, behavior: 'smooth'});
}

function parseIds(text) {
    return text.split(/[\n,;]+/).map(function(s) { return s.trim(); }).filter(function(s) { return s.length > 0 && /^\d+$/.test(s); });
}

function submitIds() {
    var ids = parseIds(document.getElementById('simap-ids').value);
    if (ids.length === 0) { showMsg('Bitte mindestens eine ID eingeben.'); return; }
    fetch('/api/onboarding/simap-ids', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids})
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.success) goToStep(4);
        else showMsg(res.error || 'Fehler beim Speichern.');
    }).catch(function() { showMsg('Verbindungsfehler.'); });
}

function loadRatingTenders() {
    fetch('/api/onboarding/sample-projects')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            ratingTenders = data.projects || [];
            if (ratingTenders.length === 0) {
                document.getElementById('rating-list-container').innerHTML =
                    '<div style="text-align:center;padding:var(--space-xl);color:var(--danger);">Keine passenden Ausschreibungen für Ihren Filter gefunden.</div>';
                return;
            }
            RATING_TARGET = ratingTenders.length;
            document.getElementById('rating-total').textContent = RATING_TARGET;
            ratings = {};
            renderRatingList();
        })
        .catch(function() {
            document.getElementById('rating-list-container').innerHTML =
                '<div style="text-align:center;padding:var(--space-xl);color:var(--danger);">Fehler beim Laden.</div>';
        });
}

function renderRatingList() {
    var html = '<div class="onb-rating-list">';
    ratingTenders.forEach(function(t, idx) {
        var pid = t.id;
        var r = ratings[pid] ? ratings[pid].rating : 0;
        var cardClass = r === 1 ? 'rated-yes' : '';
        var desc = stripHtml(t.description_de || '');
        var isArchive = t.source === 'archive';

        html += '<div class="onb-rcard ' + cardClass + '">';

        if (isArchive) {
            var winnerText = t.winner_name || 'Unbekannt';
            if (t.winner_city) winnerText += ' (' + t.winner_city + ')';
            var priceText = t.award_amount ? 'CHF ' + Number(t.award_amount).toLocaleString('de-CH') : '—';
            var dateText = t.award_decision_date ? formatDate(t.award_decision_date) : '';

            html += '<div class="onb-arch-header">' +
                '<span class="onb-arch-badge">' +
                    '<svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> ' +
                    'Abgeschlossen' +
                '</span>' +
                '<div class="onb-arch-info">' +
                    '<div><span class="onb-arch-label">Gewinner:</span> <span class="onb-arch-value">' + escapeHtml(winnerText) + '</span></div>' +
                    '<div><span class="onb-arch-label">Zuschlag:</span> <span class="onb-arch-price">' + priceText + '</span></div>' +
                    (dateText ? '<div><span class="onb-arch-label">Datum:</span> <span class="onb-arch-value">' + dateText + '</span></div>' : '') +
                '</div>' +
            '</div>';
        }

        html += '<div class="onb-rcard-top">' +
            '<div class="onb-rcard-content">' +
                '<div class="onb-rcard-title">' + escapeHtml(t.title_de || 'Ohne Titel') + '</div>' +
                '<div class="onb-rcard-desc" id="rdesc-' + idx + '">' + escapeHtml(desc) + '</div>';

        if (desc.length > 120) {
            html += '<button class="onb-rcard-expand" onclick="toggleDesc(' + idx + ')">Mehr anzeigen</button>';
        }

        html += '<div class="onb-rcard-meta">';
        if (t.canton) html += '<span class="onb-rcard-tag">' + escapeHtml(KANTON_NAMES[t.canton] || t.canton) + '</span>';
        if (t.project_subtype) html += '<span class="onb-rcard-tag">' + escapeHtml(SUBTYPE_LABELS[t.project_subtype] || t.project_subtype) + '</span>';
        if (!isArchive && t.award_amount) html += '<span class="onb-rcard-tag">CHF ' + Number(t.award_amount).toLocaleString('de-CH') + '</span>';
        html += '</div>';

        if (r === 1) html += '<div class="onb-rcard-status yes"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Relevant</div>';

        html += '</div>' +
            '<div class="onb-rcard-btns">' +
                '<button class="onb-rbtn onb-rbtn-yes' + (r === 1 ? ' active' : '') + '" onclick="rateItem(' + idx + ',1)">' +
                    '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Relevant' +
                '</button>' +
            '</div>' +
        '</div>';
        html += '</div>';
    });
    html += '</div>';
    document.getElementById('rating-list-container').innerHTML = html;
}

function rateItem(idx, rating) {
    var t = ratingTenders[idx];
    var pid = t.id;
    var source = t.source || 'project';
    if (ratings[pid]) {
        delete ratings[pid];
    } else {
        ratings[pid] = { rating: 1, source: source };
    }
    updateRatingProgress();
    renderRatingList();
}

function toggleDesc(idx) {
    var desc = document.getElementById('rdesc-' + idx);
    if (desc) desc.classList.toggle('expanded');
}

function updateRatingProgress() {
    var likeCount = Object.keys(ratings).length;
    var pct = Math.min(100, Math.round(likeCount / 3 * 100));
    document.getElementById('rating-fill').style.width = pct + '%';
    document.getElementById('rating-current').textContent = likeCount;
    document.getElementById('rating-total').textContent = 3;
    document.getElementById('btn-finish-rating').disabled = likeCount < 3;
}

function finishRating() {
    var likeCount = Object.keys(ratings).length;
    if (likeCount < 3) { showMsg('Bitte mindestens 3 Ausschreibungen als "Relevant" markieren.'); return; }
    var ratingsArray = [];
    for (var pid in ratings) {
        ratingsArray.push({ project_id: pid, rating: ratings[pid].rating, source: ratings[pid].source });
    }
    fetch('/api/onboarding/submit-ratings', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ratings: ratingsArray})
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.success) goToStep(4);
        else showMsg(res.error || 'Fehler beim Speichern.');
    }).catch(function() { showMsg('Verbindungsfehler.'); });
}

function showMsg(text) {
    var c = document.getElementById('msg-container');
    c.textContent = '';
    var el = document.createElement('div');
    el.className = 'onb-msg-error';
    el.textContent = text;
    c.appendChild(el);
}
function clearMsg() { document.getElementById('msg-container').innerHTML = ''; }
function escapeHtml(t) { if(!t)return''; var d=document.createElement('div'); d.textContent=t; return d.innerHTML; }
function stripHtml(t) { return t ? t.replace(/<[^>]+>/g,'').replace(/&nbsp;/g,' ').trim() : ''; }
function formatDate(d) { if(!d)return'-'; try{return new Date(d).toLocaleDateString('de-CH',{day:'2-digit',month:'2-digit',year:'numeric'});}catch(e){return d;} }

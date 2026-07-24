"""
app.py - SAJF Strategies Tender Platform
Mit Admin Panel für Content Management
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
import os
from dotenv import load_dotenv
from supabase_client import (
    init_supabase,
    get_all_projects,
    get_projects_paginated,
    get_filter_options,
    get_project_by_id,
    search_projects,
    filter_projects,
    get_statistics,
    get_cantons,
    get_content,
    update_content,
    get_team_members,
    add_team_member,
    update_team_member,
    delete_team_member,
    get_admin_by_email,
    add_favorite,
    remove_favorite,
    get_user_favorites_ids,
    register_user,
    login_user,
    logout_user,
    get_user_by_id,
    is_onboarding_complete,
    save_user_profile,
    get_user_profile,
    save_user_simap_ids,
    save_user_ratings,
    get_random_archive_tenders,
    get_onboarding_filter_options,
    get_filtered_sample_projects,
    save_user_ratings_v2,
    get_user_recommendations,
    recommendation_diversity_metric,
    get_user_ratings_with_details,
    remove_user_rating,
    upsert_feed_rating,
    get_feed_ratings_map,
    get_test_runs_overview,
    TEST_COMPANY_SEEDS,
    seed_test_companies,
    get_user_like_count,
    get_analytics_data,
    get_tender_note,
    save_tender_note,
    get_project_by_simap_id,
    create_team,
    join_team,
    leave_team,
    delete_team,
    get_user_team,
    get_team_members_data,
    get_team_favorites,
    get_team_ratings,
    get_market_pulse_data,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'sajf-strategies-secret-2025')

# Supabase initialisieren
print("=" * 60)
print("SAJF Strategies - Tender Platform startet...")
print("=" * 60)

try:
    init_supabase()
except Exception as e:
    print(f"[ERROR] Supabase Fehler: {e}")


# ============================================
# LOGIN DECORATORS
# ============================================

def login_required(f):
    """Decorator für geschützte Seiten (erfordert Login)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_logged_in'):
            return redirect(url_for('user_login_page'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# ONBOARDING
# ============================================

@app.route('/onboarding')
@login_required
def onboarding_page():
    """Onboarding Wizard"""
    return render_template('onboarding.html')


@app.route('/api/onboarding/profile', methods=['POST'])
def api_onboarding_profile():
    """Speichere Firmenprofil"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    data = request.get_json()
    result = save_user_profile(session.get('user_id'), data)
    return jsonify(result)


@app.route('/api/onboarding/simap-ids', methods=['POST'])
def api_onboarding_simap_ids():
    """Speichere Simap Projekt-IDs"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    data = request.get_json()
    ids = data.get('ids', [])
    result = save_user_simap_ids(session.get('user_id'), ids)
    return jsonify(result)


@app.route('/api/onboarding/ratings', methods=['POST'])
def api_onboarding_ratings():
    """Speichere Tender-Bewertungen"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    data = request.get_json()
    ratings_list = data.get('ratings', [])
    result = save_user_ratings(session.get('user_id'), ratings_list)
    return jsonify(result)


@app.route('/api/onboarding/random-tenders', methods=['GET'])
def api_random_tenders():
    """Zufällige Archiv-Ausschreibungen für Rating"""
    count = request.args.get('count', 20, type=int)
    tenders = get_random_archive_tenders(count)
    return jsonify({'tenders': tenders})


# ============================================
# PUBLIC PAGES
# ============================================

@app.route('/')
def index():
    """Landing Page"""
    return render_template('landing.html')


@app.route('/how-it-works')
def how_it_works():
    """So funktioniert's Seite"""
    return render_template('how_it_works.html')


@app.route('/features')
def features():
    """Features Seite"""
    return render_template('features.html')


@app.route('/about')
def about():
    """Über uns Seite"""
    content = get_content('about')
    team = get_team_members()
    return render_template('about.html', content=content, team=team)


@app.route('/pro')
def pro():
    """Pro Version Seite"""
    content = get_content('pro')
    return render_template('pro.html', content=content)


@app.route('/support')
def support():
    """Support Seite"""
    content = get_content('support')
    return render_template('support.html', content=content)


@app.route('/ueber-uns')
def ueber_uns():
    return render_template('ueber_uns.html')


@app.route('/impressum')
def impressum():
    """Impressum (Platzhalter bis zur vollständigen Fassung)"""
    return render_template('legal_page.html', page_title='Impressum')


@app.route('/datenschutz')
def datenschutz():
    """Datenschutzerklärung (Platzhalter)"""
    return render_template('legal_page.html', page_title='Datenschutz')


@app.route('/agb')
def agb():
    """AGB (Platzhalter)"""
    return render_template('legal_page.html', page_title='Allgemeine Geschäftsbedingungen (AGB)')


# ============================================
# AUTHENTICATION PAGES
# ============================================

@app.route('/register')
def register_page():
    """Registrierungs-Seite"""
    return render_template('register.html')


@app.route('/login')
def user_login_page():
    """Login-Seite"""
    return render_template('login.html')


@app.route('/logout')
def user_logout():
    """User Logout"""
    logout_user()
    session.clear()
    return redirect(url_for('index'))


# ============================================
# AUTHENTICATION API
# ============================================

@app.route('/auth/register', methods=['POST'])
def auth_register():
    """API: Registrierung - registriert UND loggt direkt ein"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        company_name = data.get('company_name')

        if not email or not password or not company_name:
            return jsonify({'success': False, 'error': 'Alle Felder sind erforderlich'}), 400

        result = register_user(email, password, company_name)

        if result.get('success'):
            # Auto-Login: Session direkt setzen nach Registrierung
            user = result.get('user', {})
            session['user_logged_in'] = True
            session['user_id'] = user.get('id')
            session['user_email'] = user.get('email', email)
            session['user_company_name'] = user.get('company_name', company_name)

            print(f"✅ Auto-Login nach Registrierung: {email}")

            # Direkt zum Onboarding weiterleiten
            return jsonify({
                'success': True,
                'redirect': '/onboarding',
                'user': user
            }), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        print(f"[ERROR] Register API Fehler: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/auth/login', methods=['POST'])
def auth_login():
    """API: Login"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'success': False, 'error': 'E-Mail und Passwort sind erforderlich'}), 400

        result = login_user(email, password)

        if result.get('success'):
            # Setze Session
            user = result.get('user')
            session['user_logged_in'] = True
            session['user_id'] = user.get('id')
            session['user_email'] = user.get('email')
            session['user_company_name'] = user.get('company_name')

            # Prüfe ob Onboarding nötig ist
            if not is_onboarding_complete(user.get('id')):
                return jsonify({
                    'success': True,
                    'redirect': '/onboarding',
                    'user': user
                })

            # Onboarding erledigt -> publications
            return jsonify({
                'success': True,
                'redirect': '/publications',
                'user': user
            }), 200
        else:
            return jsonify(result), 401

    except Exception as e:
        print(f"[ERROR] Login API Fehler: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PROTECTED PAGES (After Login)
# ============================================

@app.route('/publications')
@login_required
def publications():
    """Ausschreibungen-Seite (geschützt) — nur nach abgeschlossenem Onboarding."""
    if not is_onboarding_complete(session.get('user_id')):
        return redirect(url_for('onboarding_page'))
    return render_template('publications.html')


@app.route('/api/profile/data', methods=['GET'])
@login_required
def api_profile_data():
    """API: Aktuelles Firmenprofil lesen."""
    user_id = session.get('user_id')
    profile = get_user_profile(user_id) or {}
    return jsonify(profile)


@app.route('/profile')
@login_required
def profile_page():
    """Profil-Seite (geschützt) - Firmendaten und Präferenzen bearbeiten."""
    user_id = session.get('user_id')
    profile = get_user_profile(user_id) or {}
    return render_template('profile.html', profile=profile)


@app.route('/api/profile/update', methods=['POST'])
def api_profile_update():
    """API: Firmenprofil aktualisieren (inkl. preferred_cantons)."""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    data = request.get_json(silent=True) or {}
    result = save_user_profile(session.get('user_id'), data)

    # Company-Name auch in der Session aktualisieren, damit UI konsistent bleibt
    if result.get('success') and data.get('company_name'):
        session['user_company_name'] = data.get('company_name')

    status = 200 if result.get('success') else 400
    return jsonify(result), status



@app.route('/api/onboarding/filter-options', methods=['GET'])
def api_onboarding_filter_options():
    return jsonify(get_onboarding_filter_options())


@app.route('/api/onboarding/sample-projects', methods=['GET'])
def api_sample_projects():
    if not session.get('user_logged_in'):
        return jsonify({'projects': []}), 401
    projects = get_filtered_sample_projects(session.get('user_id'), 30)
    return jsonify({'projects': projects})


@app.route('/api/onboarding/submit-ratings', methods=['POST'])
def api_submit_ratings():
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401
    data = request.get_json()
    result = save_user_ratings_v2(session.get('user_id'), data.get('ratings', []))
    return jsonify(result)


@app.route('/api/recommendations', methods=['GET'])
def api_recommendations():
    if not session.get('user_logged_in'):
        return jsonify({'recommendations': []}), 401
    try:
        count = int(request.args.get('count', 20))
        count = max(1, min(count, 100))
    except (TypeError, ValueError):
        count = 20
    user_id = session.get('user_id')
    recs = get_user_recommendations(user_id, count)

    hint = None
    if not recs:
        n_likes = get_user_like_count(user_id)
        if n_likes == 0:
            hint = 'no_ratings'
        else:
            profile = get_user_profile(user_id) or {}
            has_narrow = bool(
                profile.get('project_subtype') or
                profile.get('award_amount_min') is not None or
                profile.get('award_amount_max') is not None
            )
            hint = 'profile_too_narrow' if has_narrow else 'no_results'

    return jsonify({'recommendations': recs, 'hint': hint})


@app.route('/api/recommendations/diversity', methods=['GET'])
def api_recommendations_diversity():
    """Messmetrik fuer Task 4: durchschnittliche pairwise-Cosine der Top-N
    Empfehlungen, mit und ohne MMR. Zielwert <= 0.75."""
    if not session.get('user_logged_in'):
        return jsonify({'error': 'not authenticated'}), 401
    try:
        count = int(request.args.get('count', 10))
    except (TypeError, ValueError):
        count = 10
    return jsonify(recommendation_diversity_metric(session.get('user_id'), count))

@app.route('/api/user-ratings', methods=['GET'])
def api_user_ratings():
    """Alle Bewertungen des Users mit Projekt-Details"""
    if not session.get('user_logged_in'):
        return jsonify({'ratings': []}), 401
    ratings = get_user_ratings_with_details(session.get('user_id'))
    return jsonify({'ratings': ratings})


@app.route('/api/remove-rating', methods=['POST'])
def api_remove_rating():
    """Einzelnes Like entfernen (Unlike)."""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401
    data = request.get_json() or {}
    result = remove_user_rating(
        session.get('user_id'),
        data.get('tender_id'),
        data.get('source', 'project'),
    )
    return jsonify(result)


@app.route('/api/feed-rate', methods=['POST'])
def api_feed_rate():
    """Idempotentes Like aus dem Live-Feed (Tab 'Ausschreibungen').
    Body: {tender_id: uuid, rating: 0|1, source?: 'project'|'archive'}
      rating=1 setzt das Like, rating=0 entfernt es (Toggle).
    """
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401
    data = request.get_json() or {}
    result = upsert_feed_rating(
        session.get('user_id'),
        data.get('tender_id'),
        data.get('rating'),
        data.get('source', 'project'),
    )
    return jsonify(result)


@app.route('/api/feed-ratings', methods=['GET'])
def api_feed_ratings():
    """Aktuelle Ratings des Users als Map {tender_id: rating} fuer Tab 1."""
    if not session.get('user_logged_in'):
        return jsonify({'ratings': {}}), 401
    return jsonify({'ratings': get_feed_ratings_map(session.get('user_id'))})


# ============================================
# TEST-RUN DASHBOARD (nur lokal, ENV-gated)
# ============================================
def _test_runs_enabled() -> bool:
    return os.getenv('ENABLE_TEST_DASHBOARD', 'false').lower() in ('1', 'true', 'yes')


@app.route('/admin/test-runs')
def admin_test_runs():
    """Minimal-Dashboard zur Test-Auswertung (nur wenn ENABLE_TEST_DASHBOARD=true).

    Zeigt pro Test-User (@recommender.dev): Likes, Taste-Vector-Status,
    Diversity-Score (baseline vs MMR) und Top-5 Empfehlungen.
    """
    if not _test_runs_enabled():
        return 'Test-Dashboard deaktiviert. Setze ENABLE_TEST_DASHBOARD=true.', 404
    overview = get_test_runs_overview(top_n=10)
    return render_template(
        'admin_test_runs.html',
        rows=overview,
        test_company_seeds=TEST_COMPANY_SEEDS,
    )


@app.route('/api/admin/test-runs')
def api_admin_test_runs():
    """JSON-Variante des Dashboards (praktisch fuer Skripte)."""
    if not _test_runs_enabled():
        return jsonify({'error': 'disabled'}), 404
    return jsonify({'rows': get_test_runs_overview(top_n=10)})


@app.route('/api/admin/seed-test-companies', methods=['POST'])
def api_admin_seed_test_companies():
    """Legt die 5 vordefinierten Test-Firmen an (Auth + Profil). Gleiche Logik wie scripts/create_test_companies.py."""
    if not _test_runs_enabled():
        return jsonify({'error': 'disabled'}), 404
    out = seed_test_companies()
    code = 200 if out.get('success') else 400
    return jsonify(out), code

# ============================================
# FAVORITES / MERKLISTE ROUTES
# ============================================

@app.route('/api/favorites', methods=['GET'])
def api_get_favorites():
    """API: Hole Favoriten-IDs des Users"""
    if not session.get('user_logged_in'):
        return jsonify({'favorites': []})

    favorite_ids = get_user_favorites_ids(session.get('user_id'))
    return jsonify({'favorites': favorite_ids})


@app.route('/api/favorites/add', methods=['POST'])
def api_add_favorite():
    """API: Füge Favorit hinzu"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('user_id')
    data = request.get_json()

    project = {
        'id': data.get('project_id'),
        'title': data.get('title'),
        'canton': data.get('canton'),
        'description': data.get('description'),
        'simap_url': data.get('simap_url')
    }

    success = add_favorite(user_id, project)

    return jsonify({'success': success})


@app.route('/api/favorites/remove', methods=['POST'])
def api_remove_favorite():
    """API: Entferne Favorit"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('user_id')
    data = request.get_json()
    project_id = data.get('project_id')

    success = remove_favorite(user_id, project_id)

    return jsonify({'success': success})


# ============================================
# ADMIN PANEL
# ============================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin Login"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        admin = get_admin_by_email(email)
        if admin and admin.get('password') == password:
            session['admin_logged_in'] = True
            session['admin_email'] = email
            session['admin_name'] = admin.get('name', 'Admin')
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/login.html', error='Falsche Anmeldedaten')

    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    """Admin Logout"""
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    stats = get_statistics()
    return render_template('admin/dashboard.html', stats=stats)


@app.route('/admin/content/<page>', methods=['GET', 'POST'])
@admin_required
def admin_content(page):
    """Content bearbeiten"""
    if request.method == 'POST':
        data = request.form.to_dict()
        update_content(page, data)
        return redirect(url_for('admin_content', page=page, saved=1))

    content = get_content(page)
    return render_template('admin/content.html', page=page, content=content)


@app.route('/admin/team', methods=['GET'])
@admin_required
def admin_team():
    """Team verwalten"""
    team = get_team_members()
    return render_template('admin/team.html', team=team)


@app.route('/admin/team/add', methods=['POST'])
@admin_required
def admin_team_add():
    """Team-Mitglied hinzufügen"""
    data = {
        'name': request.form.get('name'),
        'role': request.form.get('role'),
        'bio': request.form.get('bio'),
        'photo_url': request.form.get('photo_url'),
        'order': request.form.get('order', 0)
    }
    add_team_member(data)
    return redirect(url_for('admin_team'))


@app.route('/admin/team/update/<member_id>', methods=['POST'])
@admin_required
def admin_team_update(member_id):
    """Team-Mitglied aktualisieren"""
    data = {
        'name': request.form.get('name'),
        'role': request.form.get('role'),
        'bio': request.form.get('bio'),
        'photo_url': request.form.get('photo_url'),
        'order': request.form.get('order', 0)
    }
    update_team_member(member_id, data)
    return redirect(url_for('admin_team'))


@app.route('/admin/team/delete/<member_id>', methods=['POST'])
@admin_required
def admin_team_delete(member_id):
    """Team-Mitglied löschen"""
    delete_team_member(member_id)
    return redirect(url_for('admin_team'))


# ============================================
# API ENDPOINTS
# ============================================

@app.route('/api/projects', methods=['GET'])
def api_get_projects():
    """API: Projekte mit Server-Side Pagination, Filter und Suche"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    search = request.args.get('search', '').strip()
    canton = request.args.get('canton', '').strip()
    cantons_str = request.args.get('cantons', '').strip()
    cantons = [c.strip() for c in cantons_str.split(',') if c.strip()] if cantons_str else []
    order_type = request.args.get('order_type', '').strip()
    process_type = request.args.get('process_type', '').strip()
    pub_type = request.args.get('pub_type', '').strip()
    sort = request.args.get('sort', 'newest')
    cpv = request.args.get('cpv', '').strip()

    result = get_projects_paginated(
        page=page, per_page=per_page, search=search,
        canton=canton, cantons=cantons, order_type=order_type,
        process_type=process_type, pub_type=pub_type,
        sort=sort, cpv=cpv
    )
    return jsonify(result)


@app.route('/api/filter-options', methods=['GET'])
def api_filter_options():
    """API: Unique Filter-Werte aus DB"""
    options = get_filter_options()
    return jsonify(options)


@app.route('/api/projects/<project_id>', methods=['GET'])
def api_get_project(project_id):
    project = get_project_by_id(project_id)
    if project:
        return jsonify(project)
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/search', methods=['GET'])
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = search_projects(query)
    return jsonify(results)


@app.route('/api/filter', methods=['GET'])
def api_filter():
    canton = request.args.get('canton')
    process_type = request.args.get('process_type')
    order_type = request.args.get('order_type')

    results = filter_projects(
        canton=canton,
        process_type=process_type,
        order_type=order_type
    )
    return jsonify(results)


@app.route('/api/cantons', methods=['GET'])
def api_cantons():
    cantons = get_cantons()
    return jsonify(cantons)


@app.route('/api/statistics', methods=['GET'])
def api_statistics():
    stats = get_statistics()
    return jsonify(stats)


# ============================================
# ANALYTICS DASHBOARD
# ============================================

@app.route('/api/analytics', methods=['GET'])
def api_analytics():
    if not session.get('user_logged_in'):
        return jsonify({'error': 'Nicht eingeloggt'}), 401
    return jsonify(get_analytics_data())


# ============================================
# TENDER DETAIL PAGE
# ============================================

@app.route('/tender/<simap_id>')
@login_required
def tender_detail(simap_id):
    project = get_project_by_simap_id(simap_id)
    if not project:
        return render_template('tender_detail.html', project=None, simap_id=simap_id, note='')
    uid = session.get('user_id') or ''
    note = get_tender_note(uid, simap_id)
    return render_template('tender_detail.html', project=project, simap_id=simap_id, note=note)


@app.route('/api/tender/<simap_id>/note', methods=['GET'])
@login_required
def api_tender_note_get(simap_id):
    note = get_tender_note(session.get('user_id') or '', simap_id)
    return jsonify({'note': note})


@app.route('/api/tender/<simap_id>/note', methods=['POST'])
@login_required
def api_tender_note_save(simap_id):
    data = request.get_json(silent=True) or {}
    result = save_tender_note(session.get('user_id') or '', simap_id, data.get('note', ''))
    return jsonify(result)


# ============================================
# TEAM ACCOUNTS
# ============================================

@app.route('/team')
@login_required
def team_page():
    uid = session.get('user_id') or ''
    team = get_user_team(uid)
    members = get_team_members_data(team['id']) if team else []
    return render_template('team.html', team=team, members=members)


@app.route('/api/team/create', methods=['POST'])
@login_required
def api_team_create():
    data = request.get_json(silent=True) or {}
    result = create_team(session.get('user_id') or '', data.get('name', ''))
    return jsonify(result), (200 if result.get('success') else 400)


@app.route('/api/team/join', methods=['POST'])
@login_required
def api_team_join():
    data = request.get_json(silent=True) or {}
    result = join_team(session.get('user_id') or '', data.get('invite_code', ''))
    return jsonify(result), (200 if result.get('success') else 400)


@app.route('/api/team/leave', methods=['POST'])
@login_required
def api_team_leave():
    uid = session.get('user_id') or ''
    team = get_user_team(uid)
    if not team:
        return jsonify({'success': False, 'error': 'Kein Team'}), 400
    result = leave_team(uid, team['id'])
    return jsonify(result), (200 if result.get('success') else 400)


@app.route('/api/team/delete', methods=['POST'])
@login_required
def api_team_delete():
    uid = session.get('user_id') or ''
    team = get_user_team(uid)
    if not team:
        return jsonify({'success': False, 'error': 'Kein Team'}), 400
    result = delete_team(uid, team['id'])
    return jsonify(result), (200 if result.get('success') else 400)


@app.route('/api/team/info', methods=['GET'])
@login_required
def api_team_info():
    team = get_user_team(session.get('user_id') or '')
    if not team:
        return jsonify({'team': None})
    members = get_team_members_data(team['id'])
    return jsonify({'team': team, 'members': members})


@app.route('/api/team/favorites', methods=['GET'])
@login_required
def api_team_favorites():
    team = get_user_team(session.get('user_id') or '')
    if not team:
        return jsonify({'favorites': []})
    return jsonify({'favorites': get_team_favorites(team['id'])})


@app.route('/api/team/ratings', methods=['GET'])
@login_required
def api_team_ratings():
    team = get_user_team(session.get('user_id') or '')
    if not team:
        return jsonify({'ratings': []})
    return jsonify({'ratings': get_team_ratings(team['id'])})


# ============================================
# MARKTPULS — public market statistics
# ============================================

@app.route('/marktpuls')
def marktpuls():
    import json
    data = get_market_pulse_data()
    stats = get_statistics()
    return render_template(
        'marktpuls.html',
        data_json=json.dumps(data, ensure_ascii=False),
        total_all=stats.get('total', data['total_all']),
        today=stats.get('today', 0),
        avg_per_day=data['avg_per_day'],
        total_30d=data['total_30d'],
    )


# ============================================
# BOB — CHAT ASSISTANT
# ============================================

_BOB_SYSTEM = """Du bist Bob, Assistent von SAJF Strategies.

ÜBER SAJF STRATEGIES:
- Digitale Plattform für öffentliche Ausschreibungen in der Schweiz, basiert in Zürich
- Aggregiert Ausschreibungen von simap.ch, stündlich aktualisiert
- Kostenlose Basis-Version: Suche, Filter nach Kanton/Typ/Verfahren, Empfehlungen, Favoriten
- Pro-Version: E-Mail-Benachrichtigungen, KI-Analyse, Priority Support
- Rechtlich massgebend ist immer www.simap.ch

REGELN:
- Antworte sachlich, präzise, auf Deutsch — maximal 2 Sätze
- Keine Füllwörter, keine Wiederholungen, kein Small Talk
- Nur Themen: öffentliche Ausschreibungen und die Plattform selbst
- Verrate KEINE technischen Details (Embeddings, ML-Modelle, Algorithmen, Datenbankstruktur, Code)
- Bei themenfremden Fragen: einen Satz Hinweis, kein weiteres Eingehen
- Wenn Ausschreibungsdaten als Kontext vorhanden, nutze sie für konkrete Antworten"""


@app.route('/api/bob/chat', methods=['POST'])
def api_bob_chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not user_message:
        return jsonify({'error': 'Keine Nachricht'}), 400

    api_key = os.getenv('GROQ_API_KEY', '')
    if not api_key or api_key.startswith('your-'):
        return jsonify({'reply': 'Ich bin gerade nicht verfügbar. Bitte wenden Sie sich an support@sajf-strategies.ch.'})

    # Search for relevant tenders when the question is tender-related
    tender_context = ''
    tender_keywords = ['ausschreibung', 'tender', 'auftrag', 'vergabe', 'kanton', 'beschaffung',
                       'frist', 'einreichung', 'simap', 'submission', 'projekt']
    if any(kw in user_message.lower() for kw in tender_keywords):
        try:
            results = get_projects_paginated(page=1, per_page=5, search=user_message)
            projects = results.get('projects', [])
            if projects:
                tender_context = '\n\nAktuelle relevante Ausschreibungen aus der Datenbank:\n'
                for p in projects:
                    pub = (p.get('publication_date') or '')[:10]
                    line = f"- {p['title']} | {p.get('organization', '')} | Kanton: {p.get('canton', '')} | Veröffentlicht: {pub}"
                    if p.get('deadline'):
                        line += f" | Einreichungsfrist: {str(p['deadline'])[:10]}"
                    tender_context += line + '\n'
        except Exception as e:
            print(f'Bob tender search error: {e}')

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        messages = [{'role': 'system', 'content': _BOB_SYSTEM + tender_context}]
        for h in history[-10:]:
            role = h.get('role') or ''
            content = h.get('content') or ''
            if role in ('user', 'assistant') and content:
                messages.append({'role': role, 'content': content})
        messages.append({'role': 'user', 'content': user_message})

        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=messages,
            max_tokens=200,
            temperature=0.3,
        )
        return jsonify({'reply': response.choices[0].message.content})
    except Exception as e:
        print(f'Bob chat error: {e}')
        return jsonify({'reply': 'Entschuldigung, ich kann gerade nicht antworten. Bitte versuchen Sie es später erneut.'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "=" * 60)
    print("SAJF Strategies - Tender Platform")
    print("Datenbank: Supabase")
    print(f"URL: http://127.0.0.1:{port}")
    print(f"Admin: http://127.0.0.1:{port}/admin")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=port)

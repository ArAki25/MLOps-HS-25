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
    get_pro_user,
    get_user_favorites,
    add_favorite,
    remove_favorite,
    get_user_favorites_ids,
    register_user,
    login_user,
    logout_user,
    get_user_by_id,
    is_onboarding_complete,
    save_user_profile,
    save_user_simap_ids,
    save_user_ratings,
    get_random_archive_tenders,
    # NEU:
    get_onboarding_filter_options,
    get_filtered_sample_projects,
    save_user_ratings_v2,
    get_user_recommendations,
    get_user_ratings_with_details,
    update_single_rating,
)
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
    get_pro_user,
    get_user_favorites,
    add_favorite,
    remove_favorite,
    get_user_favorites_ids,
    register_user,
    login_user,
    logout_user,
    get_user_by_id,
    is_onboarding_complete,
    save_user_profile,
    save_user_simap_ids,
    save_user_ratings,
    get_random_archive_tenders,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'sajf-strategies-secret-2025')

# Supabase initialisieren
print("=" * 60)
print("🚀 SAJF Strategies - Tender Platform startet...")
print("=" * 60)

try:
    init_supabase()
except Exception as e:
    print(f"❌ Supabase Fehler: {e}")


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
        print(f"❌ Register API Fehler: {e}")
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
        print(f"❌ Login API Fehler: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PROTECTED PAGES (After Login)
# ============================================

@app.route('/publications')
@login_required
def publications():
    """Ausschreibungen-Seite (geschützt)"""
    return render_template('publications.html')


# ============================================
# OLD PRO USER LOGIN (kept for compatibility)
# ============================================

@app.route('/login-old', methods=['GET', 'POST'])
def user_login():
    """Old Pro User Login (für Kompatibilität)"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = get_pro_user(username, password)
        if user:
            session['pro_logged_in'] = True
            session['pro_user_id'] = user.get('id')
            session['pro_company_name'] = user.get('company_name')
            session['pro_table_name'] = user.get('ml_table_name')
            return redirect(url_for('pro_dashboard'))
        else:
            return render_template('login.html', error='Falsche Anmeldedaten')

    return render_template('login.html')


def pro_user_required(f):
    """Decorator für Pro-User Seiten"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pro_logged_in'):
            return redirect(url_for('user_login_page'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/pro/dashboard')
@pro_user_required
def pro_dashboard():
    """Pro User Dashboard"""
    stats = get_statistics()
    company_name = session.get('pro_company_name', 'Unternehmen')

    recommended_count = 0
    match_rate = 0
    table_name = session.get('pro_table_name')
    if table_name:
        try:
            from supabase_client import get_recommended_projects
            recommended = get_recommended_projects(table_name)
            recommended_count = len(recommended)
            match_rate = 85
        except:
            pass

    return render_template('pro_dashboard.html',
                           stats=stats,
                           company_name=company_name,
                           recommended_count=recommended_count,
                           match_rate=match_rate)


@app.route('/pro/tenders')
@pro_user_required
def pro_tenders():
    """Pro User - Alle Tenders"""
    return render_template('index.html')


@app.route('/pro/recommended')
@pro_user_required
def pro_recommended():
    """Pro User - Empfohlene Aufträge"""
    table_name = session.get('pro_table_name')
    company_name = session.get('pro_company_name', 'Unternehmen')

    projects = []
    avg_match = 0
    if table_name:
        try:
            from supabase_client import get_recommended_projects
            projects = get_recommended_projects(table_name)

            if projects:
                total_prob = sum(p.get('probability', 0) for p in projects)
                avg_match = int((total_prob / len(projects)) * 100)
        except Exception as e:
            print(f"❌ Fehler beim Laden empfohlener Projekte: {e}")

    return render_template('pro_recommended.html',
                           projects=projects,
                           company_name=company_name,
                           avg_match=avg_match)

@app.route('/api/onboarding/filter-options', methods=['GET'])
def api_onboarding_filter_options():
    return jsonify(get_onboarding_filter_options())


@app.route('/api/onboarding/sample-projects', methods=['GET'])
def api_sample_projects():
    if not session.get('user_logged_in'):
        return jsonify({'projects': []}), 401
    projects = get_filtered_sample_projects(session.get('user_id'),20)
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
    recs = get_user_recommendations(session.get('user_id'), 20)
    return jsonify({'recommendations': recs})

@app.route('/api/user-ratings', methods=['GET'])
def api_user_ratings():
    """Alle Bewertungen des Users mit Projekt-Details"""
    if not session.get('user_logged_in'):
        return jsonify({'ratings': []}), 401
    ratings = get_user_ratings_with_details(session.get('user_id'))
    return jsonify({'ratings': ratings})


@app.route('/api/update-rating', methods=['POST'])
def api_update_rating():
    """Einzelne Bewertung ändern"""
    if not session.get('user_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401
    data = request.get_json()
    result = update_single_rating(
        session.get('user_id'),
        data.get('tender_id'),
        data.get('rating')
    )
    return jsonify(result)


# ============================================
# FAVORITES / MERKLISTE ROUTES
# ============================================

@app.route('/pro/favorites')
@pro_user_required
def pro_favorites():
    """Pro User - Merkliste"""
    user_id = session.get('pro_user_id')
    company_name = session.get('pro_company_name', 'Unternehmen')

    favorites = get_user_favorites(user_id)

    return render_template('pro_favorites.html',
                           favorites=favorites,
                           company_name=company_name)


@app.route('/api/favorites', methods=['GET'])
def api_get_favorites():
    """API: Hole Favoriten-IDs des Users"""
    if not (session.get('user_logged_in') or session.get('pro_logged_in')):
        return jsonify({'favorites': []})

    user_id = session.get('user_id') or session.get('pro_user_id')
    favorite_ids = get_user_favorites_ids(user_id)

    return jsonify({'favorites': favorite_ids})


@app.route('/api/favorites/add', methods=['POST'])
def api_add_favorite():
    """API: Füge Favorit hinzu"""
    if not (session.get('user_logged_in') or session.get('pro_logged_in')):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('user_id') or session.get('pro_user_id')
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
    if not (session.get('user_logged_in') or session.get('pro_logged_in')):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('user_id') or session.get('pro_user_id')
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
    order_type = request.args.get('order_type', '').strip()
    process_type = request.args.get('process_type', '').strip()
    pub_type = request.args.get('pub_type', '').strip()
    sort = request.args.get('sort', 'newest')

    result = get_projects_paginated(
        page=page, per_page=per_page, search=search,
        canton=canton, order_type=order_type,
        process_type=process_type, pub_type=pub_type,
        sort=sort
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


@app.route('/pro/bkp-calculator')
@pro_user_required
def pro_bkp_calculator():
    """Pro User - BKP Rechner"""
    company_name = session.get('pro_company_name', 'Unternehmen')

    return render_template('pro_bkp_calculator.html',
                           company_name=company_name)


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🌐 SAJF Strategies - Tender Platform")
    print("📊 Datenbank: Supabase")
    print("🔗 URL: http://127.0.0.1:5000")
    print("🔐 Admin: http://127.0.0.1:5000/admin")
    print("=" * 60)

    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

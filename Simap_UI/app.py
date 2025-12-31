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
    get_user_favorites_ids
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
# ADMIN LOGIN DECORATOR
# ============================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# PUBLIC PAGES
# ============================================

@app.route('/')
def index():
    """Hauptseite - Tenders"""
    return render_template('index.html')


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
# PRO USER LOGIN & DASHBOARD
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    """Pro User Login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Prüfe Pro-User in Datenbank
        user = get_pro_user(username, password)
        if user:
            session['pro_logged_in'] = True
            session['pro_user_id'] = user.get('id')
            session['pro_company_name'] = user.get('company_name')
            session['pro_table_name'] = user.get('ml_table_name')  # z.B. 'company_a_predictions'
            return redirect(url_for('pro_dashboard'))
        else:
            return render_template('login.html', error='Falsche Anmeldedaten')
    
    return render_template('login.html')


@app.route('/logout')
def user_logout():
    """Pro User Logout"""
    session.pop('pro_logged_in', None)
    session.pop('pro_user_id', None)
    session.pop('pro_company_name', None)
    session.pop('pro_table_name', None)
    return redirect(url_for('index'))


def pro_user_required(f):
    """Decorator für Pro-User Seiten"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pro_logged_in'):
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/pro/dashboard')
@pro_user_required
def pro_dashboard():
    """Pro User Dashboard"""
    stats = get_statistics()
    company_name = session.get('pro_company_name', 'Unternehmen')
    
    # Hole empfohlene Aufträge count (falls ML-Tabelle existiert)
    recommended_count = 0
    match_rate = 0
    table_name = session.get('pro_table_name')
    if table_name:
        try:
            from supabase_client import get_recommended_projects
            recommended = get_recommended_projects(table_name)
            recommended_count = len(recommended)
            match_rate = 85  # Beispiel, später aus ML-Daten
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

            # Berechne durchschnittliche Match-Rate
            if projects:
                total_prob = sum(p.get('probability', 0) for p in projects)
                avg_match = int((total_prob / len(projects)) * 100)
        except Exception as e:
            print(f"❌ Fehler beim Laden empfohlener Projekte: {e}")

    return render_template('pro_recommended.html',
                           projects=projects,
                           company_name=company_name,
                           avg_match=avg_match)


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
    if not session.get('pro_logged_in'):
        return jsonify({'favorites': []})

    user_id = session.get('pro_user_id')
    favorite_ids = get_user_favorites_ids(user_id)

    return jsonify({'favorites': favorite_ids})


@app.route('/api/favorites/add', methods=['POST'])
def api_add_favorite():
    """API: Füge Favorit hinzu"""
    if not session.get('pro_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('pro_user_id')
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
    if not session.get('pro_logged_in'):
        return jsonify({'success': False, 'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('pro_user_id')
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
    limit = request.args.get('limit', 50, type=int)
    projects = get_all_projects(limit=limit)
    return jsonify(projects)


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


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🌐 SAJF Strategies - Tender Platform")
    print("📊 Datenbank: Supabase")
    print("🔗 URL: http://127.0.0.1:5000")
    print("🔐 Admin: http://127.0.0.1:5000/admin")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

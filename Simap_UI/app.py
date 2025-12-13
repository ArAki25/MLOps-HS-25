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
    get_admin_by_email
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

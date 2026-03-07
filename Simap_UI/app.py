"""
app.py - SAJF Platform
2 Seiten: Landing + Ausschreibungen (simap.ch Style)
"""
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
import os
from dotenv import load_dotenv
from supabase_client import (
    init_supabase, get_all_projects, get_project_by_id,
    search_projects, filter_projects, get_statistics,
    get_cantons, get_order_types, get_process_types,
    register_user, login_user, logout_user,
    get_user_favorites, get_user_favorites_ids,
    add_favorite, remove_favorite
)

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'sajf-2026-secret')

try:
    init_supabase()
except Exception as e:
    print(f"❌ Supabase Fehler: {e}")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_logged_in'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ============================================
# PAGES
# ============================================

@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/ausschreibungen')
@login_required
def ausschreibungen():
    return render_template('publications.html')


@app.route('/merkliste')
@login_required
def merkliste():
    user_id = session.get('user_id')
    favorites = get_user_favorites(user_id)
    return render_template('merkliste.html', favorites=favorites)


@app.route('/logout')
def user_logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))


# ============================================
# AUTH API
# ============================================

@app.route('/auth/register', methods=['POST'])
def auth_register():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        company_name = data.get('company_name')
        if not email or not password or not company_name:
            return jsonify({'success': False, 'error': 'Alle Felder erforderlich'}), 400
        result = register_user(email, password, company_name)
        if result.get('success'):
            return jsonify(result), 200
        return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/auth/login', methods=['POST'])
def auth_login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'success': False, 'error': 'E-Mail und Passwort erforderlich'}), 400
        result = login_user(email, password)
        if result.get('success'):
            user = result.get('user')
            session['user_logged_in'] = True
            session['user_id'] = user.get('id')
            session['user_email'] = user.get('email')
            session['user_company'] = user.get('company_name')
            return jsonify(result), 200
        return jsonify(result), 401
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# DATA API
# ============================================

@app.route('/api/projects')
def api_projects():
    limit = request.args.get('limit', 200, type=int)
    projects = get_all_projects(limit=limit)
    return jsonify(projects)


@app.route('/api/projects/<project_id>')
def api_project(project_id):
    project = get_project_by_id(project_id)
    if project:
        return jsonify(project)
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    return jsonify(search_projects(q))


@app.route('/api/filter')
def api_filter():
    canton = request.args.get('canton')
    order_type = request.args.get('order_type')
    process_type = request.args.get('process_type')
    pub_type = request.args.get('pub_type')
    search = request.args.get('search')
    results = filter_projects(
        canton=canton, order_type=order_type,
        process_type=process_type, pub_type=pub_type,
        search=search
    )
    return jsonify(results)


@app.route('/api/cantons')
def api_cantons():
    return jsonify(get_cantons())


@app.route('/api/order_types')
def api_order_types():
    return jsonify(get_order_types())


@app.route('/api/process_types')
def api_process_types():
    return jsonify(get_process_types())


@app.route('/api/statistics')
def api_statistics():
    return jsonify(get_statistics())


# ============================================
# FAVORITES API
# ============================================

@app.route('/api/favorites')
def api_get_favorites():
    if not session.get('user_logged_in'):
        return jsonify({'favorites': []})
    user_id = session.get('user_id')
    return jsonify({'favorites': get_user_favorites_ids(user_id)})


@app.route('/api/favorites/add', methods=['POST'])
def api_add_favorite():
    if not session.get('user_logged_in'):
        return jsonify({'success': False}), 401
    user_id = session.get('user_id')
    data = request.get_json()
    project = {
        'id': data.get('project_id'),
        'title': data.get('title'),
        'canton': data.get('canton'),
        'description': data.get('description'),
        'simap_url': data.get('simap_url')
    }
    return jsonify({'success': add_favorite(user_id, project)})


@app.route('/api/favorites/remove', methods=['POST'])
def api_remove_favorite():
    if not session.get('user_logged_in'):
        return jsonify({'success': False}), 401
    user_id = session.get('user_id')
    data = request.get_json()
    return jsonify({'success': remove_favorite(user_id, data.get('project_id'))})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 SAJF → http://127.0.0.1:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)
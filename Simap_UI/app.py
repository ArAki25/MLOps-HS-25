"""
app.py - SAJF Strategies Tender Platform
Zeigt öffentliche Ausschreibungen von simap.ch
Keine Login-Funktion, kein ML - einfach Daten anzeigen
"""

from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
from supabase_client import (
    init_supabase,
    get_all_projects,
    get_project_by_id,
    search_projects,
    filter_projects,
    get_statistics,
    get_cantons
)

load_dotenv()

app = Flask(__name__)

# Supabase initialisieren
print("=" * 60)
print("🚀 SAJF Strategies - Tender Platform startet...")
print("=" * 60)

try:
    init_supabase()
except Exception as e:
    print(f"❌ Supabase Fehler: {e}")


@app.route('/')
def index():
    """Hauptseite - Zeigt alle Ausschreibungen"""
    return render_template('index.html')


@app.route('/api/projects', methods=['GET'])
def api_get_projects():
    """
    GET /api/projects
    Optional: ?limit=50
    """
    limit = request.args.get('limit', 50, type=int)
    projects = get_all_projects(limit=limit)
    return jsonify(projects)


@app.route('/api/projects/<project_id>', methods=['GET'])
def api_get_project(project_id):
    """GET /api/projects/<id> - Einzelnes Projekt"""
    project = get_project_by_id(project_id)
    if project:
        return jsonify(project)
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/search', methods=['GET'])
def api_search():
    """
    GET /api/search?q=keyword
    Sucht in Titel und Beschreibung
    """
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    results = search_projects(query)
    return jsonify(results)


@app.route('/api/filter', methods=['GET'])
def api_filter():
    """
    GET /api/filter?canton=ZH&process_type=open&order_type=service
    """
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
    """GET /api/cantons - Liste aller Kantone"""
    cantons = get_cantons()
    return jsonify(cantons)


@app.route('/api/statistics', methods=['GET'])
def api_statistics():
    """GET /api/statistics - Statistiken"""
    stats = get_statistics()
    return jsonify(stats)


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🌐 SAJF Strategies - Tender Platform")
    print("📊 Datenbank: Supabase (stündlich aktualisiert)")
    print("🔗 URL: http://127.0.0.1:5000")
    print("=" * 60)

    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
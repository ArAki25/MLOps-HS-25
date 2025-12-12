"""
app.py - Finale Simap.ch Anwendung
Mit Supabase Datenbank & ML-Modell Integration
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import os
from dotenv import load_dotenv

# Supabase Datenbank
from Simap_UI.supabase_database import (
    init_supabase,
    get_user_by_email,
    get_all_ausschreibungen,
    get_ausschreibung_by_id,
    get_ausschreibungen_by_status,
    create_ausschreibung,
    update_ausschreibung,
    delete_ausschreibung,
    save_ausschreibung_for_user,
    get_saved_ausschreibungen_for_user,
    get_statistics,
    search_ausschreibungen,
    filter_ausschreibungen,
    bulk_create_ausschreibungen,
    add_example_data
)

# ML-Modell
from Simap_UI.ml_integration import (
    initialize_ml_system,
    predict_ausschreibung,
    calculate_relevanz
)
import os
import sys

# Füge Simap_UI zum Path hinzu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Simap_UI'))

# Setze Template/Static Ordner
template_dir = os.path.join(os.path.dirname(__file__), 'Simap_UI', 'templates')
static_dir = os.path.join(os.path.dirname(__file__), 'Simap_UI', 'static')

from flask import Flask
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# ... rest deines Codes
load_dotenv()


# TEST: Zeige ob .env geladen wurde
print("DEBUG: SUPABASE_URL =", os.getenv('SUPABASE_URL'))
print("DEBUG: SUPABASE_KEY =", os.getenv('SUPABASE_KEY')[:20] if os.getenv('SUPABASE_KEY') else None)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dein-geheimer-schluessel')

# Initialisierung beim Start
print("=" * 60)
print("🚀 Simap.ch KI-Assistent startet...")
print("=" * 60)

# Supabase initialisieren
try:
    init_supabase()
except Exception as e:
    print(f"❌ Supabase Fehler: {e}")
    print("Bitte überprüfe SUPABASE_URL und SUPABASE_KEY in .env")

# ML-System initialisieren
try:
    initialize_ml_system()
except Exception as e:
    print(f"⚠️  ML-System Warnung: {e}")
    print("Verwende Fallback-Modell für Vorhersagen")


@app.before_request
def check_example_data():
    """Erstelle Beispieldaten beim ersten Start"""
    if not hasattr(app, 'data_initialized'):
        try:
            add_example_data()
            app.data_initialized = True
        except Exception as e:
            print(f"Beispieldaten-Fehler: {e}")


@app.route('/')
def index():
    """Hauptseite - Dashboard oder Login"""
    if not session.get('logged_in'):
        return render_template('login.html')

    try:
        # Hole Ausschreibungen aus Supabase
        ausschreibungen = get_all_ausschreibungen(limit=50)

        # Hole Statistiken
        stats = get_statistics()

        return render_template('dashboard.html',
                               ausschreibungen=ausschreibungen,
                               stats=stats,
                               user=session)
    except Exception as e:
        print(f"Fehler beim Laden des Dashboards: {e}")
        return render_template('dashboard.html',
                               ausschreibungen=[],
                               stats={'neue': 0, 'laufend': 0, 'abgeschlossen': 0},
                               user=session)


@app.route('/login', methods=['POST'])
def login():
    """Login mit Supabase-Validierung"""
    email = request.form.get('email')
    password = request.form.get('password')

    try:
        user = get_user_by_email(email)

        if user and user['password'] == password:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['firma'] = user['firma']
            session['name'] = user['name']
            return redirect(url_for('index'))
    except Exception as e:
        print(f"Login-Fehler: {e}")

    return redirect(url_for('index'))


@app.route('/logout', methods=['POST'])
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('index'))


# ============================================
# API ENDPOINTS - AUSSCHREIBUNGEN
# ============================================

@app.route('/api/ausschreibungen', methods=['GET'])
def api_get_ausschreibungen():
    """
    GET /api/ausschreibungen
    Optional: ?limit=100
    """
    limit = request.args.get('limit', 100, type=int)
    ausschreibungen = get_all_ausschreibungen(limit=limit)
    return jsonify(ausschreibungen)


@app.route('/api/ausschreibungen/<int:id>', methods=['GET'])
def api_get_ausschreibung(id):
    """GET /api/ausschreibungen/1"""
    ausschreibung = get_ausschreibung_by_id(id)
    if ausschreibung:
        return jsonify(ausschreibung)
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/ausschreibungen', methods=['POST'])
def api_create_ausschreibung():
    """
    POST /api/ausschreibungen

    Body (JSON):
    {
        "titel": "...",
        "unternehmen": "...",
        "beschreibung": "...",
        "kategorie": "...",
        "wert": "...",
        "deadline": "..."
    }
    """
    data = request.get_json()

    try:
        # ML-Vorhersage für neue Ausschreibung
        predictions = predict_ausschreibung(data)

        # Füge Predictions hinzu
        data['relevanz'] = predictions['relevanz']
        data['order_type'] = predictions['order_type']
        data['size_bucket'] = predictions['size_bucket']
        data['status'] = data.get('status', 'neu')

        # Speichere in Supabase
        ausschreibung = create_ausschreibung(data)

        return jsonify({
            'success': True,
            'ausschreibung': ausschreibung,
            'predictions': predictions
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ausschreibungen/<int:id>', methods=['PUT'])
def api_update_ausschreibung(id):
    """PUT /api/ausschreibungen/1"""
    data = request.get_json()

    try:
        ausschreibung = update_ausschreibung(id, data)
        if ausschreibung:
            return jsonify({'success': True, 'ausschreibung': ausschreibung})
        return jsonify({'error': 'Nicht gefunden'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ausschreibungen/<int:id>', methods=['DELETE'])
def api_delete_ausschreibung(id):
    """DELETE /api/ausschreibungen/1"""
    try:
        success = delete_ausschreibung(id)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Nicht gefunden'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ausschreibungen/status/<status>', methods=['GET'])
def api_get_by_status(status):
    """GET /api/ausschreibungen/status/neu"""
    ausschreibungen = get_ausschreibungen_by_status(status)
    return jsonify(ausschreibungen)


# ============================================
# API ENDPOINTS - SUCHE & FILTER
# ============================================

@app.route('/api/search', methods=['GET'])
def api_search():
    """
    GET /api/search?q=software
    """
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    results = search_ausschreibungen(query)
    return jsonify(results)


@app.route('/api/filter', methods=['GET'])
def api_filter():
    """
    GET /api/filter?status=neu&kategorie=IT&min_relevanz=80
    """
    status = request.args.get('status')
    kategorie = request.args.get('kategorie')
    min_relevanz = request.args.get('min_relevanz', type=int)

    results = filter_ausschreibungen(
        status=status,
        kategorie=kategorie,
        min_relevanz=min_relevanz
    )
    return jsonify(results)


# ============================================
# API ENDPOINTS - ML PREDICTIONS
# ============================================

@app.route('/api/predict', methods=['POST'])
def api_predict():
    """
    POST /api/predict

    Body:
    {
        "titel": "Software Entwicklung",
        "beschreibung": "CRM System",
        "kategorie": "IT",
        "wert": "200000 CHF"
    }

    Returns:
    {
        "relevanz": 88,
        "order_type": "service",
        "size_bucket": "mittel"
    }
    """
    data = request.get_json()

    try:
        predictions = predict_ausschreibung(data)
        return jsonify(predictions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/calculate-relevanz', methods=['POST'])
def api_calculate_relevanz():
    """
    POST /api/calculate-relevanz

    Schnellere Version nur für Relevanz-Berechnung
    """
    data = request.get_json()

    try:
        relevanz = calculate_relevanz(data)
        return jsonify({'relevanz': relevanz})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# API ENDPOINTS - USER ACTIONS
# ============================================

@app.route('/api/user/save-ausschreibung', methods=['POST'])
def api_save_ausschreibung():
    """
    POST /api/user/save-ausschreibung

    Body:
    {
        "ausschreibung_id": 1,
        "notizen": "Interessant"
    }
    """
    if not session.get('logged_in'):
        return jsonify({'error': 'Nicht eingeloggt'}), 401

    data = request.get_json()
    user_id = session.get('user_id')
    ausschreibung_id = data.get('ausschreibung_id')
    notizen = data.get('notizen')

    try:
        saved = save_ausschreibung_for_user(user_id, ausschreibung_id, notizen)
        return jsonify({'success': True, 'saved': saved})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/saved-ausschreibungen', methods=['GET'])
def api_get_saved():
    """GET /api/user/saved-ausschreibungen"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Nicht eingeloggt'}), 401

    user_id = session.get('user_id')
    ausschreibungen = get_saved_ausschreibungen_for_user(user_id)
    return jsonify(ausschreibungen)


@app.route('/api/statistics', methods=['GET'])
def api_get_statistics():
    """GET /api/statistics"""
    stats = get_statistics()
    return jsonify(stats)


# ============================================
# WEBHOOK - TÄGLICHE UPDATES
# ============================================

@app.route('/webhook/daily-update', methods=['POST'])
def webhook_daily_update():
    """
    POST /webhook/daily-update

    Body: Liste von neuen Ausschreibungen von Simap.ch
    """
    data = request.get_json()
    neue_ausschreibungen = data.get('ausschreibungen', [])

    try:
        # ML-Predictions für alle neuen Ausschreibungen
        for ausschreibung in neue_ausschreibungen:
            predictions = predict_ausschreibung(ausschreibung)
            ausschreibung['relevanz'] = predictions['relevanz']
            ausschreibung['order_type'] = predictions['order_type']
            ausschreibung['size_bucket'] = predictions['size_bucket']
            ausschreibung['status'] = 'neu'

        # Bulk-Insert in Supabase
        count = bulk_create_ausschreibungen(neue_ausschreibungen)

        return jsonify({
            'success': True,
            'added': count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# ADMIN ENDPOINTS
# ============================================

@app.route('/admin/retrain-models', methods=['POST'])
def admin_retrain():
    """
    POST /admin/retrain-models

    Trainiert ML-Modelle neu mit aktuellen Daten
    """
    # Nur für Admins
    if not session.get('logged_in') or session.get('email') != 'admin@musterfirma.ch':
        return jsonify({'error': 'Keine Berechtigung'}), 403

    try:
        from Simap_UI.ml_integration import train_models, save_models

        success = train_models()
        if success:
            save_models()
            return jsonify({'success': True, 'message': 'Modelle erfolgreich trainiert'})
        else:
            return jsonify({'success': False, 'message': 'Training fehlgeschlagen'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("📊 Datenbank: Supabase")
    print("🤖 ML-Modell: Aktiviert")
    print("🌐 URL: http://127.0.0.1:5000")
    print("👤 Login: admin@musterfirma.ch")
    print("🔑 Passwort: admin123")
    print("=" * 60)
    print("\n📡 API Endpoints:")
    print("  Ausschreibungen:")
    print("    GET    /api/ausschreibungen")
    print("    POST   /api/ausschreibungen")
    print("    GET    /api/ausschreibungen/<id>")
    print("    PUT    /api/ausschreibungen/<id>")
    print("    DELETE /api/ausschreibungen/<id>")
    print("\n  ML Predictions:")
    print("    POST   /api/predict")
    print("    POST   /api/calculate-relevanz")
    print("\n  Suche & Filter:")
    print("    GET    /api/search?q=software")
    print("    GET    /api/filter?status=neu")
    print("\n  User:")
    print("    POST   /api/user/save-ausschreibung")
    print("    GET    /api/user/saved-ausschreibungen")
    print("\n  Webhook:")
    print("    POST   /webhook/daily-update")
    print("=" * 60)

    # if __name__ == '__main__':
    #     app.run()
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
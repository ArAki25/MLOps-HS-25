"""
Simap.ch KI-Assistent - Hauptanwendung

Web-UI für die Anzeige von SIMAP-Ausschreibungen aus der Supabase-Datenbank.
"""
import os
import sys

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from dotenv import load_dotenv

# Füge Parent-Verzeichnis zum Path hinzu für Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.models import User, Ausschreibung, get_statistics

# Lade Umgebungsvariablen
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dein-geheimer-schluessel-hier')

# Beispiel-Benutzer (später durch echte Auth ersetzen)
users_db = {
    'admin@musterfirma.ch': User(
        email='admin@musterfirma.ch',
        password='admin123',
        firma='Musterfirma AG',
        name='Admin User'
    )
}


def load_ausschreibungen_from_db(limit: int = 50, cantons: list = None):
    """
    Lädt Ausschreibungen aus der Supabase-Datenbank.
    
    Args:
        limit: Maximale Anzahl zu ladender Einträge
        cantons: Optionale Liste von Kantonen zum Filtern
    
    Returns:
        Liste von Ausschreibung-Objekten
    """
    try:
        from database import load_with_filters
        
        df = load_with_filters(
            cantons=cantons,
            publication_types=['tender', 'award'],
            limit=limit
        )
        
        if df.empty:
            return []
        
        ausschreibungen = []
        for _, row in df.iterrows():
            # Einfacher Relevanz-Score basierend auf verfügbaren Daten
            relevanz = 50
            if row.get('estimated_amount'):
                relevanz += 20
            if row.get('description'):
                relevanz += 15
            if row.get('canton'):
                relevanz += 10
            relevanz = min(relevanz, 99)
            
            ausschreibung = Ausschreibung.from_db_row(row.to_dict(), relevanz=relevanz)
            ausschreibungen.append(ausschreibung)
        
        return ausschreibungen
        
    except Exception as e:
        print(f"Fehler beim Laden aus DB: {e}")
        # Fallback: Rückgabe leerer Liste
        return []


def get_fallback_data():
    """Liefert Demo-Daten wenn keine DB-Verbindung besteht."""
    return [
        Ausschreibung(
            id=1,
            titel='IT-Infrastruktur Modernisierung',
            unternehmen='Stadt Zürich',
            wert="250'000 CHF",
            deadline='15.12.2025',
            status='neu',
            relevanz=95,
            kategorie='IT-Services',
            beschreibung='Modernisierung der IT-Infrastruktur für städtische Verwaltung'
        ),
        Ausschreibung(
            id=2,
            titel='Software-Entwicklung CRM System',
            unternehmen='Kanton Bern',
            wert="180'000 CHF",
            deadline='20.12.2025',
            status='laufend',
            relevanz=88,
            kategorie='Software',
            beschreibung='Entwicklung eines massgeschneiderten CRM-Systems'
        ),
    ]


@app.route('/')
def index():
    """Hauptseite - Dashboard oder Login"""
    if not session.get('logged_in'):
        return render_template('login.html')

    # Versuche Daten aus DB zu laden
    ausschreibungen = load_ausschreibungen_from_db(limit=50)
    
    # Fallback auf Demo-Daten wenn DB leer/nicht erreichbar
    if not ausschreibungen:
        ausschreibungen = get_fallback_data()
    
    stats = get_statistics(ausschreibungen)
    return render_template('dashboard.html',
                           ausschreibungen=[a.to_dict() for a in ausschreibungen],
                           stats=stats,
                           user=session)


@app.route('/login', methods=['POST'])
def login():
    """Login-Verarbeitung"""
    email = request.form.get('email')
    password = request.form.get('password')

    if email in users_db and users_db[email].password == password:
        user = users_db[email]
        session['logged_in'] = True
        session['email'] = user.email
        session['firma'] = user.firma
        session['name'] = user.name
        return redirect(url_for('index'))

    return redirect(url_for('index'))


@app.route('/logout', methods=['POST'])
def logout():
    """Logout-Verarbeitung"""
    session.clear()
    return redirect(url_for('index'))


# API Endpoints
@app.route('/api/ausschreibungen', methods=['GET'])
def api_get_ausschreibungen():
    """API: Alle Ausschreibungen abrufen"""
    limit = request.args.get('limit', 50, type=int)
    canton = request.args.get('canton')
    
    cantons = [canton] if canton else None
    ausschreibungen = load_ausschreibungen_from_db(limit=limit, cantons=cantons)
    
    if not ausschreibungen:
        ausschreibungen = get_fallback_data()
    
    return jsonify([a.to_dict() for a in ausschreibungen])


@app.route('/api/ausschreibungen/<int:id>', methods=['GET'])
def api_get_ausschreibung(id):
    """API: Einzelne Ausschreibung abrufen"""
    ausschreibungen = load_ausschreibungen_from_db(limit=100)
    ausschreibung = next((a for a in ausschreibungen if a.id == id), None)
    
    if ausschreibung:
        return jsonify(ausschreibung.to_dict())
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/ki-relevanz', methods=['POST'])
def api_calculate_relevanz():
    """
    API: KI-Relevanz berechnen
    Hier kann das trainierte Modell aus ml/classifier.py eingebunden werden
    """
    data = request.get_json()
    # TODO: Hier KI-Modell aufrufen
    # from ml.classifier import predict_relevanz
    # relevanz = predict_relevanz(data)
    return jsonify({'relevanz': 85})


@app.route('/api/statistics', methods=['GET'])
def api_get_statistics():
    """API: Statistiken abrufen"""
    try:
        from database import get_statistics as db_get_statistics
        stats = db_get_statistics()
        return jsonify(stats)
    except Exception as e:
        # Fallback
        ausschreibungen = load_ausschreibungen_from_db(limit=100)
        if not ausschreibungen:
            ausschreibungen = get_fallback_data()
        stats = get_statistics(ausschreibungen)
        return jsonify(stats)


if __name__ == '__main__':
    print("=" * 60)
    print("Simap.ch KI-Assistent startet...")
    print("=" * 60)
    print(f"URL: http://127.0.0.1:5000")
    print(f"Login: admin@musterfirma.ch")
    print(f"Passwort: admin123")
    print("=" * 60)

    # Debug-Modus aus für PyCharm
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)


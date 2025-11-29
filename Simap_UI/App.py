"""
Simap.ch KI-Assistent - Hauptanwendung
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from models import User, Ausschreibung, get_statistics
import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dein-geheimer-schluessel-hier')

# Beispiel-Datenbank (später durch echte DB ersetzen)
users_db = {
    'admin@musterfirma.ch': User(
        email='admin@musterfirma.ch',
        password='admin123',
        firma='Musterfirma AG',
        name='Admin User'
    )
}

ausschreibungen_db = [
    Ausschreibung(
        id=1,
        titel='IT-Infrastruktur Modernisierung',
        unternehmen='Stadt Zuerich',
        wert='250.000 CHF',
        deadline='15.12.2025',
        status='neu',
        relevanz=95,
        kategorie='IT-Services',
        beschreibung='Modernisierung der IT-Infrastruktur fuer staedtische Verwaltung'
    ),
    Ausschreibung(
        id=2,
        titel='Software-Entwicklung CRM System',
        unternehmen='Kanton Bern',
        wert='180.000 CHF',
        deadline='20.12.2025',
        status='laufend',
        relevanz=88,
        kategorie='Software',
        beschreibung='Entwicklung eines massgeschneiderten CRM-Systems'
    ),
    Ausschreibung(
        id=3,
        titel='Cloud Migration Services',
        unternehmen='Bundesamt fuer Statistik',
        wert='420.000 CHF',
        deadline='10.01.2026',
        status='neu',
        relevanz=92,
        kategorie='Cloud Services',
        beschreibung='Migration bestehender Systeme in die Cloud-Infrastruktur'
    ),
    Ausschreibung(
        id=4,
        titel='Netzwerk-Security Audit',
        unternehmen='Stadt Basel',
        wert='95.000 CHF',
        deadline='05.11.2025',
        status='abgeschlossen',
        relevanz=85,
        kategorie='Security',
        beschreibung='Umfassende Sicherheitsueberpruefung der Netzwerkinfrastruktur'
    ),
    Ausschreibung(
        id=5,
        titel='Webportal Entwicklung',
        unternehmen='Kanton Aargau',
        wert='310.000 CHF',
        deadline='18.12.2025',
        status='laufend',
        relevanz=90,
        kategorie='Webentwicklung',
        beschreibung='Entwicklung eines buergerfreundlichen Online-Portals'
    )
]


@app.route('/')
def index():
    """Hauptseite - Dashboard oder Login"""
    if not session.get('logged_in'):
        return render_template('login.html')

    stats = get_statistics(ausschreibungen_db)
    return render_template('dashboard.html',
                           ausschreibungen=[a.to_dict() for a in ausschreibungen_db],
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
    return jsonify([a.to_dict() for a in ausschreibungen_db])


@app.route('/api/ausschreibungen/<int:id>', methods=['GET'])
def api_get_ausschreibung(id):
    """API: Einzelne Ausschreibung abrufen"""
    ausschreibung = next((a for a in ausschreibungen_db if a.id == id), None)
    if ausschreibung:
        return jsonify(ausschreibung.to_dict())
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/api/ki-relevanz', methods=['POST'])
def api_calculate_relevanz():
    """
    API: KI-Relevanz berechnen
    Hier kann dein Kollege das trainierte Modell einbinden
    """
    data = request.get_json()
    # TODO: Hier KI-Modell aufrufen
    # from ki_model import predict_relevanz
    # relevanz = predict_relevanz(data)
    return jsonify({'relevanz': 85})


@app.route('/api/statistics', methods=['GET'])
def api_get_statistics():
    """API: Statistiken abrufen"""
    stats = get_statistics(ausschreibungen_db)
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
# app.py - Hauptdatei für PyCharm
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'dein-geheimer-schluessel-hier'  # Ändere dies in Produktion!

# Beispiel-Datenbank (später durch echte Datenbank ersetzen)
AUSSCHREIBUNGEN_DB = [
    {
        'id': 1,
        'titel': 'IT-Infrastruktur Modernisierung',
        'unternehmen': 'Stadt Zürich',
        'wert': '250.000 CHF',
        'deadline': '15.12.2025',
        'status': 'neu',
        'relevanz': 95,
        'kategorie': 'IT-Services',
        'beschreibung': 'Modernisierung der IT-Infrastruktur für städtische Verwaltung'
    },
    {
        'id': 2,
        'titel': 'Software-Entwicklung CRM System',
        'unternehmen': 'Kanton Bern',
        'wert': '180.000 CHF',
        'deadline': '20.12.2025',
        'status': 'laufend',
        'relevanz': 88,
        'kategorie': 'Software',
        'beschreibung': 'Entwicklung eines massgeschneiderten CRM-Systems'
    },
    {
        'id': 3,
        'titel': 'Cloud Migration Services',
        'unternehmen': 'Bundesamt für Statistik',
        'wert': '420.000 CHF',
        'deadline': '10.01.2026',
        'status': 'neu',
        'relevanz': 92,
        'kategorie': 'Cloud Services',
        'beschreibung': 'Migration bestehender Systeme in die Cloud-Infrastruktur'
    },
    {
        'id': 4,
        'titel': 'Netzwerk-Security Audit',
        'unternehmen': 'Stadt Basel',
        'wert': '95.000 CHF',
        'deadline': '05.11.2025',
        'status': 'abgeschlossen',
        'relevanz': 85,
        'kategorie': 'Security',
        'beschreibung': 'Umfassende Sicherheitsüberprüfung der Netzwerkinfrastruktur'
    },
    {
        'id': 5,
        'titel': 'Webportal Entwicklung',
        'unternehmen': 'Kanton Aargau',
        'wert': '310.000 CHF',
        'deadline': '18.12.2025',
        'status': 'laufend',
        'relevanz': 90,
        'kategorie': 'Webentwicklung',
        'beschreibung': 'Entwicklung eines bürgerfreundlichen Online-Portals'
    }
]

# Benutzer-Datenbank (Beispiel)
USERS_DB = {
    'admin@musterfirma.ch': {
        'password': 'admin123',  # In Produktion: Gehashte Passwörter verwenden!
        'firma': 'Musterfirma AG',
        'name': 'Admin User'
    }
}

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simap.ch KI-Assistent</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f9fafb;
            color: #1f2937;
        }

        .header {
            background: white;
            border-bottom: 1px solid #e5e7eb;
            padding: 1rem 2rem;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1400px;
            margin: 0 auto;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .logo-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #2563eb, #60a5fa);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 20px;
        }

        .user-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .user-avatar {
            width: 40px;
            height: 40px;
            background: #2563eb;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }

        .container {
            display: flex;
            max-width: 1400px;
            margin: 0 auto;
        }

        .sidebar {
            width: 250px;
            background: white;
            border-right: 1px solid #e5e7eb;
            min-height: calc(100vh - 73px);
            padding: 1rem;
        }

        .nav-button {
            width: 100%;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            border: none;
            background: transparent;
            text-align: left;
            cursor: pointer;
            border-radius: 8px;
            font-size: 14px;
            color: #4b5563;
            transition: all 0.2s;
        }

        .nav-button:hover {
            background: #f3f4f6;
        }

        .nav-button.active {
            background: #dbeafe;
            color: #2563eb;
            font-weight: 600;
        }

        .main-content {
            flex: 1;
            padding: 2rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
        }

        .stat-card.blue {
            background: #eff6ff;
            border-color: #bfdbfe;
        }

        .stat-card.yellow {
            background: #fefce8;
            border-color: #fde047;
        }

        .stat-card.green {
            background: #f0fdf4;
            border-color: #bbf7d0;
        }

        .stat-card.purple {
            background: #faf5ff;
            border-color: #e9d5ff;
        }

        .stat-label {
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }

        .stat-value {
            font-size: 32px;
            font-weight: bold;
        }

        .search-bar {
            background: white;
            padding: 1rem;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            margin-bottom: 1.5rem;
        }

        .search-input {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 1rem;
        }

        .filter-buttons {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 0.5rem 1rem;
            border: 1px solid #d1d5db;
            background: #f3f4f6;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }

        .filter-btn:hover {
            background: #e5e7eb;
        }

        .filter-btn.active {
            background: #2563eb;
            color: white;
            border-color: #2563eb;
        }

        .ausschreibung-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            margin-bottom: 1rem;
            transition: box-shadow 0.2s;
        }

        .ausschreibung-card:hover {
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 1rem;
        }

        .card-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }

        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 0.5rem;
        }

        .status-neu {
            background: #dbeafe;
            color: #1e40af;
        }

        .status-laufend {
            background: #fef3c7;
            color: #92400e;
        }

        .status-abgeschlossen {
            background: #d1fae5;
            color: #065f46;
        }

        .relevanz-box {
            background: linear-gradient(135deg, #10b981, #3b82f6);
            color: white;
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            min-width: 100px;
        }

        .relevanz-label {
            font-size: 10px;
            text-transform: uppercase;
        }

        .relevanz-value {
            font-size: 28px;
            font-weight: bold;
        }

        .card-meta {
            display: flex;
            gap: 1.5rem;
            font-size: 14px;
            color: #6b7280;
            margin: 1rem 0;
        }

        .card-actions {
            display: flex;
            gap: 0.5rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
        }

        .btn {
            padding: 0.5rem 1.5rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }

        .btn-primary {
            background: #2563eb;
            color: white;
        }

        .btn-primary:hover {
            background: #1d4ed8;
        }

        .btn-secondary {
            background: #f3f4f6;
            color: #4b5563;
        }

        .btn-secondary:hover {
            background: #e5e7eb;
        }

        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        .login-box {
            background: white;
            padding: 3rem;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 400px;
        }

        .login-title {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 2rem;
            text-align: center;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 500;
            font-size: 14px;
        }

        .form-input {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 14px;
        }

        .form-input:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        .btn-login {
            width: 100%;
            padding: 0.75rem;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .btn-login:hover {
            background: #1d4ed8;
        }

        .logout-btn {
            padding: 0.5rem 1rem;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
        }

        .logout-btn:hover {
            background: #dc2626;
        }
    </style>
</head>
<body>
    {% if not session.get('logged_in') %}
    <!-- Login Page -->
    <div class="login-container">
        <div class="login-box">
            <h1 class="login-title">🔐 Simap.ch Login</h1>
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">E-Mail</label>
                    <input type="email" name="email" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Passwort</label>
                    <input type="password" name="password" class="form-input" required>
                </div>
                <button type="submit" class="btn-login">Anmelden</button>
            </form>
            <p style="margin-top: 1rem; text-align: center; font-size: 12px; color: #6b7280;">
                Demo: admin@musterfirma.ch / admin123
            </p>
        </div>
    </div>
    {% else %}
    <!-- Dashboard -->
    <div class="header">
        <div class="header-content">
            <div class="logo">
                <div class="logo-icon">📋</div>
                <div>
                    <h1 style="font-size: 18px; font-weight: bold;">Simap.ch KI-Assistent</h1>
                    <p style="font-size: 12px; color: #6b7280;">Intelligente Ausschreibungsberatung</p>
                </div>
            </div>
            <div class="user-info">
                <div style="text-align: right; margin-right: 1rem;">
                    <p style="font-size: 14px; font-weight: 500;">{{ session.get('firma', 'Unbekannt') }}</p>
                    <p style="font-size: 12px; color: #6b7280;">{{ session.get('email', '') }}</p>
                </div>
                <div class="user-avatar">M</div>
                <form method="POST" action="/logout" style="margin-left: 1rem;">
                    <button type="submit" class="logout-btn">Abmelden</button>
                </form>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="sidebar">
            <button class="nav-button active" onclick="showTab('dashboard')">📊 Dashboard</button>
            <button class="nav-button" onclick="showTab('projekte')">📁 Projekte</button>
            <button class="nav-button" onclick="showTab('analyse')">📈 Analyse</button>
            <button class="nav-button" onclick="showTab('einstellungen')">⚙️ Einstellungen</button>
        </div>

        <div class="main-content">
            <div id="dashboard-content">
                <!-- Stats -->
                <div class="stats-grid">
                    <div class="stat-card blue">
                        <p class="stat-label" style="color: #2563eb;">Neue Ausschreibungen</p>
                        <p class="stat-value" style="color: #1e3a8a;">{{ stats.neue }}</p>
                        <p style="font-size: 12px; color: #2563eb; margin-top: 0.5rem;">Heute aktualisiert</p>
                    </div>
                    <div class="stat-card yellow">
                        <p class="stat-label" style="color: #ca8a04;">Laufende Projekte</p>
                        <p class="stat-value" style="color: #78350f;">{{ stats.laufend }}</p>
                        <p style="font-size: 12px; color: #ca8a04; margin-top: 0.5rem;">In Bearbeitung</p>
                    </div>
                    <div class="stat-card green">
                        <p class="stat-label" style="color: #16a34a;">Abgeschlossen</p>
                        <p class="stat-value" style="color: #14532d;">{{ stats.abgeschlossen }}</p>
                        <p style="font-size: 12px; color: #16a34a; margin-top: 0.5rem;">Erfolgreich</p>
                    </div>
                    <div class="stat-card purple">
                        <p class="stat-label" style="color: #9333ea;">Gesamtvolumen</p>
                        <p class="stat-value" style="color: #581c87;">{{ stats.volumen }}</p>
                        <p style="font-size: 12px; color: #9333ea; margin-top: 0.5rem;">Dieses Jahr</p>
                    </div>
                </div>

                <!-- Search & Filter -->
                <div class="search-bar">
                    <input type="text" id="searchInput" class="search-input" placeholder="Ausschreibungen durchsuchen..." onkeyup="filterAusschreibungen()">
                    <div class="filter-buttons">
                        <button class="filter-btn active" onclick="setFilter('alle')">Alle</button>
                        <button class="filter-btn" onclick="setFilter('neu')">Neu</button>
                        <button class="filter-btn" onclick="setFilter('laufend')">Laufend</button>
                        <button class="filter-btn" onclick="setFilter('abgeschlossen')">Abgeschlossen</button>
                    </div>
                </div>

                <!-- Ausschreibungen -->
                <div id="ausschreibungen-container">
                    {% for item in ausschreibungen %}
                    <div class="ausschreibung-card" data-status="{{ item.status }}">
                        <div class="card-header">
                            <div style="flex: 1;">
                                <div>
                                    <span class="card-title">{{ item.titel }}</span>
                                    <span class="status-badge status-{{ item.status }}">{{ item.status|upper }}</span>
                                </div>
                                <p style="color: #6b7280; margin: 0.5rem 0;">{{ item.beschreibung }}</p>
                                <div class="card-meta">
                                    <span>🏢 {{ item.unternehmen }}</span>
                                    <span>📅 Deadline: {{ item.deadline }}</span>
                                    <span>💰 {{ item.wert }}</span>
                                </div>
                            </div>
                            <div style="margin-left: 2rem;">
                                <div class="relevanz-box">
                                    <div class="relevanz-label">KI-Relevanz</div>
                                    <div class="relevanz-value">{{ item.relevanz }}%</div>
                                </div>
                                <span style="display: block; margin-top: 0.5rem; padding: 0.25rem 0.75rem; background: #f3f4f6; border-radius: 20px; font-size: 12px; text-align: center;">
                                    {{ item.kategorie }}
                                </span>
                            </div>
                        </div>
                        <div class="card-actions">
                            <button class="btn btn-primary">Details ansehen</button>
                            <button class="btn btn-secondary">Merken</button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div id="projekte-content" style="display: none;">
                <div style="background: white; padding: 2rem; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <h2 style="font-size: 24px; font-weight: bold; margin-bottom: 1rem;">Meine Projekte</h2>
                    <p style="color: #6b7280;">Hier werden alle Ihre gespeicherten und verfolgten Ausschreibungen angezeigt.</p>
                </div>
            </div>

            <div id="analyse-content" style="display: none;">
                <div style="background: white; padding: 2rem; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <h2 style="font-size: 24px; font-weight: bold; margin-bottom: 1rem;">Analyse & Statistiken</h2>
                    <p style="color: #6b7280;">KI-gestützte Analysen und Erfolgsstatistiken Ihrer Ausschreibungen.</p>
                </div>
            </div>

            <div id="einstellungen-content" style="display: none;">
                <div style="background: white; padding: 2rem; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <h2 style="font-size: 24px; font-weight: bold; margin-bottom: 1rem;">Einstellungen</h2>
                    <div style="margin-top: 2rem;">
                        <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 0.5rem;">Unternehmensprofil</h3>
                        <p style="color: #6b7280; margin-bottom: 2rem;">Verwalten Sie Ihre Unternehmensdaten und Präferenzen.</p>

                        <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 0.5rem;">KI-Präferenzen</h3>
                        <p style="color: #6b7280; margin-bottom: 2rem;">Passen Sie die KI-Empfehlungen an Ihre Bedürfnisse an.</p>

                        <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 0.5rem;">Benachrichtigungen</h3>
                        <p style="color: #6b7280;">Legen Sie fest, wie Sie über neue Ausschreibungen informiert werden möchten.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentFilter = 'alle';

        function showTab(tabName) {
            document.querySelectorAll('.main-content > div').forEach(div => {
                div.style.display = 'none';
            });
            document.getElementById(tabName + '-content').style.display = 'block';

            document.querySelectorAll('.nav-button').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
        }

        function setFilter(status) {
            currentFilter = status;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            filterAusschreibungen();
        }

        function filterAusschreibungen() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.ausschreibung-card');

            cards.forEach(card => {
                const status = card.getAttribute('data-status');
                const text = card.textContent.toLowerCase();

                const matchesFilter = currentFilter === 'alle' || status === currentFilter;
                const matchesSearch = text.includes(searchTerm);

                card.style.display = (matchesFilter && matchesSearch) ? 'block' : 'none';
            });
        }
    </script>
    {% endif %}
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    if not session.get('logged_in'):
        return render_template_string(HTML_TEMPLATE)

    # Statistiken berechnen
    stats = {
        'neue': len([a for a in AUSSCHREIBUNGEN_DB if a['status'] == 'neu']),
        'laufend': len([a for a in AUSSCHREIBUNGEN_DB if a['status'] == 'laufend']),
        'abgeschlossen': len([a for a in AUSSCHREIBUNGEN_DB if a['status'] == 'abgeschlossen']),
        'volumen': '2.4 Mio CHF'
    }

    return render_template_string(HTML_TEMPLATE,
                                 ausschreibungen=AUSSCHREIBUNGEN_DB,
                                 stats=stats)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    if email in USERS_DB and USERS_DB[email]['password'] == password:
        session['logged_in'] = True
        session['email'] = email
        session['firma'] = USERS_DB[email]['firma']
        session['name'] = USERS_DB[email]['name']
        return redirect(url_for('index'))

    return redirect(url_for('index'))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))

# API Endpoints für Backend-Integration
@app.route('/api/ausschreibungen', methods=['GET'])
def get_ausschreibungen():
    """API Endpoint zum Abrufen aller Ausschreibungen"""
    return jsonify(AUSSCHREIBUNGEN_DB)

@app.route('/api/ausschreibungen/<int:id>', methods=['GET'])
def get_ausschreibung(id):
    """API Endpoint zum Abrufen einer einzelnen Ausschreibung"""
    ausschreibung = next((a for a in AUSSCHREIBUNGEN_DB if a['id'] == id), None)
    if ausschreibung:
        return jsonify(ausschreibung)
    return jsonify({'error': 'Nicht gefunden'}), 404

@app.route('/api/ki-relevanz', methods=['POST'])
def calculate_relevanz():
    """
    API Endpoint für KI-Modell Integration
    Hier kann dein Kollege das trainierte Modell einbinden
    """
    data = request.get_json()
    # Hier würde das KI-Modell aufgerufen werden
    # relevanz = model.predict(data)
    return jsonify({'relevanz': 85})  # Beispiel

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Simap.ch KI-Assistent startet...")
    print("=" * 50)
    print("📍 URL: http://127.0.0.1:5000")
    print("👤 Login: admin@musterfirma.ch")
    print("🔑 Passwort: admin123")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=5000)
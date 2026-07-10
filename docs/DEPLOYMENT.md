# Deployment & Betrieb

## Umgebungsvariablen

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `SUPABASE_URL` | ja | Supabase-Projekt-URL (kein Fallback mehr im Code) |
| `SUPABASE_ANON_KEY` | ja* | Anon-Key für die Web-App (*oder `SUPABASE_SERVICE_ROLE_KEY`) |
| `SUPABASE_SERVICE_ROLE_KEY` | nur ETL | Nur für Skripte/Embedding-Pipeline, nie im Frontend |
| `SECRET_KEY` | in Prod | Session-Signierung. Fehlt sie und `FLASK_ENV=production`, startet die App nicht. Im Dev wird ein ephemerer Key generiert. |
| `GROQ_API_KEY` | nein | Chatbot "Bob". Ohne Key antwortet Bob mit einer Fallback-Meldung. |
| `HOST` | nein | Bind-Adresse. Dev-Default `127.0.0.1`; Deployment setzt `0.0.0.0`. |
| `PORT` | nein | Default `5000`. |
| `LOG_LEVEL` | nein | `DEBUG`/`INFO`/`WARNING`… (Default `INFO`). |
| `ENABLE_TEST_DASHBOARD` | nein | `true` schaltet `/admin/test-runs` frei (nur lokal). |

Vorlage: [.env.example](../.env.example). `SECRET_KEY` generieren:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Entwicklung (Windows/macOS/Linux)

```bash
./dev                      # bootstrapt venv, kopiert .env.example, startet die App
# oder manuell:
pip install -r simap_ui/requirements.txt
python simap_ui/app.py
```

Tests & Linting:

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q
```

## Produktion

Werkzeug (`app.run`) ist nur für Dev. In Produktion gunicorn verwenden:

```bash
pip install -r simap_ui/requirements.txt
FLASK_ENV=production SECRET_KEY=<hex> HOST=0.0.0.0 \
    gunicorn --chdir simap_ui wsgi:app -w 2 -b 0.0.0.0:${PORT:-5000}
```

## Einmalige Migration: Passwort-Hashing

Admin-/Pro-User-Passwörter werden beim ersten erfolgreichen Login
automatisch von Klartext auf bcrypt migriert. Für Accounts, die sich
nicht mehr einloggen, einmalig lokal:

```bash
python scripts/hash_existing_passwords.py --dry-run   # erst prüfen
python scripts/hash_existing_passwords.py             # dann migrieren
```

(braucht `SUPABASE_SERVICE_ROLE_KEY` in der `.env`)

## Embedding-Pipeline

Läuft nächtlich via GitHub Action ([embedding_sync.yml](../.github/workflows/embedding_sync.yml)).
Manuell: `python -m embeddings.build_embeddings --source all`

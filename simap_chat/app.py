import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = "simapscout-new-structure-2026"

# ===== SUPABASE CONFIG =====
SUPABASE_URL = "https://rkfwuxocuojkjswigoss.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJrZnd1eG9jdW9qa2pzd2lnb3NzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3ODE1MDMsImV4cCI6MjA3ODM1NzUwM30.IzL3liuJVeoFQZfZ3rsPeT5ExKMklyoxMO_yGuGKEv0"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "projects_ui"


@app.route('/')
def landing():
    # Seite 1: Landing Page (GIF-Style)
    return render_template('landing.html')


@app.route('/publications')
def publications():
    # Seite 2: Suche (simap.ch 1:1 Style)
    search = request.args.get('search', '').strip()
    kanton = request.args.get('kanton', 'alle')

    query = supabase.table(TABLE).select("*")
    if search:
        query = query.ilike("title_de", f"%{search}%")
    if kanton != 'alle':
        query = query.eq("canton", kanton)

    result = query.order("publication_date", desc=True).limit(20).execute()
    auftraege = result.data if result.data else []

    return render_template('publications.html', auftraege=auftraege, search=search)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
#!/usr/bin/env python
"""Test-Skript für Datenbankverbindung."""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database.connection import get_db_connection

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL nicht gefunden in .env!")
    sys.exit(1)

# Entferne Anführungszeichen falls vorhanden
db_url = db_url.strip().strip('"').strip("'")

# Prüfe Format
if not db_url.startswith("postgresql://"):
    print("⚠ Warnung: DATABASE_URL sollte mit 'postgresql://' beginnen")
    print(f"  Aktueller Wert (maskiert): {db_url[:20]}...")

# Maskiere Passwort für Ausgabe
if "@" in db_url:
    parts = db_url.split("@")
    if ":" in parts[0]:
        user, _ = parts[0].rsplit(":", 1)
        print(f"✓ DATABASE_URL gefunden: {user}:***@{parts[1]}")
    else:
        print("✓ DATABASE_URL gefunden")
else:
    print("⚠ DATABASE_URL Format könnte falsch sein (kein @ gefunden)")
    print("  Format sollte sein: postgresql://postgres:PASSWORD@host:port/db")

# Setze bereinigte URL zurück
os.environ["DATABASE_URL"] = db_url

print("\nTeste Verbindung...")
try:
    conn = get_db_connection()
    print("✓ Verbindung erfolgreich!")
    conn.close()
except Exception as e:
    print(f"❌ Fehler: {e}")
    print("\nPrüfe:")
    print("1. Ist das Passwort korrekt?")
    print("2. Verwendest du das 'URI' Format (nicht Connection Pooling)?")
    print("3. Enthält DATABASE_URL Anführungszeichen? (sollten entfernt werden)")
    print("4. Format: postgresql://postgres:PASSWORD@host:port/db")
    sys.exit(1)
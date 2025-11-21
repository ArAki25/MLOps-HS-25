"""
Debug-Skript: Prüft ob Daten wirklich in die DB gehen
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Verbindung
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL nicht in .env!")
    exit(1)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# BEFORE
cur.execute("SELECT COUNT(*) FROM simap_projects")
before = cur.fetchone()[0]
print(f"BEFORE: {before:,} Einträge in DB")

# Prüfe letzte Einträge
cur.execute("""
    SELECT project_id, title, updated_at
    FROM simap_projects
    ORDER BY updated_at DESC
    LIMIT 5
""")
rows = cur.fetchall()
print(f"\nLetzte 5 Einträge (nach updated_at):")
for row in rows:
    print(f"  - {row[0]}: {row[1][:30]}... (updated: {row[2]})")

# Test: Einfach einen Insert
print("\n\nTEST: Füge einen Test-Eintrag hinzu...")
test_sql = """
INSERT INTO simap_projects (project_id, publication_id)
VALUES ('TEST_ID_12345', 'TEST_PUB_12345')
ON CONFLICT (project_id, publication_id) DO NOTHING
"""

try:
    cur.execute(test_sql)
    conn.commit()
    print("✓ Insert erfolgreich")
except Exception as e:
    print(f"❌ Fehler: {e}")
    conn.rollback()

# AFTER
cur.execute("SELECT COUNT(*) FROM simap_projects")
after = cur.fetchone()[0]
print(f"\nAFTER: {after:,} Einträge in DB")
print(f"Differenz: {after - before:,} neue Einträge")

# Prüfe ob Test-Eintrag da ist
cur.execute("SELECT * FROM simap_projects WHERE project_id = 'TEST_ID_12345'")
test_row = cur.fetchone()
if test_row:
    print("✓ Test-Eintrag erfolgreich eingefügt!")
else:
    print("❌ Test-Eintrag NICHT in DB!")

conn.close()

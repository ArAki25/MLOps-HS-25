# Supabase Storage Setup für ML-Modelle

## Problem
Der `sb_publishable_` Key hat nur Leserechte. Um Modelle zu speichern, brauchst du:
- **Öffentlicher Bucket**: `anon` key
- **Privater Bucket**: `service_role` key (empfohlen für Modelle)

## Schritt-für-Schritt Anleitung

### 1. Hole die richtigen API Keys

Gehe zu: https://rkfwuxocuojkjswigoss.supabase.com

Navigiere zu: **Settings → API**

Dort findest du:
- `anon` / `public` key - für öffentliche Buckets
- `service_role` key - für private Buckets (empfohlen!)

### 2. Aktualisiere die .env Datei

Öffne `.env` und füge hinzu:

```bash
# Für private Storage Buckets (empfohlen für Modelle)
SUPABASE_SERVICE_KEY=dein-service-role-key-hier

# ODER für öffentliche Buckets
SUPABASE_KEY=dein-anon-key-hier
```

**WICHTIG:** Der service_role Key ist sehr mächtig - NIE auf GitHub pushen!

### 3. Erstelle einen Storage Bucket

#### Option A: Über Supabase Dashboard (einfacher)

1. Gehe zu: **Storage → Create a new bucket**
2. Name: `models`
3. **Public bucket**: `OFF` (privat für Sicherheit)
4. **File size limit**: 50 MB
5. **Allowed MIME types**: `application/octet-stream`
6. Klicke **Create bucket**

#### Option B: Per API (automatisch)

Wenn du den service_role key hast, führe aus:

```bash
cd "c:\Users\Akishan\Documents\FHNW BAI\3. Semester\ML\MLOps-HS-25"
python -c "from ml.algorithm.supabase_storage_handler import SupabaseStorageHandler; h = SupabaseStorageHandler(); h.erstelle_bucket()"
```

### 4. Teste die Verbindung

```bash
cd "c:\Users\Akishan\Documents\FHNW BAI\3. Semester\ML\MLOps-HS-25"
python ml/algorithm/supabase_storage_handler.py
```

## Verwendung im Code

### Modell zu Supabase speichern:

```python
from ml.classifier import ProjektKlassifikator

klassifikator = ProjektKlassifikator()
# ... trainiere das Modell ...

# Speichere zu Supabase Storage
klassifikator.speichern(
    pfad="production/mein_modell_v1.pkl",
    zu_supabase=True,
    bucket_name="models"
)
```

### Modell von Supabase laden:

```python
from ml.classifier import ProjektKlassifikator

klassifikator = ProjektKlassifikator()

# Lade von Supabase Storage
klassifikator.laden(
    pfad="production/mein_modell_v1.pkl",
    von_supabase=True,
    bucket_name="models"
)

# Jetzt kannst du das Modell verwenden
df = klassifikator.lade_daten_von_supabase(tage_zurueck=7)
results = klassifikator.finde_interessante(df, min_prob=0.7)
```

## Sicherheits-Tipps

1. **Niemals** den `service_role` key auf GitHub pushen
2. Füge `.env` zur `.gitignore` hinzu (falls noch nicht)
3. Verwende private Buckets für ML-Modelle
4. Setze Bucket Policies für zusätzliche Sicherheit

## Alternative: Öffentlicher Bucket

Wenn du keinen service_role key verwenden möchtest:

1. Erstelle einen **öffentlichen** Bucket im Dashboard
2. Verwende den `anon` key (nicht publishable)
3. Beachte: Jeder mit dem Link kann das Modell herunterladen!

## Troubleshooting

### "row-level security policy" Fehler
→ Du brauchst den service_role key ODER einen öffentlichen Bucket

### "Unauthorized" Fehler
→ Prüfe ob du den richtigen API Key verwendest (nicht publishable)

### Bucket existiert nicht
→ Erstelle den Bucket zuerst über das Dashboard oder mit service_role key

## Nächste Schritte

Nach dem Setup kannst du:
- Modelle automatisch zu Supabase hochladen nach Training
- Modell-Versioning implementieren (v1, v2, etc.)
- Mehrere Modelle parallel testen (production, staging, experiments)
- CI/CD Pipeline für Modell-Deployment aufbauen

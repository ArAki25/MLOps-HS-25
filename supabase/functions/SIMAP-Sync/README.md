# SIMAP Sync Edge Function v3

Diese Edge Function synchronisiert SIMAP-Projekte kontinuierlich in die Supabase Datenbank.

## Setup

### 1. Supabase CLI installieren

**Option A: Über npm (empfohlen, wenn Node.js installiert ist)**
```bash
npm install -g supabase
```

**Option B: Über Scoop (Windows)**
```bash
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase
```

**Option C: Über Chocolatey (Windows)**
```bash
choco install supabase
```

**Option D: Manuell (Windows)**
1. Lade die neueste Version von: https://github.com/supabase/cli/releases
2. Entpacke die `.exe` Datei
3. Füge sie zum System-PATH hinzu

### 2. Mit Supabase verbinden

```bash
# Login bei Supabase
supabase login

# Projekt verbinden (deine Projekt-ID: rkfwuxocuojkjswigoss)
supabase link --project-ref rkfwuxocuojkjswigoss
```

### 3. Edge Function deployen

```bash
# Von Projekt-Root aus
cd supabase/functions/SIMAP-Sync
supabase functions deploy SIMAP-Sync

# Oder direkt:
supabase functions deploy SIMAP-Sync --project-ref rkfwuxocuojkjswigoss
```

## Verwendung

### Manuell auslösen:
```bash
curl -X POST https://rkfwuxocuojkjswigoss.supabase.co/functions/v1/SIMAP-Sync \
  -H "Authorization: Bearer YOUR_ANON_KEY"
```

### Parameter:
- `?days_back=7` - Nur Projekte der letzten 7 Tage
- `?full_sync=true` - Vollständiger Sync (30 Tage zurück)
- `?skip_details=true` - Überspringt Detail-API (nur für Testing)
- `?refetch_details=true` - Lädt Details auch für bestehende Projekte neu
- `?cantons=ZH,BE` - Nur bestimmte Kantone
- `?max_pages=5` - Limit für Testing

### Beispiel:
```bash
# Nur neue Projekte der letzten 3 Tage
curl -X POST "https://rkfwuxocuojkjswigoss.supabase.co/functions/v1/SIMAP-Sync?days_back=3" \
  -H "Authorization: Bearer YOUR_ANON_KEY"

# Vollständiger Sync mit Details
curl -X POST "https://rkfwuxocuojkjswigoss.supabase.co/functions/v1/SIMAP-Sync?full_sync=true" \
  -H "Authorization: Bearer YOUR_ANON_KEY"
```

## Workflow

Die Edge Function arbeitet in 3 Phasen:

1. **Search-API**: Holt alle Projekte im Zeitraum
2. **Detail-API**: Lädt Details für relevante Projekte (tender, award, etc.)
3. **Upsert**: Speichert alles in der Datenbank

## Statistiken

Die Response enthält detaillierte Statistiken:
```json
{
  "success": true,
  "message": "Sync: 15 new, 3 updated, 18 enriched",
  "stats": {
    "fetched": 18,
    "new_projects": 15,
    "updated_projects": 3,
    "details_fetched": 18,
    "details_skipped": 0,
    "details_errors": 0,
    "duration_seconds": 45.23
  }
}
```

## Winner-Daten

Die Funktion extrahiert Winner-Daten aus `decision.vendors[0]` für Awards:
- `winner_name` - Name des Gewinners
- `winner_city` - Stadt des Gewinners
- `winner_canton` - Kanton des Gewinners
- `award_amount` - Zuschlagspreis
- `award_currency` - Währung (CHF)
- `award_vat_type` - MwSt-Typ


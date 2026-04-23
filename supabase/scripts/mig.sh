#!/usr/bin/env bash
# =============================================================================
# mig.sh  –  Einfacher Migrations-Workflow fuer das SIMAP-Projekt
# =============================================================================
# Nutzung:
#   ./supabase/scripts/mig.sh new <name>     # Neue Migration anlegen
#   ./supabase/scripts/mig.sh push           # Neue Migrationen pushen
#   ./supabase/scripts/mig.sh sync           # Remote-Stand ins Repo ziehen
#   ./supabase/scripts/mig.sh status         # Vergleich lokal vs. remote
# =============================================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cmd="${1:-}"

case "$cmd" in

  new)
    # Erstellt eine neue Migration mit korrektem 14-stelligem Timestamp.
    # Supabase CLI uebernimmt die Benennung automatisch.
    name="${2:?Bitte einen Namen angeben: ./mig.sh new mein_name}"
    cd "$ROOT"
    supabase migration new "$name"
    echo ""
    echo "Naechste Schritte:"
    echo "  1. SQL eintragen in supabase/migrations/*_${name}.sql"
    echo "  2. ./supabase/scripts/mig.sh push"
    ;;

  push)
    cd "$ROOT"
    echo "→ supabase db push"
    supabase db push --yes
    ;;

  sync)
    # Zieht alle Remote-Migrationen ins Repo (fuer Migrationen die nur im
    # Dashboard oder via db query angelegt wurden).
    cd "$ROOT"
    echo "→ Remote-Migrationen synchronisieren..."
    python3 supabase/scripts/sync_migrations_from_remote.py
    echo ""
    echo "→ Status nach Sync:"
    supabase migration list
    ;;

  status)
    cd "$ROOT"
    supabase migration list
    ;;

  *)
    echo "Nutzung: $0 {new <name> | push | sync | status}"
    exit 1
    ;;
esac

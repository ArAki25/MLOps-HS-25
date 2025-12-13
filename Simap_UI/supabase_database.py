"""
supabase_database.py - Supabase Datenbank Integration
Angepasst für Tabellen: projects_website und users
"""

from supabase import create_client, Client
from typing import List, Dict, Optional
import os
from datetime import datetime

# Supabase Client (wird bei init_supabase() gesetzt)
supabase: Client = None


def init_supabase():
    """Initialisiere Supabase Client"""
    global supabase

    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url or not key:
        print(f"❌ SUPABASE_URL: {url}")
        print(f"❌ SUPABASE_KEY: {key[:20] if key else None}...")
        raise ValueError(
            "SUPABASE_URL und SUPABASE_KEY nicht gefunden!\n"
            "Setze sie in .env oder als Environment Variables."
        )

    try:
        supabase = create_client(url, key)
        print("✅ Supabase verbunden!")
        print(f"   URL: {url}")
        return supabase
    except Exception as e:
        print(f"❌ Supabase Verbindungsfehler: {e}")
        raise


# ============================================
# USERS
# ============================================

def get_user_by_email(email: str) -> Optional[Dict]:
    """Hole Benutzer per E-Mail"""
    if not supabase:
        print("❌ Supabase nicht initialisiert!")
        return None

    try:
        response = supabase.table('users').select('*').eq('email', email).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Fehler beim Laden des Users: {e}")
        return None


def create_user(email: str, password: str, firma: str, name: str) -> Dict:
    """Erstelle neuen Benutzer"""
    if not supabase:
        return None

    user_data = {
        'email': email,
        'password': password,
        'firma': firma,
        'name': name,
        'created_at': datetime.utcnow().isoformat()
    }

    try:
        response = supabase.table('users').insert(user_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Fehler beim Erstellen des Users: {e}")
        return None


# ============================================
# PROJECTS (Ausschreibungen) - Tabelle: projects_website
# ============================================

def get_all_ausschreibungen(limit: int = 100) -> List[Dict]:
    """Hole alle Projekte/Ausschreibungen aus projects_website"""
    if not supabase:
        print("❌ Supabase nicht initialisiert!")
        return []

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()

        # Transformiere Daten für Frontend
        projects = []
        for row in (response.data or []):
            projects.append(transform_project_for_frontend(row))

        return projects
    except Exception as e:
        print(f"❌ Fehler beim Laden der Projekte: {e}")
        return []


def transform_project_for_frontend(row: Dict) -> Dict:
    """Transformiert projects_website Zeile für das Frontend"""
    return {
        'id': row.get('id'),
        'titel': row.get('title_de') or row.get('title_fr') or 'Ohne Titel',
        'beschreibung': row.get('description_de') or row.get('description_fr') or '',
        'unternehmen': row.get('proc_office_name_de') or row.get('proc_office_name_fr') or '',
        'kategorie': row.get('project_type') or '',
        'order_type': row.get('order_type') or '',
        'process_type': row.get('process_type') or '',
        'canton': row.get('canton') or '',
        'city': row.get('city') or '',
        'country': row.get('country') or 'CH',
        'deadline': row.get('submission_deadline') or '',
        'publication_date': row.get('publication_date') or '',
        'wert': format_award_amount(row.get('award_amount'), row.get('award_currency')),
        'status': determine_status(row),
        'relevanz': 50,  # Default, wird durch ML berechnet
        'cpv_code': row.get('cpv_code_main') or '',
        'project_number': row.get('project_number') or '',
        'publication_number': row.get('publication_number') or '',
        'winner_name': row.get('winner_name') or '',
        'simap_project_id': row.get('simap_project_id') or '',
        # Original-Daten für Details
        'raw': row
    }


def format_award_amount(amount, currency) -> str:
    """Formatiert den Auftragswert"""
    if not amount:
        return ''
    try:
        amount_float = float(amount)
        currency = currency or 'CHF'
        if amount_float >= 1000000:
            return f"{amount_float / 1000000:.1f} Mio {currency}"
        elif amount_float >= 1000:
            return f"{amount_float / 1000:.0f}'000 {currency}"
        else:
            return f"{amount_float:.0f} {currency}"
    except:
        return str(amount)


def determine_status(row: Dict) -> str:
    """Bestimmt den Status basierend auf pub_type und anderen Feldern"""
    pub_type = row.get('pub_type', '')

    if pub_type == 'award':
        return 'abgeschlossen'
    elif pub_type == 'tender':
        return 'neu'
    elif pub_type == 'participant_selection':
        return 'laufend'
    elif pub_type == 'cancellation':
        return 'abgebrochen'
    else:
        return 'neu'


def get_ausschreibung_by_id(id: str) -> Optional[Dict]:
    """Hole ein spezifisches Projekt"""
    if not supabase:
        return None

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .eq('id', id) \
            .execute()

        if response.data and len(response.data) > 0:
            return transform_project_for_frontend(response.data[0])
        return None
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None


def get_ausschreibungen_by_status(status: str, limit: int = 100) -> List[Dict]:
    """Hole Projekte nach Status"""
    if not supabase:
        return []

    # Mapping von Frontend-Status zu pub_type
    status_mapping = {
        'neu': 'tender',
        'laufend': 'participant_selection',
        'abgeschlossen': 'award',
        'abgebrochen': 'cancellation'
    }

    pub_type = status_mapping.get(status, status)

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .eq('pub_type', pub_type) \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()

        return [transform_project_for_frontend(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return []


def create_ausschreibung(data: Dict) -> Dict:
    """Erstelle neues Projekt (falls benötigt)"""
    if not supabase:
        return None

    project_data = {
        'title_de': data.get('titel'),
        'description_de': data.get('beschreibung'),
        'proc_office_name_de': data.get('unternehmen'),
        'project_type': data.get('kategorie'),
        'order_type': data.get('order_type'),
        'canton': data.get('canton', 'ZH'),
        'country': data.get('country', 'CH'),
        'submission_deadline': data.get('deadline'),
        'pub_type': 'tender',
        'publication_date': datetime.utcnow().strftime('%Y-%m-%d'),
        'created_at': datetime.utcnow().isoformat()
    }

    try:
        response = supabase.table('projects_website').insert(project_data).execute()
        if response.data:
            return transform_project_for_frontend(response.data[0])
        return None
    except Exception as e:
        print(f"❌ Fehler beim Erstellen: {e}")
        return None


def update_ausschreibung(id: str, data: Dict) -> Dict:
    """Update ein Projekt"""
    if not supabase:
        return None

    update_data = {
        'updated_at': datetime.utcnow().isoformat()
    }

    # Mapping von Frontend-Feldern zu DB-Feldern
    field_mapping = {
        'titel': 'title_de',
        'beschreibung': 'description_de',
        'unternehmen': 'proc_office_name_de',
        'kategorie': 'project_type',
        'deadline': 'submission_deadline'
    }

    for frontend_field, db_field in field_mapping.items():
        if frontend_field in data:
            update_data[db_field] = data[frontend_field]

    try:
        response = supabase.table('projects_website') \
            .update(update_data) \
            .eq('id', id) \
            .execute()

        if response.data:
            return transform_project_for_frontend(response.data[0])
        return None
    except Exception as e:
        print(f"❌ Fehler beim Update: {e}")
        return None


def delete_ausschreibung(id: str) -> bool:
    """Lösche ein Projekt"""
    if not supabase:
        return False

    try:
        supabase.table('projects_website').delete().eq('id', id).execute()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Löschen: {e}")
        return False


# ============================================
# GESPEICHERTE PROJEKTE (für User)
# ============================================

def save_ausschreibung_for_user(user_id: int, ausschreibung_id: str, notizen: str = None) -> Dict:
    """Speichere Projekt für Benutzer"""
    if not supabase:
        return None

    data = {
        'user_id': user_id,
        'project_id': ausschreibung_id,
        'notizen': notizen,
        'created_at': datetime.utcnow().isoformat()
    }

    try:
        response = supabase.table('saved_projects').insert(data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None


def get_saved_ausschreibungen_for_user(user_id: int) -> List[Dict]:
    """Hole gespeicherte Projekte für Benutzer"""
    if not supabase:
        return []

    try:
        response = supabase.table('saved_projects') \
            .select('project_id') \
            .eq('user_id', user_id) \
            .execute()

        if not response.data:
            return []

        ids = [item['project_id'] for item in response.data]
        response = supabase.table('projects_website') \
            .select('*') \
            .in_('id', ids) \
            .execute()

        return [transform_project_for_frontend(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return []


# ============================================
# STATISTIKEN
# ============================================

def get_statistics() -> Dict:
    """Berechne Statistiken"""
    if not supabase:
        return {'neue': 0, 'laufend': 0, 'abgeschlossen': 0, 'total': 0}

    try:
        # Zähle nach pub_type
        neue = supabase.table('projects_website') \
            .select('id', count='exact') \
            .eq('pub_type', 'tender') \
            .execute()

        laufend = supabase.table('projects_website') \
            .select('id', count='exact') \
            .eq('pub_type', 'participant_selection') \
            .execute()

        abgeschlossen = supabase.table('projects_website') \
            .select('id', count='exact') \
            .eq('pub_type', 'award') \
            .execute()

        total = supabase.table('projects_website') \
            .select('id', count='exact') \
            .execute()

        return {
            'neue': neue.count if neue.count else 0,
            'laufend': laufend.count if laufend.count else 0,
            'abgeschlossen': abgeschlossen.count if abgeschlossen.count else 0,
            'total': total.count if total.count else 0
        }
    except Exception as e:
        print(f"❌ Statistik-Fehler: {e}")
        return {'neue': 0, 'laufend': 0, 'abgeschlossen': 0, 'total': 0}


# ============================================
# SUCHE
# ============================================

def search_ausschreibungen(query: str, limit: int = 50) -> List[Dict]:
    """Suche Projekte nach Text"""
    if not supabase:
        return []

    try:
        # Suche in title_de und description_de
        response = supabase.table('projects_website') \
            .select('*') \
            .or_(f'title_de.ilike.%{query}%,description_de.ilike.%{query}%,proc_office_name_de.ilike.%{query}%') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()

        return [transform_project_for_frontend(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Such-Fehler: {e}")
        return []


def filter_ausschreibungen(
        status: Optional[str] = None,
        kategorie: Optional[str] = None,
        canton: Optional[str] = None,
        order_type: Optional[str] = None,
        min_relevanz: Optional[int] = None,
        limit: int = 100
) -> List[Dict]:
    """Filtere Projekte"""
    if not supabase:
        return []

    try:
        query = supabase.table('projects_website').select('*')

        # Status-Filter (mapping zu pub_type)
        if status:
            status_mapping = {
                'neu': 'tender',
                'laufend': 'participant_selection',
                'abgeschlossen': 'award'
            }
            pub_type = status_mapping.get(status, status)
            query = query.eq('pub_type', pub_type)

        if kategorie:
            query = query.eq('project_type', kategorie)

        if canton:
            query = query.eq('canton', canton)

        if order_type:
            query = query.eq('order_type', order_type)

        response = query.order('publication_date', desc=True).limit(limit).execute()
        return [transform_project_for_frontend(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Filter-Fehler: {e}")
        return []


# ============================================
# BULK OPERATIONS
# ============================================

def bulk_create_ausschreibungen(projects: List[Dict]) -> int:
    """Erstelle mehrere Projekte auf einmal"""
    if not supabase:
        return 0

    try:
        # Transformiere zu DB-Format
        db_projects = []
        for p in projects:
            db_projects.append({
                'title_de': p.get('titel') or p.get('title_de'),
                'description_de': p.get('beschreibung') or p.get('description_de'),
                'proc_office_name_de': p.get('unternehmen') or p.get('proc_office_name_de'),
                'project_type': p.get('kategorie') or p.get('project_type'),
                'order_type': p.get('order_type'),
                'canton': p.get('canton', 'ZH'),
                'country': p.get('country', 'CH'),
                'pub_type': p.get('pub_type', 'tender'),
                'publication_date': p.get('publication_date', datetime.utcnow().strftime('%Y-%m-%d')),
                'created_at': datetime.utcnow().isoformat()
            })

        response = supabase.table('projects_website').insert(db_projects).execute()
        return len(response.data) if response.data else 0
    except Exception as e:
        print(f"❌ Bulk-Insert Fehler: {e}")
        return 0


# ============================================
# BEISPIELDATEN (optional)
# ============================================

def add_example_data():
    """Füge Beispieldaten hinzu (nur wenn leer)"""
    if not supabase:
        print("❌ Supabase nicht initialisiert - keine Beispieldaten")
        return

    # Prüfe ob schon User existiert
    user = get_user_by_email('admin@musterfirma.ch')
    if not user:
        user = create_user(
            email='admin@musterfirma.ch',
            password='admin123',
            firma='Musterfirma AG',
            name='Admin User'
        )
        if user:
            print(f"✅ Beispiel-User erstellt")
    else:
        print(f"ℹ️  User admin@musterfirma.ch existiert bereits")
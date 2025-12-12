"""
supabase_database.py - Supabase Datenbank Integration (KORRIGIERT)
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

    # Hole Werte dynamisch (wichtig wenn sie nach import gesetzt wurden)
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url or not key:
        print(f"❌ SUPABASE_URL: {url}")
        print(f"❌ SUPABASE_KEY: {key[:20] if key else None}...")
        raise ValueError(
            "SUPABASE_URL und SUPABASE_KEY nicht gefunden!\n"
            "Setze sie in .env oder direkt im Code."
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
# AUSSCHREIBUNGEN
# ============================================

def get_all_ausschreibungen(limit: int = 100) -> List[Dict]:
    """Hole alle Ausschreibungen"""
    if not supabase:
        print("❌ Supabase nicht initialisiert!")
        return []

    try:
        response = supabase.table('ausschreibungen') \
            .select('*') \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()

        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Fehler beim Laden der Ausschreibungen: {e}")
        return []


def get_ausschreibung_by_id(id: int) -> Optional[Dict]:
    """Hole eine spezifische Ausschreibung"""
    if not supabase:
        return None

    try:
        response = supabase.table('ausschreibungen') \
            .select('*') \
            .eq('id', id) \
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None


def get_ausschreibungen_by_status(status: str, limit: int = 100) -> List[Dict]:
    """Hole Ausschreibungen nach Status"""
    if not supabase:
        return []

    try:
        response = supabase.table('ausschreibungen') \
            .select('*') \
            .eq('status', status) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()

        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return []


def create_ausschreibung(data: Dict) -> Dict:
    """Erstelle neue Ausschreibung"""
    if not supabase:
        return None

    ausschreibung_data = {
        'titel': data.get('titel'),
        'unternehmen': data.get('unternehmen'),
        'wert': data.get('wert'),
        'deadline': data.get('deadline'),
        'status': data.get('status', 'neu'),
        'relevanz': data.get('relevanz', 0),
        'kategorie': data.get('kategorie'),
        'beschreibung': data.get('beschreibung'),
        'order_type': data.get('order_type'),
        'size_bucket': data.get('size_bucket'),
        'created_at': datetime.utcnow().isoformat()
    }

    try:
        response = supabase.table('ausschreibungen').insert(ausschreibung_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Fehler beim Erstellen: {e}")
        return None


def update_ausschreibung(id: int, data: Dict) -> Dict:
    """Update eine Ausschreibung"""
    if not supabase:
        return None

    data['updated_at'] = datetime.utcnow().isoformat()

    try:
        response = supabase.table('ausschreibungen') \
            .update(data) \
            .eq('id', id) \
            .execute()

        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Fehler beim Update: {e}")
        return None


def delete_ausschreibung(id: int) -> bool:
    """Lösche eine Ausschreibung"""
    if not supabase:
        return False

    try:
        supabase.table('ausschreibungen').delete().eq('id', id).execute()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Löschen: {e}")
        return False


# ============================================
# GESPEICHERTE AUSSCHREIBUNGEN
# ============================================

def save_ausschreibung_for_user(user_id: int, ausschreibung_id: int, notizen: str = None) -> Dict:
    """Speichere Ausschreibung für Benutzer"""
    if not supabase:
        return None

    data = {
        'user_id': user_id,
        'ausschreibung_id': ausschreibung_id,
        'notizen': notizen,
        'created_at': datetime.utcnow().isoformat()
    }

    try:
        response = supabase.table('gespeicherte_ausschreibungen').insert(data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None


def get_saved_ausschreibungen_for_user(user_id: int) -> List[Dict]:
    """Hole gespeicherte Ausschreibungen für Benutzer"""
    if not supabase:
        return []

    try:
        response = supabase.table('gespeicherte_ausschreibungen') \
            .select('ausschreibung_id') \
            .eq('user_id', user_id) \
            .execute()

        if not response.data:
            return []

        ids = [item['ausschreibung_id'] for item in response.data]
        response = supabase.table('ausschreibungen') \
            .select('*') \
            .in_('id', ids) \
            .execute()

        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return []


# ============================================
# STATISTIKEN
# ============================================

def get_statistics() -> Dict:
    """Berechne Statistiken"""
    if not supabase:
        return {'neue': 0, 'laufend': 0, 'abgeschlossen': 0, 'volumen': '0 CHF'}

    try:
        neue = supabase.table('ausschreibungen') \
            .select('id', count='exact') \
            .eq('status', 'neu') \
            .execute()

        laufend = supabase.table('ausschreibungen') \
            .select('id', count='exact') \
            .eq('status', 'laufend') \
            .execute()

        abgeschlossen = supabase.table('ausschreibungen') \
            .select('id', count='exact') \
            .eq('status', 'abgeschlossen') \
            .execute()

        return {
            'neue': neue.count if neue.count else 0,
            'laufend': laufend.count if laufend.count else 0,
            'abgeschlossen': abgeschlossen.count if abgeschlossen.count else 0,
            'volumen': '2.4 Mio CHF'
        }
    except Exception as e:
        print(f"❌ Statistik-Fehler: {e}")
        return {'neue': 0, 'laufend': 0, 'abgeschlossen': 0, 'volumen': '0 CHF'}


# ============================================
# BULK OPERATIONS
# ============================================

def bulk_create_ausschreibungen(ausschreibungen: List[Dict]) -> int:
    """Erstelle mehrere Ausschreibungen auf einmal"""
    if not supabase:
        return 0

    try:
        for data in ausschreibungen:
            data['created_at'] = datetime.utcnow().isoformat()

        response = supabase.table('ausschreibungen').insert(ausschreibungen).execute()
        return len(response.data) if response.data else 0
    except Exception as e:
        print(f"❌ Bulk-Insert Fehler: {e}")
        return 0


# ============================================
# SUCHE
# ============================================

def search_ausschreibungen(query: str, limit: int = 50) -> List[Dict]:
    """Suche Ausschreibungen nach Text"""
    if not supabase:
        return []

    try:
        response = supabase.table('ausschreibungen') \
            .select('*') \
            .or_(f'titel.ilike.%{query}%,beschreibung.ilike.%{query}%') \
            .limit(limit) \
            .execute()

        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Such-Fehler: {e}")
        return []


def filter_ausschreibungen(
        status: Optional[str] = None,
        kategorie: Optional[str] = None,
        min_relevanz: Optional[int] = None,
        limit: int = 100
) -> List[Dict]:
    """Filtere Ausschreibungen"""
    if not supabase:
        return []

    try:
        query = supabase.table('ausschreibungen').select('*')

        if status:
            query = query.eq('status', status)
        if kategorie:
            query = query.eq('kategorie', kategorie)
        if min_relevanz is not None:
            query = query.gte('relevanz', min_relevanz)

        response = query.order('created_at', desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Filter-Fehler: {e}")
        return []


# ============================================
# BEISPIELDATEN
# ============================================

def add_example_data():
    """Füge Beispieldaten hinzu"""
    if not supabase:
        print("❌ Supabase nicht initialisiert - keine Beispieldaten")
        return

    # User
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

    # Ausschreibungen
    beispiele = [
        {
            'titel': 'IT-Infrastruktur Modernisierung',
            'unternehmen': 'Stadt Zuerich',
            'wert': '250.000 CHF',
            'deadline': '15.12.2025',
            'status': 'neu',
            'relevanz': 95,
            'kategorie': 'IT-Services',
            'beschreibung': 'Modernisierung der IT-Infrastruktur',
            'order_type': 'service',
            'size_bucket': 'mittel'
        },
        {
            'titel': 'Software-Entwicklung CRM',
            'unternehmen': 'Kanton Bern',
            'wert': '180.000 CHF',
            'deadline': '20.12.2025',
            'status': 'laufend',
            'relevanz': 88,
            'kategorie': 'Software',
            'beschreibung': 'CRM-System Entwicklung',
            'order_type': 'service',
            'size_bucket': 'mittel'
        }
    ]

    count = bulk_create_ausschreibungen(beispiele)
    if count > 0:
        print(f"✅ {count} Beispiel-Ausschreibungen erstellt")
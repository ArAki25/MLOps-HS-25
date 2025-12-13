"""
supabase_client.py - Supabase Datenbank Client
Einfache Version: Liest Projekte aus projects_website
"""

from supabase import create_client, Client
from typing import List, Dict, Optional
import os
from datetime import datetime, timezone

supabase: Client = None


def init_supabase():
    """Initialisiere Supabase Client"""
    global supabase

    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url or not key:
        raise ValueError("SUPABASE_URL und SUPABASE_KEY nicht gefunden!")

    supabase = create_client(url, key)
    print("✅ Supabase verbunden!")
    return supabase


def get_all_projects(limit: int = 50) -> List[Dict]:
    """Hole alle Projekte, neueste zuerst"""
    if not supabase:
        return []

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()

        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return []


def get_project_by_id(project_id: str) -> Optional[Dict]:
    """Hole einzelnes Projekt nach ID"""
    if not supabase:
        return None

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .eq('id', project_id) \
            .execute()

        if response.data and len(response.data) > 0:
            return transform_project(response.data[0], include_details=True)
        return None
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None


def search_projects(query: str, limit: int = 50) -> List[Dict]:
    """Suche in Titel, Beschreibung und Projekt-Nummer"""
    if not supabase or not query:
        return []

    try:
        response = supabase.table('projects_website') \
            .select('*') \
            .or_(
            f'title_de.ilike.%{query}%,description_de.ilike.%{query}%,project_number.ilike.%{query}%,proc_office_name_de.ilike.%{query}%') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()

        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Such-Fehler: {e}")
        return []


def filter_projects(
        canton: Optional[str] = None,
        process_type: Optional[str] = None,
        order_type: Optional[str] = None,
        limit: int = 50
) -> List[Dict]:
    """Filtere Projekte nach Kriterien"""
    if not supabase:
        return []

    try:
        query = supabase.table('projects_website').select('*')

        if canton:
            query = query.eq('canton', canton)
        if process_type:
            query = query.eq('process_type', process_type)
        if order_type:
            query = query.eq('order_type', order_type)

        response = query.order('publication_date', desc=True).limit(limit).execute()
        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ Filter-Fehler: {e}")
        return []


def get_cantons() -> List[Dict]:
    """Hole Liste aller Kantone mit Anzahl Projekten"""
    if not supabase:
        return []

    try:
        response = supabase.table('projects_website') \
            .select('canton') \
            .execute()

        # Zähle Kantone
        canton_counts = {}
        for row in (response.data or []):
            canton = row.get('canton')
            if canton:
                canton_counts[canton] = canton_counts.get(canton, 0) + 1

        # Sortiere nach Anzahl
        cantons = [{'code': k, 'count': v} for k, v in canton_counts.items()]
        cantons.sort(key=lambda x: x['count'], reverse=True)

        return cantons
    except Exception as e:
        print(f"❌ Canton-Fehler: {e}")
        return []


def get_statistics() -> Dict:
    """Hole Statistiken"""
    if not supabase:
        return {'total': 0, 'today': 0, 'this_week': 0}

    try:
        # Total
        total = supabase.table('projects_website') \
            .select('id', count='exact') \
            .execute()

        # Heute (basierend auf publication_date)
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        today_count = supabase.table('projects_website') \
            .select('id', count='exact') \
            .eq('publication_date', today) \
            .execute()

        return {
            'total': total.count if total.count else 0,
            'today': today_count.count if today_count.count else 0
        }
    except Exception as e:
        print(f"❌ Statistik-Fehler: {e}")
        return {'total': 0, 'today': 0}


def transform_project(row: Dict, include_details: bool = False) -> Dict:
    """Transformiert DB-Zeile für Frontend"""

    # Berechne relative Zeit
    pub_date = row.get('publication_date')
    time_ago = calculate_time_ago(pub_date)

    # Basis-Daten
    project = {
        'id': row.get('id'),
        'title': row.get('title_de') or row.get('title_fr') or 'Ohne Titel',
        'description': clean_html(row.get('description_de') or row.get('description_fr') or ''),
        'organization': row.get('proc_office_name_de') or row.get('proc_office_name_fr') or '',
        'canton': row.get('canton') or '',
        'city': row.get('city') or '',
        'country': row.get('country') or 'CH',
        'process_type': row.get('process_type') or '',
        'order_type': row.get('order_type') or '',
        'pub_type': row.get('pub_type') or '',
        'publication_date': pub_date,
        'time_ago': time_ago,
        'deadline': row.get('submission_deadline'),
        'project_number': row.get('project_number') or '',
        'publication_number': row.get('publication_number') or '',
        'simap_id': row.get('simap_project_id') or '',
        'simap_url': generate_simap_url(row)
    }

    # Details nur wenn angefordert
    if include_details:
        project['cpv_code'] = row.get('cpv_code_main') or ''
        project['award_amount'] = row.get('award_amount')
        project['award_currency'] = row.get('award_currency') or 'CHF'
        project['winner_name'] = row.get('winner_name') or ''
        project['winner_city'] = row.get('winner_city') or ''
        project['proc_office_email'] = row.get('proc_office_email') or ''
        project['proc_office_phone'] = row.get('proc_office_phone') or ''
        project['proc_office_street'] = row.get('proc_office_street') or ''
        project['proc_office_postal_code'] = row.get('proc_office_postal_code') or ''

    return project


def clean_html(text: str) -> str:
    """Entfernt HTML Tags für Preview"""
    if not text:
        return ''
    import re
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace('&nbsp;', ' ').strip()
    # Kürze für Preview
    if len(clean) > 300:
        clean = clean[:300] + '...'
    return clean


def calculate_time_ago(date_str: str) -> str:
    """Berechnet 'vor X Minuten/Stunden/Tagen'"""
    if not date_str:
        return ''

    try:
        pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)

        # Falls pub_date kein Timezone hat
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        diff = now - pub_date

        minutes = int(diff.total_seconds() / 60)
        hours = int(diff.total_seconds() / 3600)
        days = diff.days

        if minutes < 1:
            return 'Gerade eben'
        elif minutes < 60:
            return f'vor {minutes} Min.'
        elif hours < 24:
            return f'vor {hours} Std.'
        elif days == 1:
            return 'Gestern'
        elif days < 7:
            return f'vor {days} Tagen'
        elif days < 30:
            weeks = days // 7
            return f'vor {weeks} Woche{"n" if weeks > 1 else ""}'
        else:
            return pub_date.strftime('%d.%m.%Y')
    except:
        return ''


def generate_simap_url(row: Dict) -> str:
    """Generiert Link zu simap.ch (Format: /de/project-detail/{simap_project_id})"""

    # Prüfe ob simap_link schon in DB gespeichert ist
    if row.get('simap_link'):
        return row.get('simap_link')

    # URL-Format: https://www.simap.ch/de/project-detail/{simap_project_id}
    project_id = row.get('simap_project_id')

    if project_id:
        return f"https://www.simap.ch/de/project-detail/{project_id}"
    else:
        return "https://www.simap.ch"
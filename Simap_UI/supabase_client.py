"""
supabase_client.py - Supabase Datenbank Client
Mit Content Management für Admin Panel
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


# ============================================
# PROJECTS (Tenders)
# ============================================

def get_all_projects(limit: int = 50) -> List[Dict]:
    """Hole alle Projekte, neueste zuerst"""
    if not supabase:
        return []

    try:
        response = supabase.table('projects_ui') \
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
        response = supabase.table('projects_ui') \
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
        response = supabase.table('projects_ui') \
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
        query = supabase.table('projects_ui').select('*')

        if canton:
            # Case-insensitive canton filter
            query = query.ilike('canton', canton)
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
        # Hole alle Kantone in Batches um Limit zu umgehen
        all_cantons = []
        batch_size = 1000
        offset = 0

        while True:
            response = supabase.table('projects_ui') \
                .select('canton') \
                .range(offset, offset + batch_size - 1) \
                .execute()

            if not response.data or len(response.data) == 0:
                break

            all_cantons.extend(response.data)

            if len(response.data) < batch_size:
                break

            offset += batch_size

        # Zähle Kantone
        canton_counts = {}
        for row in all_cantons:
            canton = row.get('canton')
            if canton:
                canton_counts[canton] = canton_counts.get(canton, 0) + 1

        cantons = [{'code': k, 'count': v} for k, v in canton_counts.items()]
        cantons.sort(key=lambda x: x['count'], reverse=True)

        print(f"✅ {len(cantons)} Kantone geladen, {len(all_cantons)} Projekte gezählt")
        return cantons
    except Exception as e:
        print(f"❌ Canton-Fehler: {e}")
        return []


def get_statistics() -> Dict:
    """Hole Statistiken"""
    if not supabase:
        return {'total': 0, 'today': 0}

    try:
        total = supabase.table('projects_ui') \
            .select('id', count='exact') \
            .execute()

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        today_count = supabase.table('projects_ui') \
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

    pub_date = row.get('publication_date')
    time_ago = calculate_time_ago(pub_date)

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

    if include_details:
        project['cpv_code'] = row.get('cpv_code_main') or ''
        project['award_amount'] = row.get('award_amount')
        project['award_currency'] = row.get('award_currency') or 'CHF'
        project['winner_name'] = row.get('winner_name') or ''
        project['winner_city'] = row.get('winner_city') or ''
        project['proc_office_email'] = row.get('proc_office_email') or ''
        project['proc_office_phone'] = row.get('proc_office_phone') or ''

    return project


def generate_simap_url(row: Dict) -> str:
    """Generiert Link zu simap.ch"""

    if row.get('simap_link'):
        return row.get('simap_link')

    project_id = row.get('simap_project_id')

    if project_id:
        return f"https://www.simap.ch/de/project-detail/{project_id}"
    else:
        return "https://www.simap.ch"


def clean_html(text: str) -> str:
    """Entfernt HTML Tags"""
    if not text:
        return ''
    import re
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace('&nbsp;', ' ').strip()
    return clean


def calculate_time_ago(date_str: str) -> str:
    """Berechnet 'vor X Minuten/Stunden/Tagen'"""
    if not date_str:
        return ''

    try:
        pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)

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


# ============================================
# CONTENT MANAGEMENT (für Admin Panel)
# ============================================

def get_content(page: str) -> Dict:
    """Hole Content für eine Seite"""
    if not supabase:
        return {}

    try:
        response = supabase.table('site_content') \
            .select('*') \
            .eq('page', page) \
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0].get('content', {})
        return {}
    except Exception as e:
        print(f"❌ Content-Fehler: {e}")
        return {}


def update_content(page: str, content: Dict) -> bool:
    """Update Content für eine Seite"""
    if not supabase:
        return False

    try:
        existing = supabase.table('site_content') \
            .select('id') \
            .eq('page', page) \
            .execute()

        if existing.data and len(existing.data) > 0:
            supabase.table('site_content') \
                .update({'content': content, 'updated_at': datetime.utcnow().isoformat()}) \
                .eq('page', page) \
                .execute()
        else:
            supabase.table('site_content') \
                .insert({'page': page, 'content': content}) \
                .execute()

        return True
    except Exception as e:
        print(f"❌ Content-Update-Fehler: {e}")
        return False


# ============================================
# TEAM MEMBERS (für Über uns Seite)
# ============================================

def get_team_members() -> List[Dict]:
    """Hole alle Team-Mitglieder"""
    if not supabase:
        return []

    try:
        response = supabase.table('team_members') \
            .select('*') \
            .order('display_order', desc=False) \
            .execute()

        return response.data or []
    except Exception as e:
        print(f"❌ Team-Fehler: {e}")
        return []


def add_team_member(data: Dict) -> Optional[Dict]:
    """Füge Team-Mitglied hinzu"""
    if not supabase:
        return None

    try:
        response = supabase.table('team_members') \
            .insert({
            'name': data.get('name'),
            'role': data.get('role'),
            'bio': data.get('bio'),
            'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0)
        }) \
            .execute()

        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Team-Add-Fehler: {e}")
        return None


def update_team_member(member_id: str, data: Dict) -> bool:
    """Update Team-Mitglied"""
    if not supabase:
        return False

    try:
        supabase.table('team_members') \
            .update({
            'name': data.get('name'),
            'role': data.get('role'),
            'bio': data.get('bio'),
            'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0),
            'updated_at': datetime.utcnow().isoformat()
        }) \
            .eq('id', member_id) \
            .execute()
        return True
    except Exception as e:
        print(f"❌ Team-Update-Fehler: {e}")
        return False


def delete_team_member(member_id: str) -> bool:
    """Lösche Team-Mitglied"""
    if not supabase:
        return False

    try:
        supabase.table('team_members') \
            .delete() \
            .eq('id', member_id) \
            .execute()
        return True
    except Exception as e:
        print(f"❌ Team-Delete-Fehler: {e}")
        return False


# ============================================
# ADMIN AUTHENTICATION
# ============================================

def get_admin_by_email(email: str) -> Optional[Dict]:
    """Hole Admin per E-Mail"""
    if not supabase:
        return None

    try:
        response = supabase.table('admins') \
            .select('*') \
            .eq('email', email) \
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Admin-Fehler: {e}")
        return None


# ============================================
# PRO USER AUTHENTICATION
# ============================================

def get_pro_user(username: str, password: str) -> Optional[Dict]:
    """Hole Pro-User per Username/Email und Passwort"""
    if not supabase:
        return None

    try:
        response = supabase.table('pro_users') \
            .select('*') \
            .or_(f'email.eq.{username},company_name.eq.{username}') \
            .eq('password', password) \
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Pro-User-Fehler: {e}")
        return None


# ============================================
# ML / RECOMMENDED PROJECTS
# ============================================

def get_recommended_projects(table_name: str, limit: int = 50) -> List[Dict]:
    """Hole empfohlene Projekte aus firmenspezifischer ML-Tabelle"""
    if not supabase or not table_name:
        return []

    try:
        response = supabase.table(table_name) \
            .select('*') \
            .order('probability', desc=True) \
            .limit(limit) \
            .execute()

        # Transformiere die Daten für das Frontend
        projects = []
        for row in (response.data or []):
            # Berechne time_ago
            time_ago = calculate_time_ago(row.get('publication_date'))

            projects.append({
                'id': row.get('id'),
                'project_id': row.get('project_id'),
                'title': row.get('title') or 'Ohne Titel',
                'description': clean_html(row.get('description') or ''),
                'canton': row.get('canton') or '',
                'probability': row.get('probability') or 0,
                'prediction': row.get('prediction'),
                'publication_date': row.get('publication_date'),
                'time_ago': time_ago,
                'cpv_code': row.get('cpv_code'),
                'simap_url': f"https://www.simap.ch/de/project-detail/{row.get('project_id')}" if row.get(
                    'project_id') else "https://www.simap.ch"
            })

        return projects
    except Exception as e:
        print(f"❌ ML-Projekte-Fehler: {e}")
        return []
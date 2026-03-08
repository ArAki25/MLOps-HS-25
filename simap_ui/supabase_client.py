"""
supabase_client.py - Supabase Datenbank Client
SAJF Strategies - Bulletproof Version
"""

from supabase import create_client, Client
from typing import List, Dict, Optional
import os
from datetime import datetime, timezone

# ============================================
# GLOBAL CLIENT
# ============================================
supabase: Client = None


def init_supabase():
    """Initialisiere Supabase Client"""
    global supabase

    # .env hat Priorität, sonst Hardcoded Fallback
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    # Fallback falls .env nicht geladen wird
    if not url:
        url = 'https://rkfwuxocuojkjswigoss.supabase.co'
    if not key:
        key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJrZnd1eG9jdW9qa2pzd2lnb3NzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mjc4MTUwMywiZXhwIjoyMDc4MzU3NTAzfQ.j-n-tnWaAp9WxoBxWPsYDcU1E4lcKgCYu3ukWzdtF6k'

    print(f"🔗 URL: {url[:50]}...")
    print(f"🔑 Key: {key[:20]}...{key[-10:]}")

    supabase = create_client(url, key)
    print(f"✅ Supabase verbunden! Client: {type(supabase).__name__}")
    return supabase


def get_client():
    """Hole Supabase Client (mit Auto-Init)"""
    global supabase
    if supabase is None:
        init_supabase()
    return supabase


# ============================================
# PROJECTS (Tenders)
# ============================================

def get_all_projects(limit: int = 50) -> List[Dict]:
    """Hole alle Projekte, neueste zuerst"""
    sb = get_client()
    if not sb:
        return []
    try:
        response = sb.table('projects_ui') \
            .select('*') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()
        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ get_all_projects Fehler: {e}")
        return []


def get_project_by_id(project_id: str) -> Optional[Dict]:
    sb = get_client()
    if not sb:
        return None
    try:
        response = sb.table('projects_ui').select('*').eq('id', project_id).execute()
        if response.data and len(response.data) > 0:
            return transform_project(response.data[0], include_details=True)
        return None
    except Exception as e:
        print(f"❌ get_project_by_id Fehler: {e}")
        return None


def search_projects(query: str, limit: int = 50) -> List[Dict]:
    sb = get_client()
    if not sb or not query:
        return []
    try:
        response = sb.table('projects_ui') \
            .select('*') \
            .or_(f'title_de.ilike.%{query}%,description_de.ilike.%{query}%,project_number.ilike.%{query}%,proc_office_name_de.ilike.%{query}%') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()
        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ search_projects Fehler: {e}")
        return []


def filter_projects(canton=None, process_type=None, order_type=None, limit=50) -> List[Dict]:
    sb = get_client()
    if not sb:
        return []
    try:
        query = sb.table('projects_ui').select('*')
        if canton:
            query = query.ilike('canton', canton)
        if process_type:
            query = query.eq('process_type', process_type)
        if order_type:
            query = query.eq('order_type', order_type)
        response = query.order('publication_date', desc=True).limit(limit).execute()
        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ filter_projects Fehler: {e}")
        return []


def get_cantons() -> List[str]:
    sb = get_client()
    if not sb:
        return []
    try:
        all_cantons = []
        batch_size = 1000
        offset = 0
        while True:
            response = sb.table('projects_ui').select('canton').range(offset, offset + batch_size - 1).execute()
            if not response.data:
                break
            all_cantons.extend(response.data)
            if len(response.data) < batch_size:
                break
            offset += batch_size
        cantons = sorted(set(row.get('canton') for row in all_cantons if row.get('canton')))
        print(f"✅ {len(cantons)} Kantone geladen")
        return cantons
    except Exception as e:
        print(f"❌ get_cantons Fehler: {e}")
        return []


def get_statistics() -> Dict:
    sb = get_client()
    if not sb:
        return {'total': 0, 'today': 0}
    try:
        total = sb.table('projects_ui').select('id', count='exact').execute()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        today_count = sb.table('projects_ui').select('id', count='exact').eq('publication_date', today).execute()
        return {
            'total': total.count if total.count else 0,
            'today': today_count.count if today_count.count else 0
        }
    except Exception as e:
        print(f"❌ get_statistics Fehler: {e}")
        return {'total': 0, 'today': 0}


# ============================================
# TRANSFORM
# ============================================

def transform_project(row: Dict, include_details: bool = False) -> Dict:
    pub_date = row.get('publication_date')
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
        'time_ago': calculate_time_ago(pub_date),
        'deadline': row.get('submission_deadline'),
        'project_number': row.get('project_number') or '',
        'publication_number': row.get('publication_number') or '',
        'simap_id': row.get('simap_project_id') or '',
        'simap_url': generate_simap_url(row)
    }
    if include_details:
        project.update({
            'cpv_code': row.get('cpv_code_main') or '',
            'award_amount': row.get('award_amount'),
            'award_currency': row.get('award_currency') or 'CHF',
            'winner_name': row.get('winner_name') or '',
            'winner_city': row.get('winner_city') or '',
            'proc_office_email': row.get('proc_office_email') or '',
            'proc_office_phone': row.get('proc_office_phone') or '',
        })
    return project


def generate_simap_url(row: Dict) -> str:
    if row.get('simap_link'):
        return row['simap_link']
    pid = row.get('simap_project_id')
    return f"https://www.simap.ch/de/project-detail/{pid}" if pid else "https://www.simap.ch"


def clean_html(text: str) -> str:
    if not text:
        return ''
    import re
    return re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').strip()


def calculate_time_ago(date_str: str) -> str:
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
        if minutes < 1: return 'Gerade eben'
        if minutes < 60: return f'vor {minutes} Min.'
        if hours < 24: return f'vor {hours} Std.'
        if days == 1: return 'Gestern'
        if days < 7: return f'vor {days} Tagen'
        if days < 30: return f'vor {days // 7} Wo.'
        return pub_date.strftime('%d.%m.%Y')
    except:
        return ''


# ============================================
# CONTENT MANAGEMENT
# ============================================

def get_content(page: str) -> Dict:
    sb = get_client()
    if not sb: return {}
    try:
        r = sb.table('site_content').select('*').eq('page', page).execute()
        return r.data[0].get('content', {}) if r.data else {}
    except: return {}

def update_content(page: str, content: Dict) -> bool:
    sb = get_client()
    if not sb: return False
    try:
        existing = sb.table('site_content').select('id').eq('page', page).execute()
        if existing.data:
            sb.table('site_content').update({'content': content}).eq('page', page).execute()
        else:
            sb.table('site_content').insert({'page': page, 'content': content}).execute()
        return True
    except: return False


# ============================================
# TEAM MEMBERS
# ============================================

def get_team_members() -> List[Dict]:
    sb = get_client()
    if not sb: return []
    try:
        r = sb.table('team_members').select('*').order('display_order').execute()
        return r.data or []
    except: return []

def add_team_member(data: Dict):
    sb = get_client()
    if not sb: return None
    try:
        return sb.table('team_members').insert({
            'name': data.get('name'), 'role': data.get('role'),
            'bio': data.get('bio'), 'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0)
        }).execute()
    except: return None

def update_team_member(member_id: str, data: Dict):
    sb = get_client()
    if not sb: return False
    try:
        sb.table('team_members').update({
            'name': data.get('name'), 'role': data.get('role'),
            'bio': data.get('bio'), 'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0)
        }).eq('id', member_id).execute()
        return True
    except: return False

def delete_team_member(member_id: str):
    sb = get_client()
    if not sb: return False
    try:
        sb.table('team_members').delete().eq('id', member_id).execute()
        return True
    except: return False


# ============================================
# ADMIN / PRO USER
# ============================================

def get_admin_by_email(email: str):
    sb = get_client()
    if not sb: return None
    try:
        r = sb.table('admins').select('*').eq('email', email).execute()
        return r.data[0] if r.data else None
    except: return None

def get_pro_user(username: str, password: str):
    sb = get_client()
    if not sb: return None
    try:
        r = sb.table('pro_users').select('*') \
            .or_(f'email.eq.{username},company_name.eq.{username}') \
            .eq('password', password).execute()
        return r.data[0] if r.data else None
    except: return None


# ============================================
# ML / RECOMMENDED
# ============================================

def get_recommended_projects(table_name: str, limit: int = 50) -> List[Dict]:
    sb = get_client()
    if not sb or not table_name: return []
    try:
        r = sb.table(table_name).select('*').order('probability', desc=True).limit(limit).execute()
        return [{
            'id': row.get('id'), 'project_id': row.get('project_id'),
            'title': row.get('title') or 'Ohne Titel',
            'description': clean_html(row.get('description') or ''),
            'canton': row.get('canton') or '', 'probability': row.get('probability') or 0,
            'prediction': row.get('prediction'), 'publication_date': row.get('publication_date'),
            'time_ago': calculate_time_ago(row.get('publication_date')),
            'cpv_code': row.get('cpv_code'),
            'simap_url': f"https://www.simap.ch/de/project-detail/{row.get('project_id')}" if row.get('project_id') else "https://www.simap.ch"
        } for row in (r.data or [])]
    except: return []


# ============================================
# FAVORITES
# ============================================

def get_user_favorites(user_id: str) -> List[Dict]:
    sb = get_client()
    if not sb or not user_id: return []
    try:
        r = sb.table('favorites').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        return r.data or []
    except: return []

def add_favorite(user_id: str, project: Dict) -> bool:
    sb = get_client()
    if not sb or not user_id: return False
    try:
        sb.table('favorites').insert({
            'user_id': user_id, 'project_id': project.get('id'),
            'project_title': project.get('title'), 'project_canton': project.get('canton'),
            'project_description': (project.get('description') or '')[:500],
            'simap_url': project.get('simap_url')
        }).execute()
        return True
    except: return False

def remove_favorite(user_id: str, project_id: str) -> bool:
    sb = get_client()
    if not sb or not user_id: return False
    try:
        sb.table('favorites').delete().eq('user_id', user_id).eq('project_id', project_id).execute()
        return True
    except: return False

def get_user_favorites_ids(user_id: str) -> List[str]:
    sb = get_client()
    if not sb or not user_id: return []
    try:
        r = sb.table('favorites').select('project_id').eq('user_id', user_id).execute()
        return [str(row.get('project_id')) for row in (r.data or [])]
    except: return []


# ============================================
# SUPABASE AUTH
# ============================================

def register_user(email: str, password: str, company_name: str) -> Dict:
    sb = get_client()
    if not sb:
        return {'success': False, 'error': 'Datenbank nicht verbunden'}

    try:
        print(f"📝 Registrierung: {email}")
        auth_response = sb.auth.sign_up({
            'email': email,
            'password': password,
            'options': {'data': {'company_name': company_name}}
        })

        if auth_response.user:
            # User-Tabelle befüllen
            try:
                sb.table('users').insert({
                    'id': auth_response.user.id,
                    'email': email,
                    'company_name': company_name,
                    'created_at': datetime.utcnow().isoformat()
                }).execute()
                print(f"✅ User in DB gespeichert")
            except Exception as e:
                print(f"⚠️ User-Tabelle: {e} (Auth war erfolgreich)")

            return {
                'success': True,
                'user': {'id': auth_response.user.id, 'email': email, 'company_name': company_name}
            }
        return {'success': False, 'error': 'Registrierung fehlgeschlagen'}

    except Exception as e:
        msg = str(e)
        print(f"❌ Register-Fehler: {msg}")
        if 'already' in msg.lower():
            return {'success': False, 'error': 'E-Mail bereits registriert'}
        return {'success': False, 'error': f'Fehler: {msg}'}


def login_user(email: str, password: str) -> Dict:
    sb = get_client()
    if not sb:
        return {'success': False, 'error': 'Datenbank nicht verbunden'}

    try:
        print(f"🔐 Login-Versuch: {email}")
        auth_response = sb.auth.sign_in_with_password({
            'email': email,
            'password': password
        })
        print(f"🔐 Response: user={bool(auth_response.user)}, session={bool(auth_response.session)}")

        if auth_response.user and auth_response.session:
            # Company name holen
            company_name = None
            try:
                r = sb.table('users').select('company_name').eq('id', auth_response.user.id).execute()
                if r.data:
                    company_name = r.data[0].get('company_name')
            except:
                pass

            if not company_name and auth_response.user.user_metadata:
                company_name = auth_response.user.user_metadata.get('company_name')

            print(f"✅ Login erfolgreich: {email}, Firma: {company_name}")
            return {
                'success': True,
                'user': {
                    'id': auth_response.user.id,
                    'email': auth_response.user.email,
                    'company_name': company_name
                }
            }
        return {'success': False, 'error': 'Anmeldung fehlgeschlagen'}

    except Exception as e:
        msg = str(e)
        print(f"❌ Login-Fehler: {msg}")
        if 'invalid' in msg.lower() or 'credentials' in msg.lower():
            return {'success': False, 'error': 'Ungültige E-Mail oder Passwort'}
        return {'success': False, 'error': f'Fehler: {msg}'}


def logout_user() -> bool:
    sb = get_client()
    if not sb: return False
    try:
        sb.auth.sign_out()
        return True
    except:
        return False


def get_user_by_id(user_id: str):
    sb = get_client()
    if not sb or not user_id: return None
    try:
        r = sb.table('users').select('*').eq('id', user_id).execute()
        return r.data[0] if r.data else None
    except: return None

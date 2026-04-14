"""
supabase_client.py - Supabase Datenbank Client
SAJF Strategies - Schema: ui
Alle Website-Tabellen liegen im 'ui' Schema.
"""

from supabase import create_client, Client
from typing import List, Dict, Optional
import os
from datetime import datetime, timezone

# ============================================
# GLOBAL CLIENT
# ============================================
supabase: Client = None
supabase_auth: Client = None

# Schema-Name für alle UI-Tabellen
UI_SCHEMA = 'ui'


def init_supabase():
    """Initialisiere Supabase Client"""
    global supabase, supabase_auth

    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url:
        url = 'https://rkfwuxocuojkjswigoss.supabase.co'
    if not key:
        key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJrZnd1eG9jdW9qa2pzd2lnb3NzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mjc4MTUwMywiZXhwIjoyMDc4MzU3NTAzfQ.j-n-tnWaAp9WxoBxWPsYDcU1E4lcKgCYu3ukWzdtF6k'

    print(f"🔗 URL: {url[:50]}...")
    print(f"🔑 Key: {key[:20]}...{key[-10:]}")

    supabase = create_client(url, key)
    supabase_auth = create_client(url, key)
    print(f"✅ Supabase verbunden! Clients initialisiert.")
    return supabase


def get_client():
    """Hole Supabase Client (mit Auto-Init)"""
    global supabase
    if supabase is None:
        init_supabase()
    return supabase

def get_auth_client():
    """Hole separaten Auth Client, um Session-Pollution zu vermeiden"""
    global supabase_auth
    if supabase_auth is None:
        init_supabase()
    return supabase_auth


def ui(table_name: str):
    """Helper: Zugriff auf eine Tabelle im 'ui' Schema."""
    sb = get_client()
    return sb.schema(UI_SCHEMA).table(table_name)


def ui_rpc(function_name: str, params: dict):
    """Helper: Aufruf einer Postgres-Funktion im 'ui' Schema."""
    sb = get_client()
    return sb.schema(UI_SCHEMA).rpc(function_name, params)


# ============================================
# PROJECTS (Tenders)
# ============================================

def get_all_projects(limit: int = 50) -> List[Dict]:
    try:
        response = ui('projects_ui') \
            .select('*') \
            .order('publication_date', desc=True) \
            .limit(limit) \
            .execute()
        return [transform_project(row) for row in (response.data or [])]
    except Exception as e:
        print(f"❌ get_all_projects Fehler: {e}")
        return []


def get_projects_paginated(page=1, per_page=30, search='', canton='',
                           order_type='', process_type='', pub_type='',
                           sort='newest') -> Dict:
    try:
        count_q = ui('projects_ui').select('id', count='exact')
        data_q = ui('projects_ui').select('*')

        if search:
            search_filter = (
                f'title_de.ilike.%{search}%,'
                f'description_de.ilike.%{search}%,'
                f'project_number.ilike.%{search}%,'
                f'proc_office_name_de.ilike.%{search}%'
            )
            count_q = count_q.or_(search_filter)
            data_q = data_q.or_(search_filter)

        if canton:
            count_q = count_q.ilike('canton', canton)
            data_q = data_q.ilike('canton', canton)
        if order_type:
            count_q = count_q.eq('order_type', order_type)
            data_q = data_q.eq('order_type', order_type)
        if process_type:
            count_q = count_q.eq('process_type', process_type)
            data_q = data_q.eq('process_type', process_type)
        if pub_type:
            count_q = count_q.eq('pub_type', pub_type)
            data_q = data_q.eq('pub_type', pub_type)

        if sort == 'oldest':
            data_q = data_q.order('publication_date', desc=False)
        elif sort == 'alpha':
            data_q = data_q.order('title_de', desc=False)
        else:
            data_q = data_q.order('publication_date', desc=True)

        count_result = count_q.execute()
        total = count_result.count if count_result.count else 0

        offset = (page - 1) * per_page
        data_q = data_q.range(offset, offset + per_page - 1)

        data_result = data_q.execute()
        projects = [transform_project(row) for row in (data_result.data or [])]

        import math
        pages = math.ceil(total / per_page) if per_page > 0 else 0

        return {
            'data': projects, 'total': total, 'page': page,
            'per_page': per_page, 'pages': pages
        }

    except Exception as e:
        print(f"❌ get_projects_paginated Fehler: {e}")
        return {'data': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0}


def get_filter_options() -> Dict:
    try:
        all_rows = []
        batch_size = 1000
        offset = 0
        while True:
            r = ui('projects_ui') \
                .select('canton,order_type,process_type,pub_type') \
                .range(offset, offset + batch_size - 1) \
                .execute()
            if not r.data:
                break
            all_rows.extend(r.data)
            if len(r.data) < batch_size:
                break
            offset += batch_size

        cantons = sorted(set(r.get('canton') for r in all_rows if r.get('canton') and r.get('canton').strip()))
        order_types = sorted(set(r.get('order_type') for r in all_rows if r.get('order_type') and r.get('order_type').strip()))
        process_types = sorted(set(r.get('process_type') for r in all_rows if r.get('process_type') and r.get('process_type').strip()))
        pub_types = sorted(set(r.get('pub_type') for r in all_rows if r.get('pub_type') and r.get('pub_type').strip()))

        print(f"✅ Filter-Optionen: {len(cantons)} Kantone, {len(order_types)} Auftragsarten, {len(process_types)} Verfahren, {len(pub_types)} Pub-Typen")
        return {
            'cantons': cantons, 'order_types': order_types,
            'process_types': process_types, 'pub_types': pub_types
        }
    except Exception as e:
        print(f"❌ get_filter_options Fehler: {e}")
        return {'cantons': [], 'order_types': [], 'process_types': [], 'pub_types': []}


def get_project_by_id(project_id: str) -> Optional[Dict]:
    try:
        response = ui('projects_ui').select('*').eq('id', project_id).execute()
        if response.data and len(response.data) > 0:
            return transform_project(response.data[0], include_details=True)
        return None
    except Exception as e:
        print(f"❌ get_project_by_id Fehler: {e}")
        return None


def search_projects(query: str, limit: int = 50) -> List[Dict]:
    if not query:
        return []
    try:
        response = ui('projects_ui') \
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
    try:
        query = ui('projects_ui').select('*')
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
    try:
        all_cantons = []
        batch_size = 1000
        offset = 0
        while True:
            response = ui('projects_ui').select('canton').range(offset, offset + batch_size - 1).execute()
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
    try:
        total = ui('projects_ui').select('id', count='exact').execute()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        today_count = ui('projects_ui').select('id', count='exact').eq('publication_date', today).execute()
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
    try:
        r = ui('site_content').select('*').eq('page', page).execute()
        return r.data[0].get('content', {}) if r.data else {}
    except:
        return {}


def update_content(page: str, content: Dict) -> bool:
    try:
        existing = ui('site_content').select('id').eq('page', page).execute()
        if existing.data:
            ui('site_content').update({'content': content}).eq('page', page).execute()
        else:
            ui('site_content').insert({'page': page, 'content': content}).execute()
        return True
    except:
        return False


# ============================================
# TEAM MEMBERS
# ============================================

def get_team_members() -> List[Dict]:
    try:
        r = ui('team_members').select('*').order('display_order').execute()
        return r.data or []
    except:
        return []


def add_team_member(data: Dict):
    try:
        return ui('team_members').insert({
            'name': data.get('name'), 'role': data.get('role'),
            'bio': data.get('bio'), 'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0)
        }).execute()
    except:
        return None


def update_team_member(member_id: str, data: Dict):
    try:
        ui('team_members').update({
            'name': data.get('name'), 'role': data.get('role'),
            'bio': data.get('bio'), 'photo_url': data.get('photo_url'),
            'display_order': data.get('order', 0)
        }).eq('id', member_id).execute()
        return True
    except:
        return False


def delete_team_member(member_id: str):
    try:
        ui('team_members').delete().eq('id', member_id).execute()
        return True
    except:
        return False


# ============================================
# ADMIN / PRO USER
# ============================================

def get_admin_by_email(email: str):
    try:
        r = ui('admins').select('*').eq('email', email).execute()
        return r.data[0] if r.data else None
    except:
        return None


def get_pro_user(username: str, password: str):
    try:
        r = ui('pro_users').select('*') \
            .or_(f'email.eq.{username},company_name.eq.{username}') \
            .eq('password', password).execute()
        return r.data[0] if r.data else None
    except:
        return None


# ============================================
# ML / RECOMMENDED (alte Pro-User Logik)
# ============================================

def get_recommended_projects(table_name: str, limit: int = 50) -> List[Dict]:
    sb = get_client()
    if not sb or not table_name:
        return []
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
    except:
        return []


# ============================================
# FAVORITES
# ============================================

def get_user_favorites(user_id: str) -> List[Dict]:
    if not user_id:
        return []
    try:
        r = ui('favorites').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        return r.data or []
    except:
        return []


def add_favorite(user_id: str, project: Dict) -> bool:
    if not user_id:
        return False
    try:
        ui('favorites').insert({
            'user_id': user_id, 'project_id': project.get('id'),
            'project_title': project.get('title'), 'project_canton': project.get('canton'),
            'project_description': (project.get('description') or '')[:500],
            'simap_url': project.get('simap_url')
        }).execute()
        return True
    except:
        return False


def remove_favorite(user_id: str, project_id: str) -> bool:
    if not user_id:
        return False
    try:
        ui('favorites').delete().eq('user_id', user_id).eq('project_id', project_id).execute()
        return True
    except:
        return False


def get_user_favorites_ids(user_id: str) -> List[str]:
    if not user_id:
        return []
    try:
        r = ui('favorites').select('project_id').eq('user_id', user_id).execute()
        return [str(row.get('project_id')) for row in (r.data or [])]
    except:
        return []


# ============================================
# SUPABASE AUTH
# ============================================

def register_user(email: str, password: str, company_name: str) -> Dict:
    sb_auth = get_auth_client()
    if not sb_auth:
        return {'success': False, 'error': 'Datenbank nicht verbunden'}

    try:
        print(f"📝 Registrierung: {email}")
        auth_response = sb_auth.auth.sign_up({
            'email': email,
            'password': password,
            'options': {'data': {'company_name': company_name}}
        })

        if auth_response.user:
            try:
                ui('users').insert({
                    'id': auth_response.user.id,
                    'email': email,
                    'company_name': company_name,
                    'created_at': datetime.utcnow().isoformat()
                }).execute()
                print(f"✅ User in ui.users gespeichert")
            except Exception as e:
                print(f"⚠️ ui.users: {e} (Auth war erfolgreich)")

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
    sb_auth = get_auth_client()
    if not sb_auth:
        return {'success': False, 'error': 'Datenbank nicht verbunden'}

    try:
        print(f"🔐 Login-Versuch: {email}")
        auth_response = sb_auth.auth.sign_in_with_password({
            'email': email,
            'password': password
        })

        if auth_response.user and auth_response.session:
            company_name = None
            try:
                r = ui('users').select('company_name').eq('id', auth_response.user.id).execute()
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
    sb_auth = get_auth_client()
    if not sb_auth:
        return False
    try:
        sb_auth.auth.sign_out()
        return True
    except:
        return False


def get_user_by_id(user_id: str):
    if not user_id:
        return None
    try:
        r = ui('users').select('*').eq('id', user_id).execute()
        return r.data[0] if r.data else None
    except:
        return None


# ============================================
# ONBOARDING — NEU mit Embedding-Support
# ============================================

def save_user_profile(user_id, data):
    """Speichere oder update Firmenprofil mit den neuen Filter-Feldern"""
    if not user_id:
        return {'success': False, 'error': 'Nicht eingeloggt'}

    try:
        profile = {
            'user_id': user_id,
            'company_name': data.get('company_name'),
            'employee_count': data.get('employee_count'),
            'headquarters': data.get('headquarters'),
            'canton': data.get('canton'),
            'project_subtype': data.get('project_subtype'),
            'award_amount_min': data.get('award_amount_min'),
            'award_amount_max': data.get('award_amount_max'),
            'updated_at': datetime.utcnow().isoformat()
        }

        existing = ui('user_profiles').select('user_id').eq('user_id', user_id).execute()
        if existing.data:
            ui('user_profiles').update(profile).eq('user_id', user_id).execute()
        else:
            ui('user_profiles').insert(profile).execute()

        # company_name auch in ui.users updaten
        try:
            ui('users').update({'company_name': data.get('company_name')}).eq('id', user_id).execute()
        except:
            pass

        print(f"✅ Profil gespeichert für User: {user_id}")
        return {'success': True}

    except Exception as e:
        print(f"❌ Profil-Fehler: {e}")
        return {'success': False, 'error': str(e)}


def save_user_simap_ids(user_id, ids):
    """Speichere Simap Projekt-IDs"""
    if not user_id:
        return {'success': False, 'error': 'Nicht eingeloggt'}

    try:
        ui('user_simap_ids').delete().eq('user_id', user_id).execute()
        rows = [{'user_id': user_id, 'simap_project_id': str(pid)} for pid in ids]
        if rows:
            ui('user_simap_ids').insert(rows).execute()
        mark_onboarding_complete(user_id)
        print(f"✅ {len(ids)} Simap-IDs gespeichert für User: {user_id}")
        return {'success': True, 'count': len(ids)}

    except Exception as e:
        print(f"❌ Simap-IDs-Fehler: {e}")
        return {'success': False, 'error': str(e)}


def get_onboarding_filter_options():
    """Distinct project_subtypes für das Onboarding-Dropdown"""
    try:
        all_rows = []
        batch_size = 1000
        offset = 0
        while True:
            r = ui('projects_ui') \
                .select('project_subtype') \
                .not_.is_('project_subtype', 'null') \
                .range(offset, offset + batch_size - 1) \
                .execute()
            if not r.data:
                break
            all_rows.extend(r.data)
            if len(r.data) < batch_size:
                break
            offset += batch_size

        subtypes = sorted(set(
            r['project_subtype'] for r in all_rows
            if r.get('project_subtype') and r['project_subtype'].strip()
        ))
        print(f"✅ {len(subtypes)} project_subtypes geladen")
        return {'subtypes': subtypes}

    except Exception as e:
        print(f"❌ get_onboarding_filter_options Fehler: {e}")
        return {'subtypes': []}


def get_filtered_sample_projects(user_id, sample_size=10):
    """Ruft die RPC sample_projects_for_rating auf — gibt 10 gefilterte Projekte zurück"""
    if not user_id:
        return []
    try:
        result = ui_rpc('sample_projects_for_rating', {
            'p_user_id': user_id,
            'sample_size': sample_size
        }).execute()
        print(f"✅ {len(result.data or [])} sample projects für User: {user_id}")
        return result.data or []
    except Exception as e:
        print(f"❌ get_filtered_sample_projects Fehler: {e}")
        return []


def save_user_ratings_v2(user_id, ratings_list):
    """Speichert Ratings (project_id + rating -1/1) und schliesst Onboarding ab"""
    if not user_id:
        return {'success': False, 'error': 'Nicht eingeloggt'}

    try:
        rows = [{
            'user_id': user_id,
            'project_id': r.get('project_id'),
            'rating': r.get('rating')
        } for r in ratings_list if r.get('project_id') and r.get('rating') in (-1, 1)]

        if rows:
            # upsert mit ON CONFLICT auf (user_id, project_id)
            ui('user_tender_ratings').upsert(rows, on_conflict='user_id,project_id').execute()

        mark_onboarding_complete(user_id)
        print(f"✅ {len(rows)} Ratings gespeichert für User: {user_id}")
        return {'success': True, 'count': len(rows)}

    except Exception as e:
        print(f"❌ save_user_ratings_v2 Fehler: {e}")
        return {'success': False, 'error': str(e)}


def get_user_recommendations(user_id, count=20):
    """Personalisierte Empfehlungen via Embedding-Similarity"""
    if not user_id:
        return []
    try:
        result = ui_rpc('recommend_projects_for_user', {
            'p_user_id': user_id,
            'match_count': count
        }).execute()
        print(f"✅ {len(result.data or [])} recommendations für User: {user_id}")
        return result.data or []
    except Exception as e:
        print(f"❌ get_user_recommendations Fehler: {e}")
        return []


# ============================================
# Alte Funktionen — bleiben für Kompatibilität, werden aber nicht mehr genutzt
# ============================================

def save_user_ratings(user_id, ratings_list):
    """[DEPRECATED] alte Version — bitte save_user_ratings_v2 verwenden"""
    print("⚠️ save_user_ratings (alt) aufgerufen — sollte save_user_ratings_v2 sein")
    return save_user_ratings_v2(user_id, ratings_list)


def get_random_archive_tenders(count=20):
    """[DEPRECATED] wurde durch get_filtered_sample_projects ersetzt"""
    print("⚠️ get_random_archive_tenders (alt) aufgerufen")
    return []


def mark_onboarding_complete(user_id):
    """Markiere Onboarding als abgeschlossen — KORRIGIERT auf 'onboarding_completed'"""
    try:
        ui('user_profiles') \
            .update({'onboarding_completed': True, 'updated_at': datetime.utcnow().isoformat()}) \
            .eq('user_id', user_id) \
            .execute()
        print(f"✅ Onboarding completed für User: {user_id}")
    except Exception as e:
        print(f"⚠️ mark_onboarding_complete Fehler: {e}")


def is_onboarding_complete(user_id):
    """Prüfe ob User Onboarding abgeschlossen hat — KORRIGIERT auf 'onboarding_completed'"""
    if not user_id:
        return False

    try:
        r = ui('user_profiles') \
            .select('onboarding_completed') \
            .eq('user_id', user_id) \
            .execute()

        if r.data and len(r.data) > 0:
            return r.data[0].get('onboarding_completed', False)
        return False

    except Exception as e:
        print(f"⚠️ is_onboarding_complete Fehler: {e}")
        return False

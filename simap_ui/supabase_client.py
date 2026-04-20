"""
supabase_client.py - Supabase Datenbank Client
SAJF Strategies - Schema: ui
Alle Website-Tabellen liegen im 'ui' Schema.
"""

from supabase import create_client, Client
from typing import List, Dict, Optional, Tuple
import os
import json
import math
from datetime import datetime, timezone

import numpy as np

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
    # Bevorzugt: ANON Key für UI/Read-only, Service Role nur serverseitig/ETL lokal
    key = (
        os.getenv('SUPABASE_ANON_KEY')
        or os.getenv('SUPABASE_KEY')
        or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    )

    if not url:
        url = 'https://rkfwuxocuojkjswigoss.supabase.co'
    if not key:
        raise RuntimeError(
            "SUPABASE Key fehlt. Setze SUPABASE_ANON_KEY (empfohlen) oder "
            "SUPABASE_SERVICE_ROLE_KEY in deiner lokalen .env Datei."
        )

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


def get_user_ratings_with_details(user_id):
    """
    Alle Bewertungen eines Users mit Projekt-/Archiv-Details.
    Joint je nach source aus projects_ui ODER public.archive.
    """
    if not user_id:
        return []
    try:
        # 1) Alle Ratings laden
        ratings_res = ui('user_tender_ratings') \
            .select('tender_id, rating, source') \
            .eq('user_id', user_id) \
            .execute()

        if not ratings_res.data:
            return []

        # 2) IDs nach Source aufteilen
        project_ids = [r['tender_id'] for r in ratings_res.data if r.get('source') == 'project' and r.get('tender_id')]
        archive_ids = [r['tender_id'] for r in ratings_res.data if r.get('source') == 'archive' and r.get('tender_id')]

        # 3) Details aus jeweiliger Tabelle laden
        project_map = {}
        if project_ids:
            proj_res = ui('projects_ui') \
                .select('id, title_de, canton, project_subtype, award_amount') \
                .in_('id', project_ids) \
                .execute()
            project_map = {str(p['id']): p for p in (proj_res.data or [])}

        archive_map = {}
        if archive_ids:
            # archive liegt in public, daher über den Standard-Client
            from supabase_client import sb  # lokaler Import um Zirkel zu vermeiden
            arch_res = sb.table('archive') \
                .select('id, title_de, canton, order_type, award_amount, winner_name, winner_city, award_decision_date') \
                .in_('id', archive_ids) \
                .execute()
            # order_type → project_subtype zurückmappen für konsistente UI
            reverse_map = {'WORKS': 'construction', 'SERVICES': 'service', 'SUPPLIES': 'supply'}
            archive_map = {}
            for a in (arch_res.data or []):
                a['project_subtype'] = reverse_map.get(a.get('order_type'), a.get('order_type'))
                archive_map[str(a['id'])] = a

        # 4) Zusammenführen
        result = []
        for r in ratings_res.data:
            tid = r.get('tender_id', '')
            source = r.get('source', 'project')

            if source == 'archive':
                details = archive_map.get(tid, {})
                result.append({
                    'tender_id': tid,
                    'rating': r.get('rating'),
                    'source': 'archive',
                    'title_de': details.get('title_de', 'Unbekannt'),
                    'canton': details.get('canton', ''),
                    'project_subtype': details.get('project_subtype', ''),
                    'award_amount': details.get('award_amount'),
                    'winner_name': details.get('winner_name'),
                    'winner_city': details.get('winner_city'),
                    'award_decision_date': details.get('award_decision_date'),
                })
            else:
                details = project_map.get(tid, {})
                result.append({
                    'tender_id': tid,
                    'rating': r.get('rating'),
                    'source': 'project',
                    'title_de': details.get('title_de', 'Unbekannt'),
                    'canton': details.get('canton', ''),
                    'project_subtype': details.get('project_subtype', ''),
                    'award_amount': details.get('award_amount'),
                    'winner_name': None,
                    'winner_city': None,
                    'award_decision_date': None,
                })

        print(f"✅ {len(result)} Bewertungen geladen ({len(project_ids)} Projekte + {len(archive_ids)} Archiv)")
        return result
    except Exception as e:
        print(f"❌ get_user_ratings_with_details Fehler: {e}")
        return []


def update_single_rating(user_id, tender_id, rating, source='project'):
    """
    Einzelne Bewertung aktualisieren (Toggle zwischen 1 und -1).
    source wird benötigt da der Unique-Constraint auf (user_id, tender_id, source) liegt.
    """
    if not user_id or not tender_id or rating not in (-1, 1):
        return {'success': False, 'error': 'Ungültige Parameter'}
    if source not in ('project', 'archive'):
        source = 'project'
    try:
        ui('user_tender_ratings') \
            .update({'rating': rating}) \
            .eq('user_id', user_id) \
            .eq('tender_id', tender_id) \
            .eq('source', source) \
            .execute()
        print(f"✅ Rating aktualisiert: {tender_id} ({source}) → {rating}")
        return {'success': True}
    except Exception as e:
        print(f"❌ update_single_rating Fehler: {e}")
        return {'success': False, 'error': str(e)}


def get_test_runs_overview(top_n: int = 10) -> List[Dict]:
    """Aggregierter Ueberblick fuer /admin/test-runs.

    Fuer jeden Nutzer mit Test-E-Mail (Domain @recommender.dev):
      - company_name, canton, project_subtype
      - n_likes, n_dislikes (gesamt), has_taste_vector
      - avg_pairwise_cosine (Diversity), avg_similarity_top_n
      - Top-5 Empfehlungen (title + similarity)

    Rein Read-only, fuer lokale Tests gedacht.
    """
    try:
        users = ui('users') \
            .select('id,email,company_name') \
            .like('email', '%@recommender.dev') \
            .execute().data or []
    except Exception as e:
        print(f"❌ get_test_runs_overview (users): {e}")
        return []

    overview = []
    for u in users:
        uid = u.get('id')
        email = u.get('email')
        if not uid:
            continue

        row = {
            'user_id': uid,
            'email': email,
            'company_name': u.get('company_name'),
            'canton': None,
            'project_subtype': None,
            'n_likes': 0,
            'n_dislikes': 0,
            'has_taste_vector': False,
            'avg_pairwise_cosine_baseline': None,
            'avg_pairwise_cosine_mmr': None,
            'avg_similarity_top_n': None,
            'top5': [],
        }

        try:
            prof = ui('user_profiles') \
                .select('canton,project_subtype') \
                .eq('user_id', uid) \
                .execute().data or []
            if prof:
                row['canton'] = prof[0].get('canton')
                row['project_subtype'] = prof[0].get('project_subtype')
        except Exception as e:
            print(f"⚠️ test-runs profile: {e}")

        try:
            tv = ui('user_taste_vectors') \
                .select('n_likes,n_dislikes') \
                .eq('user_id', uid) \
                .execute().data or []
            if tv:
                row['has_taste_vector'] = True
                row['n_likes'] = int(tv[0].get('n_likes') or 0)
                row['n_dislikes'] = int(tv[0].get('n_dislikes') or 0)
            else:
                ratings = ui('user_tender_ratings') \
                    .select('rating') \
                    .eq('user_id', uid) \
                    .execute().data or []
                row['n_likes'] = sum(1 for r in ratings if int(r.get('rating', 0)) == 1)
                row['n_dislikes'] = sum(1 for r in ratings if int(r.get('rating', 0)) == -1)
        except Exception as e:
            print(f"⚠️ test-runs taste: {e}")

        if row['has_taste_vector']:
            try:
                m = recommendation_diversity_metric(uid, top_n)
                row['avg_pairwise_cosine_baseline'] = m.get('avg_pairwise_cosine_baseline')
                row['avg_pairwise_cosine_mmr'] = m.get('avg_pairwise_cosine_mmr')
            except Exception as e:
                print(f"⚠️ test-runs metric: {e}")

            try:
                recs = get_user_recommendations(uid, top_n) or []
                sims = [r.get('similarity') for r in recs if isinstance(r.get('similarity'), (int, float))]
                if sims:
                    row['avg_similarity_top_n'] = round(sum(sims) / len(sims), 4)
                row['top5'] = [{
                    'id': r.get('id'),
                    'title': (r.get('title_de') or '')[:90],
                    'similarity': round(r.get('similarity', 0.0), 4),
                } for r in recs[:5]]
            except Exception as e:
                print(f"⚠️ test-runs recs: {e}")

        overview.append(row)
    return overview


def get_feed_ratings_map(user_id, source='project'):
    """Gibt {tender_id: rating} fuer einen User zurueck (fuer UI-Sync)."""
    if not user_id:
        return {}
    try:
        rows = ui('user_tender_ratings') \
            .select('tender_id,rating,source') \
            .eq('user_id', user_id) \
            .eq('source', source) \
            .execute().data or []
        return {r['tender_id']: int(r['rating']) for r in rows if r.get('rating') in (-1, 1)}
    except Exception as e:
        print(f"❌ get_feed_ratings_map Fehler: {e}")
        return {}


def upsert_feed_rating(user_id, tender_id, rating, source='project'):
    """
    Idempotentes Rating aus dem Live-Feed:
      rating ==  1  -> Like
      rating == -1  -> Dislike
      rating ==  0  -> Entfernen (Unrate)

    Upsert auf Unique-Key (user_id, tender_id, source).
    Trigger ui.tg_user_tender_ratings_refresh_taste aktualisiert danach
    automatisch ui.user_taste_vectors (Rocchio).
    """
    if not user_id or not tender_id:
        return {'success': False, 'error': 'Ungültige Parameter'}
    if rating not in (-1, 0, 1):
        return {'success': False, 'error': 'rating muss -1, 0 oder 1 sein'}
    if source not in ('project', 'archive'):
        source = 'project'

    try:
        if rating == 0:
            ui('user_tender_ratings') \
                .delete() \
                .eq('user_id', user_id) \
                .eq('tender_id', str(tender_id)) \
                .eq('source', source) \
                .execute()
            return {'success': True, 'action': 'deleted'}

        ui('user_tender_ratings').upsert(
            {
                'user_id': user_id,
                'tender_id': str(tender_id),
                'rating': rating,
                'source': source,
            },
            on_conflict='user_id,tender_id,source',
        ).execute()
        return {'success': True, 'action': 'upsert', 'rating': rating}
    except Exception as e:
        print(f"❌ upsert_feed_rating Fehler: {e}")
        return {'success': False, 'error': str(e)}



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
# ONBOARDING - NEU mit Embedding-Support
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


# ============================================
# RECOMMENDATIONS (Task 4 + Task 5)
#
# Pipeline:
#   1. RPC ui.recommend_projects_for_user_v2 liefert einen groesseren
#      Kandidaten-Pool (Default 50) inkl. der 1024-d Embeddings.
#      Der Taste-Vektor wird in der Datenbank aus ui.user_taste_vectors
#      gelesen (materialisiert via Rocchio-Trigger, siehe
#      ui.refresh_user_taste).
#   2. mmr_rerank() selektiert daraus per Maximal Marginal Relevance
#      die final sichtbaren N Empfehlungen und erzwingt dabei eine
#      Mindest-Diversitaet (Cosine-Distanz >= MMR_MIN_DIVERSITY) zum
#      bereits ausgewaehlten Satz.
#
# Messbarkeit:
#   recommendation_diversity_metric() berechnet die mittlere
#   pairwise-Cosine-Aehnlichkeit ueber die Top-N; Zielwert <= 0.75.
# ============================================

MMR_LAMBDA = 0.7            # Gewichtung Relevanz vs. Diversitaet
MMR_MIN_DIVERSITY = 0.3     # min. Cosine-Distanz zum Selected-Set
MMR_POOL_SIZE = 50          # Kandidaten-Pool aus dem RPC
# -> max_allowed_sim_to_selected = 1 - MMR_MIN_DIVERSITY


def _parse_pgvector(raw) -> Optional[np.ndarray]:
    """pgvector kommt ueber PostgREST als JSON-Array-String ("[0.12,-0.03,...]")
    oder bereits als list/tuple zurueck. Diese Funktion parst beides."""
    if raw is None:
        return None
    if isinstance(raw, np.ndarray):
        return raw.astype(np.float32, copy=False)
    if isinstance(raw, (list, tuple)):
        return np.asarray(raw, dtype=np.float32)
    if isinstance(raw, str):
        try:
            return np.asarray(json.loads(raw), dtype=np.float32)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _mmr_rerank(
    candidates: List[Dict],
    k: int,
    lambda_param: float = MMR_LAMBDA,
    min_diversity: float = MMR_MIN_DIVERSITY,
) -> List[Dict]:
    """Maximal Marginal Relevance.

    candidates: Liste von Dicts mit Keys 'similarity' (float) und
                'embedding' (np.ndarray, L2-normalisiert).
    Gibt die ausgewaehlten Kandidaten in gewaehlter Reihenfolge zurueck.

    Einschub im Vergleich zum Standard-MMR: wir lassen die Diversitaets-
    Constraint als harte Kappung wirken (Kandidaten mit zu hoher
    Aehnlichkeit zum bereits gewaehlten Set werden uebersprungen),
    damit das UX-Ziel "nie mehr als ein Gewerk desselben Bauvorhabens"
    wirklich durchgesetzt wird. Wird dadurch k nicht erreicht, faellt
    die Kappung stufenweise, um nicht leer zurueckzugeben.
    """
    if not candidates:
        return []

    pool = [c for c in candidates if c.get('embedding') is not None]
    if not pool:
        return candidates[:k]

    max_sim_to_selected = 1.0 - min_diversity  # = 0.7 bei Default

    selected: List[Dict] = []
    selected_mat: List[np.ndarray] = []
    remaining = list(pool)

    while remaining and len(selected) < k:
        best_idx = -1
        best_score = -math.inf

        for i, cand in enumerate(remaining):
            rel = float(cand['similarity'])
            if selected_mat:
                cand_vec = cand['embedding']
                sim_to_selected = max(
                    float(np.dot(cand_vec, s)) for s in selected_mat
                )
                if sim_to_selected > max_sim_to_selected:
                    continue
                mmr_score = lambda_param * rel - (1 - lambda_param) * sim_to_selected
            else:
                mmr_score = rel

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        if best_idx == -1:
            # Alle verbleibenden Kandidaten verletzen die Diversitaets-
            # Kappung. Kappung lockern und weiter auffuellen.
            max_sim_to_selected = min(1.0, max_sim_to_selected + 0.05)
            continue

        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        selected_mat.append(chosen['embedding'])

    return selected


def _strip_embedding(rec: Dict) -> Dict:
    """Embedding entfernen bevor das Result ans Frontend geht."""
    out = {k: v for k, v in rec.items() if k != 'embedding'}
    return out


def get_user_recommendations(user_id, count: int = 20):
    """Personalisierte Empfehlungen: Rocchio-Taste-Vektor (materialisiert)
    kombiniert mit MMR-Reranking fuer Diversitaet."""
    if not user_id:
        return []
    try:
        pool_size = max(MMR_POOL_SIZE, count * 3)
        result = ui_rpc('recommend_projects_for_user_v2', {
            'p_user_id': user_id,
            'match_count_pool': pool_size,
        }).execute()
        raw = result.data or []

        candidates: List[Dict] = []
        for row in raw:
            vec = _parse_pgvector(row.get('embedding'))
            if vec is None:
                continue
            n = float(np.linalg.norm(vec))
            if n > 0 and abs(n - 1.0) > 1e-3:
                vec = vec / n
            candidates.append({**row, 'embedding': vec})

        reranked = _mmr_rerank(candidates, k=count)
        clean = [_strip_embedding(c) for c in reranked]

        print(f"✅ {len(clean)} recommendations (pool={len(candidates)}) für User: {user_id}")
        return clean
    except Exception as e:
        print(f"❌ get_user_recommendations Fehler: {e}")
        return []


def recommendation_diversity_metric(user_id, count: int = 10) -> Dict:
    """Misst die Diversitaet der Top-N Empfehlungen eines Users:
    durchschnittliche pairwise-Cosine-Aehnlichkeit.
    Ziel (siehe Task 4): <= 0.75.

    Gibt zusaetzlich das Ergebnis der Baseline (vor MMR) zurueck, damit
    der Effekt von MMR direkt vergleichbar ist.
    """
    if not user_id:
        return {'error': 'Kein user_id'}
    try:
        pool_size = max(MMR_POOL_SIZE, count * 3)
        result = ui_rpc('recommend_projects_for_user_v2', {
            'p_user_id': user_id,
            'match_count_pool': pool_size,
        }).execute()
        raw = result.data or []
        if not raw:
            return {'user_id': user_id, 'error': 'Keine Empfehlungen.'}

        parsed = []
        for row in raw:
            vec = _parse_pgvector(row.get('embedding'))
            if vec is not None:
                n = float(np.linalg.norm(vec))
                if n > 0 and abs(n - 1.0) > 1e-3:
                    vec = vec / n
                parsed.append({**row, 'embedding': vec})

        baseline = parsed[:count]
        mmr = _mmr_rerank(parsed, k=count)

        def avg_pairwise_cos(items):
            vecs = [x['embedding'] for x in items if x.get('embedding') is not None]
            if len(vecs) < 2:
                return None
            M = np.vstack(vecs)
            S = M @ M.T
            iu = np.triu_indices(len(vecs), k=1)
            return float(S[iu].mean())

        return {
            'user_id': user_id,
            'pool_size': len(parsed),
            'top_n': count,
            'avg_pairwise_cosine_baseline': avg_pairwise_cos(baseline),
            'avg_pairwise_cosine_mmr': avg_pairwise_cos(mmr),
            'target_max': 0.75,
        }
    except Exception as e:
        print(f"❌ recommendation_diversity_metric Fehler: {e}")
        return {'error': str(e)}


# ============================================
# Alte Funktionen - bleiben für Kompatibilität, werden aber nicht mehr genutzt
# ============================================

def save_user_ratings(user_id, ratings_list):
    """[DEPRECATED] alte Version - bitte save_user_ratings_v2 verwenden"""
    print("⚠️ save_user_ratings (alt) aufgerufen - sollte save_user_ratings_v2 sein")
    return save_user_ratings_v2(user_id, ratings_list)

def get_filtered_sample_projects(user_id, sample_size=20):
    """
    Ruft die RPC auf und gibt die Mischung aus project + archive zurück.
    Die RPC liefert bereits source, winner_name, winner_city, award_decision_date.
    """
    if not user_id:
        return []
    try:
        result = ui_rpc('sample_projects_for_rating', {
            'p_user_id': user_id,
            'sample_size': sample_size
        })
        projects = result.data if hasattr(result, 'data') else result

        # description_de hat HTML-Tags drin – für die UI ok, Frontend stripped
        for p in (projects or []):
            # award_decision_date als String falls date-Objekt zurückkommt
            if p.get('award_decision_date'):
                p['award_decision_date'] = str(p['award_decision_date'])

        print(f"✅ {len(projects or [])} Sample-Projekte geladen für User: {user_id}")
        return projects or []
    except Exception as e:
        print(f"❌ get_filtered_sample_projects Fehler: {e}")
        return []


def save_user_ratings_v2(user_id, ratings_list):
    """
    Ratings speichern - inkl. source ('project' oder 'archive').

    Erwartetes Format pro rating:
        {'project_id': <uuid>, 'rating': 1|-1, 'source': 'project'|'archive'}
    """
    if not user_id or not ratings_list:
        return {'success': False, 'error': 'Keine Ratings übergeben'}

    try:
        rows = []
        for r in ratings_list:
            tender_id = r.get('project_id')
            rating_val = r.get('rating')
            source = r.get('source', 'project')  # Default: project (für Backwards-Compat)

            if not tender_id or rating_val not in (-1, 1):
                continue
            if source not in ('project', 'archive'):
                source = 'project'

            rows.append({
                'user_id': user_id,
                'tender_id': str(tender_id),
                'rating': rating_val,
                'source': source,
            })

        if not rows:
            return {'success': False, 'error': 'Keine gültigen Ratings'}

        # Upsert damit bei Re-Rating die bestehende Zeile überschrieben wird
        ui('user_tender_ratings').upsert(
            rows,
            on_conflict='user_id,tender_id,source'
        ).execute()

        # Onboarding als abgeschlossen markieren
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
# Alte Funktionen - bleiben für Kompatibilität, werden aber nicht mehr genutzt
# ============================================

def save_user_ratings(user_id, ratings_list):
    """[DEPRECATED] alte Version - bitte save_user_ratings_v2 verwenden"""
    print("⚠️ save_user_ratings (alt) aufgerufen - sollte save_user_ratings_v2 sein")
    return save_user_ratings_v2(user_id, ratings_list)


def get_random_archive_tenders(count=20):
    """[DEPRECATED] wurde durch get_filtered_sample_projects ersetzt"""
    print("⚠️ get_random_archive_tenders (alt) aufgerufen")
    return []


def mark_onboarding_complete(user_id):
    """Markiere Onboarding als abgeschlossen - KORRIGIERT auf 'onboarding_completed'"""
    try:
        ui('user_profiles') \
            .update({'onboarding_completed': True, 'updated_at': datetime.utcnow().isoformat()}) \
            .eq('user_id', user_id) \
            .execute()
        print(f"✅ Onboarding completed für User: {user_id}")
    except Exception as e:
        print(f"⚠️ mark_onboarding_complete Fehler: {e}")


def is_onboarding_complete(user_id):
    """Prüfe ob User Onboarding abgeschlossen hat - KORRIGIERT auf 'onboarding_completed'"""
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

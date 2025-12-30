#!/usr/bin/env python3
"""
SIMAP Historical Sync - Lädt alle Aufträge seit 1. Juli 2024

Verwendung:
    python historical_sync.py --start 2024-07-01
    python historical_sync.py --start 2024-07-01 --end 2024-12-31
    python historical_sync.py --start 2024-07-01 --batch-days 7 --delay 1.0
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
from dotenv import load_dotenv

# Optional: Supabase Client
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("⚠ supabase-py nicht installiert. Installiere mit: pip install supabase")
    sys.exit(1)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

SIMAP_API_BASE = "https://www.simap.ch/api"
SEARCH_ENDPOINT = "/publications/v2/project/project-search"
DETAIL_ENDPOINT = "/publications/v1/project"

DEFAULT_CANTONS = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
    "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",  # Alle Kantone
]

PUB_TYPES_WITH_DETAILS = [
    'tender', 'award', 'direct_award', 'competition',
    'study_contract', 'participant_selection', 'selective_offering_phase',
]

DELAY_SEARCH = 0.15
DELAY_DETAIL = 0.2

# ============================================================================
# SUPABASE CLIENT
# ============================================================================

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        logger.error("SUPABASE_URL und SUPABASE_KEY müssen gesetzt sein!")
        sys.exit(1)
    
    return create_client(url, key)

# ============================================================================
# SIMAP API
# ============================================================================

def fetch_projects_for_date_range(
    start_date: str,
    end_date: Optional[str] = None,
    cantons: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Holt alle Projekte für einen Datumsbereich."""
    
    projects = []
    last_item = None
    page = 0
    
    session = requests.Session()
    session.headers.update({
        'Accept': 'application/json',
        'User-Agent': 'SIMAP-Historical-Sync/1.0'
    })
    
    while True:
        params = {'newestPublicationFrom': start_date}
        if end_date:
            params['newestPublicationTo'] = end_date
        if cantons:
            params['orderAddressCantons'] = ','.join(cantons)
        if last_item:
            params['lastItem'] = last_item
        
        url = f"{SIMAP_API_BASE}{SEARCH_ENDPOINT}"
        
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"API Error: {e}")
            break
        
        page_projects = data.get('projects', [])
        if not page_projects:
            break
        
        projects.extend(page_projects)
        
        last_item = data.get('pagination', {}).get('lastItem')
        if not last_item:
            break
        
        page += 1
        if page % 10 == 0:
            logger.info(f"  ... {len(projects)} Projekte geladen (Seite {page})")
        
        time.sleep(DELAY_SEARCH)
    
    return projects

def fetch_detail(session: requests.Session, project_id: str, publication_id: str) -> Optional[Dict]:
    """Holt Details für ein Projekt."""
    url = f"{SIMAP_API_BASE}{DETAIL_ENDPOINT}/{project_id}/publication-details/{publication_id}"
    
    try:
        response = session.get(url, timeout=30)
        if response.status_code in (401, 403, 404):
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

# ============================================================================
# PARSING
# ============================================================================

def get_translation(obj: Any, lang: str = 'de') -> Optional[str]:
    if not obj or not isinstance(obj, dict):
        return None
    return obj.get(lang)

def get_any_translation(obj: Any) -> Optional[str]:
    if not obj or not isinstance(obj, dict):
        return None
    return obj.get('de') or obj.get('fr') or obj.get('it') or obj.get('en')

def extract_code(code: Any) -> Optional[str]:
    if not code:
        return None
    if isinstance(code, str):
        return code
    if isinstance(code, dict):
        return code.get('code')
    return None

def parse_codes_array(arr: Any) -> List[str]:
    if not isinstance(arr, list):
        return []
    return [c for c in (extract_code(item) for item in arr) if c]

def parse_date(date_str: Any) -> Optional[str]:
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        if 'T' in date_str:
            return date_str.split('T')[0]
        return date_str[:10]
    except:
        return None

def parse_datetime(date_str: Any) -> Optional[str]:
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.isoformat()
    except:
        return None

def parse_project(entry: Dict) -> Dict[str, Any]:
    """Parsed ein Projekt aus der Search API."""
    
    now = datetime.utcnow().isoformat()
    
    # Address
    order_addr = entry.get('orderAddress') or {}
    lots = entry.get('lots') or []
    
    canton = order_addr.get('cantonId') if order_addr else None
    city = get_any_translation(order_addr.get('city')) if order_addr else None
    postal_code = order_addr.get('postalCode') if order_addr else None
    country = order_addr.get('countryId', 'CH') if order_addr else 'CH'
    
    # Fallback from lots
    if not canton and lots and len(lots) > 0:
        lot_addr = lots[0].get('orderAddress') or {}
        if lot_addr:
            canton = lot_addr.get('cantonId')
            city = get_any_translation(lot_addr.get('city'))
            postal_code = lot_addr.get('postalCode')
            country = lot_addr.get('countryId') or 'CH'
    
    # Publication number
    pub_num = entry.get('publicationNumber')
    if isinstance(pub_num, dict):
        pub_num = pub_num.get('publicationNumber')
    
    return {
        # IDs
        'simap_project_id': entry.get('id'),
        'simap_publication_id': entry.get('publicationId'),
        'project_number': entry.get('projectNumber'),
        'publication_number': pub_num,
        
        # Titel
        'title_de': get_translation(entry.get('title'), 'de'),
        'title_fr': get_translation(entry.get('title'), 'fr'),
        'description_de': None,
        'description_fr': None,
        
        # Datum
        'publication_date': parse_date(entry.get('publicationDate')) or now[:10],
        'submission_deadline': None,
        'offer_opening_date': None,
        'award_decision_date': None,
        
        # Klassifizierung
        'pub_type': entry.get('pubType', 'unknown'),
        'project_type': entry.get('projectType'),
        'project_subtype': entry.get('projectSubType'),
        'process_type': entry.get('processType'),
        'order_type': entry.get('orderType'),
        'lots_type': entry.get('lotsType'),
        'lots_count': len(lots),
        'corrected': entry.get('corrected', False),
        
        # Standort
        'canton': canton,
        'city': city,
        'postal_code': postal_code,
        'country': country,
        
        # Codes
        'cpv_code_main': None,
        'cpv_codes': [],
        'bkp_codes': [],
        'oag_codes': [],
        
        # Beschaffungsstelle
        'proc_office_id': entry.get('procOfficeId'),
        'proc_office_name_de': get_translation(entry.get('procOfficeName'), 'de'),
        'proc_office_name_fr': get_translation(entry.get('procOfficeName'), 'fr'),
        'proc_office_street': None,
        'proc_office_city': None,
        'proc_office_postal_code': None,
        'proc_office_canton': None,
        'proc_office_email': None,
        'proc_office_phone': None,
        'proc_office_contact': None,
        
        # Auftraggeber
        'recipient_name': None,
        'recipient_city': None,
        'recipient_canton': None,
        
        # Award
        'winner_id': None,
        'winner_name': None,
        'winner_street': None,
        'winner_city': None,
        'winner_postal_code': None,
        'winner_canton': None,
        'award_amount': None,
        'award_currency': None,
        'award_vat_type': None,
        'number_of_submissions': None,
        'all_winners': None,
        
        # Award Details
        'award_justification_de': None,
        'remedies_notice_de': None,
        'total_price_selection': None,
        
        # Referenzen
        'referencing_pub_id': None,
        'referencing_pub_type': None,
        'referencing_pub_date': None,
        'referencing_pub_number': None,
        
        # Bau
        'construction_type': None,
        'construction_category': None,
        
        # Metadaten
        'publication_ted': False,
        'state_contract_area': False,
        'creation_language': None,
        'has_project_documents': False,
        
        # Sync
        'content_hash': str(hash(str(entry.get('title'))) % 10**8),
        'last_checked_at': now,
        'detail_fetched_at': None,
        
        # Raw
        'raw_json_search': entry,
        'raw_json_detail': None,
    }

def enrich_with_detail(project: Dict, detail: Dict) -> Dict:
    """Reichert Projekt mit Detail-Daten an."""
    
    now = datetime.utcnow().isoformat()
    
    base = detail.get('base', {})
    procurement = detail.get('procurement', {})
    dates = detail.get('dates', {})
    decision = detail.get('decision', {})
    terms = detail.get('terms', {})
    project_info = detail.get('project-info', {})
    referencing_pub = detail.get('referencingPub', {})
    
    # Base
    project['publication_ted'] = base.get('publicationTed', False)
    project['state_contract_area'] = base.get('stateContractArea', False)
    project['creation_language'] = base.get('creationLanguage')
    project['referencing_pub_id'] = base.get('referencingPubId')
    
    # Procurement
    if procurement:
        order_desc = procurement.get('orderDescription', {})
        project['description_de'] = get_translation(order_desc, 'de')
        project['description_fr'] = get_translation(order_desc, 'fr')
        
        main_cpv = extract_code(procurement.get('cpvCode'))
        if main_cpv:
            project['cpv_code_main'] = main_cpv
            project['cpv_codes'] = [main_cpv]
        
        project['cpv_codes'] = list(set(
            project['cpv_codes'] + parse_codes_array(procurement.get('additionalCpvCodes', []))
        ))
        project['bkp_codes'] = parse_codes_array(procurement.get('bkpCodes', []))
        project['oag_codes'] = parse_codes_array(procurement.get('oagCodes', []))
        
        project['order_type'] = project['order_type'] or procurement.get('orderType')
        project['construction_type'] = procurement.get('constructionType')
        project['construction_category'] = procurement.get('constructionCategory')
    
    # Dates
    if dates:
        project['submission_deadline'] = parse_datetime(dates.get('offerDeadline') or dates.get('submissionDeadline'))
        project['offer_opening_date'] = parse_datetime(dates.get('offerOpening') or dates.get('offerOpeningDate'))
    
    # Terms
    if terms:
        remedies = terms.get('remediesNotice', {})
        project['remedies_notice_de'] = get_translation(remedies, 'de')
    
    # Project Info
    if project_info:
        proc_addr = project_info.get('procOfficeAddress', {})
        if proc_addr:
            project['proc_office_street'] = get_any_translation(proc_addr.get('street'))
            project['proc_office_city'] = get_any_translation(proc_addr.get('city'))
            project['proc_office_postal_code'] = proc_addr.get('postalCode')
            project['proc_office_canton'] = proc_addr.get('cantonId')
            project['proc_office_email'] = proc_addr.get('email')
            project['proc_office_phone'] = proc_addr.get('phone')
            project['proc_office_contact'] = get_any_translation(proc_addr.get('contactPerson'))
        
        recipient_addr = project_info.get('procurementRecipientAddress', {})
        if recipient_addr:
            project['recipient_name'] = get_any_translation(recipient_addr.get('name'))
            project['recipient_city'] = get_any_translation(recipient_addr.get('city'))
            project['recipient_canton'] = recipient_addr.get('cantonId')
    
    # Decision (Award)
    if decision and project['pub_type'] in ('award', 'direct_award'):
        vendors = decision.get('vendors', [])
        
        if vendors:
            all_winners = []
            for vendor in vendors:
                vendor_addr = vendor.get('vendorAddress', {})
                price = vendor.get('price', {})
                
                winner_data = {
                    'vendor_id': vendor.get('vendorId'),
                    'name': vendor.get('vendorName'),
                    'street': vendor_addr.get('street'),
                    'city': get_any_translation(vendor_addr.get('city')),
                    'postal_code': vendor_addr.get('postalCode'),
                    'canton': vendor_addr.get('cantonId'),
                    'country': vendor_addr.get('countryId', 'CH'),
                    'price': price.get('price') if isinstance(price.get('price'), (int, float)) else None,
                    'currency': (price.get('currency') or 'CHF').upper() if price else None,
                    'vat_type': price.get('vatType'),
                }
                all_winners.append(winner_data)
            
            project['all_winners'] = all_winners
            
            # Primary winner
            primary = all_winners[0]
            project['winner_id'] = primary['vendor_id']
            project['winner_name'] = primary['name']
            project['winner_street'] = primary['street']
            project['winner_city'] = primary['city']
            project['winner_postal_code'] = primary['postal_code']
            project['winner_canton'] = primary['canton']
            project['award_amount'] = primary['price']
            project['award_currency'] = primary['currency']
            project['award_vat_type'] = primary['vat_type']
        
        project['number_of_submissions'] = decision.get('numberOfSubmissions')
        project['award_decision_date'] = parse_date(decision.get('awardDecisionDate'))
        project['total_price_selection'] = decision.get('totalPriceSelection')
        
        justification = decision.get('awardDecisionJustification', {})
        project['award_justification_de'] = get_translation(justification, 'de')
    
    # Referencing Pub
    if referencing_pub:
        project['referencing_pub_id'] = project['referencing_pub_id'] or referencing_pub.get('publicationId')
        project['referencing_pub_type'] = referencing_pub.get('pubType')
        project['referencing_pub_date'] = parse_date(referencing_pub.get('publicationDate'))
        project['referencing_pub_number'] = referencing_pub.get('publicationNumber')
    
    # Metadata
    project['has_project_documents'] = detail.get('hasProjectDocuments', False)
    
    # Tracking
    project['raw_json_detail'] = detail
    project['detail_fetched_at'] = now
    
    return project

# ============================================================================
# SYNC
# ============================================================================

def sync_batch(
    supabase: Client,
    start_date: str,
    end_date: str,
    cantons: List[str],
    fetch_details: bool = True
) -> Dict[str, int]:
    """Synchronisiert einen Batch (Datumsbereich)."""
    
    stats = {
        'fetched': 0,
        'new': 0,
        'updated': 0,
        'details': 0,
        'errors': 0,
    }
    
    logger.info(f"Fetching {start_date} to {end_date}...")
    
    # Fetch from SIMAP
    raw_projects = fetch_projects_for_date_range(start_date, end_date, cantons)
    stats['fetched'] = len(raw_projects)
    
    if not raw_projects:
        logger.info(f"  Keine Projekte gefunden")
        return stats
    
    logger.info(f"  {len(raw_projects)} Projekte gefunden")
    
    # Check existing
    project_ids = [p['id'] for p in raw_projects]
    existing = set()
    
    for i in range(0, len(project_ids), 500):
        batch_ids = project_ids[i:i+500]
        result = supabase.table('projects').select('simap_project_id').in_('simap_project_id', batch_ids).execute()
        existing.update(row['simap_project_id'] for row in result.data)
    
    # Parse projects
    projects = []
    needs_detail = []
    
    for raw in raw_projects:
        project = parse_project(raw)
        projects.append(project)
        
        if raw['id'] not in existing:
            stats['new'] += 1
        else:
            stats['updated'] += 1
        
        if fetch_details and project['pub_type'] in PUB_TYPES_WITH_DETAILS:
            if project['simap_publication_id']:
                needs_detail.append(project)
    
    # Fetch details
    if fetch_details and needs_detail:
        logger.info(f"  Fetching details for {len(needs_detail)} projects...")
        
        session = requests.Session()
        session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'SIMAP-Historical-Sync/1.0'
        })
        
        for i, project in enumerate(needs_detail):
            detail = fetch_detail(
                session,
                project['simap_project_id'],
                project['simap_publication_id']
            )
            
            if detail:
                enrich_with_detail(project, detail)
                stats['details'] += 1
            else:
                stats['errors'] += 1
            
            if (i + 1) % 50 == 0:
                logger.info(f"    ... {i + 1}/{len(needs_detail)} details")
            
            time.sleep(DELAY_DETAIL)
    
    # Upsert to DB
    logger.info(f"  Upserting {len(projects)} projects...")
    
    for i in range(0, len(projects), 100):
        batch = projects[i:i+100]
        try:
            supabase.table('projects').upsert(
                batch,
                on_conflict='simap_project_id,simap_publication_id'
            ).execute()
        except Exception as e:
            logger.error(f"  Upsert error: {e}")
            stats['errors'] += len(batch)
    
    logger.info(f"  ✓ {stats['new']} new, {stats['updated']} updated, {stats['details']} details")
    
    return stats

def historical_sync(
    start_date: str,
    end_date: Optional[str] = None,
    batch_days: int = 7,
    cantons: Optional[List[str]] = None,
    fetch_details: bool = True,
    delay_between_batches: float = 1.0
):
    """Führt einen historischen Sync durch."""
    
    supabase = get_supabase_client()
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
    
    if cantons is None:
        cantons = DEFAULT_CANTONS
    
    total_stats = {
        'batches': 0,
        'fetched': 0,
        'new': 0,
        'updated': 0,
        'details': 0,
        'errors': 0,
    }
    
    logger.info("=" * 60)
    logger.info("SIMAP HISTORICAL SYNC")
    logger.info("=" * 60)
    logger.info(f"Start:      {start_date}")
    logger.info(f"End:        {end.strftime('%Y-%m-%d')}")
    logger.info(f"Batch size: {batch_days} days")
    logger.info(f"Cantons:    {len(cantons)}")
    logger.info(f"Details:    {'Yes' if fetch_details else 'No'}")
    logger.info("=" * 60)
    
    current = start
    while current < end:
        batch_end = min(current + timedelta(days=batch_days), end)
        
        batch_start_str = current.strftime('%Y-%m-%d')
        batch_end_str = batch_end.strftime('%Y-%m-%d')
        
        stats = sync_batch(
            supabase,
            batch_start_str,
            batch_end_str,
            cantons,
            fetch_details
        )
        
        total_stats['batches'] += 1
        total_stats['fetched'] += stats['fetched']
        total_stats['new'] += stats['new']
        total_stats['updated'] += stats['updated']
        total_stats['details'] += stats['details']
        total_stats['errors'] += stats['errors']
        
        current = batch_end + timedelta(days=1)
        
        if current < end:
            time.sleep(delay_between_batches)
    
    logger.info("=" * 60)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Batches:    {total_stats['batches']}")
    logger.info(f"Fetched:    {total_stats['fetched']}")
    logger.info(f"New:        {total_stats['new']}")
    logger.info(f"Updated:    {total_stats['updated']}")
    logger.info(f"Details:    {total_stats['details']}")
    logger.info(f"Errors:     {total_stats['errors']}")
    logger.info("=" * 60)
    
    return total_stats

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SIMAP Historical Sync")
    parser.add_argument('--start', '-s', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', '-e', help='End date (YYYY-MM-DD), default: today')
    parser.add_argument('--batch-days', '-b', type=int, default=7, help='Days per batch (default: 7)')
    parser.add_argument('--cantons', '-c', nargs='+', help='Cantons to fetch (default: all)')
    parser.add_argument('--no-details', action='store_true', help='Skip fetching details')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between batches in seconds')
    
    args = parser.parse_args()
    
    historical_sync(
        start_date=args.start,
        end_date=args.end,
        batch_days=args.batch_days,
        cantons=args.cantons,
        fetch_details=not args.no_details,
        delay_between_batches=args.delay
    )

if __name__ == '__main__':
    main()

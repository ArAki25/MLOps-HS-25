#!/usr/bin/env python
"""
SIMAP Database Tools v3 - Python Client

Tools für:
1. Full Sync über Supabase Edge Function
2. Export für ML Training
3. Details nachfüllen für bestehende Projekte
4. Statistiken

Verwendung:
    python simap_tools.py stats
    python simap_tools.py full-sync
    python simap_tools.py export-ml --output data/ml_training.parquet
    python simap_tools.py fill-details --limit 100
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
import pandas as pd
from dotenv import load_dotenv

# Optional: Supabase Python Client
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("⚠ supabase-py nicht installiert. Installiere mit: pip install supabase")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# KONFIGURATION
# ============================================================================

SIMAP_API_BASE = "https://www.simap.ch/api"
SEARCH_ENDPOINT = "/publications/v2/project/project-search"
DETAIL_ENDPOINT = "/publications/v1/project"

DEFAULT_CANTONS = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
    "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
]

PUB_TYPES_WITH_DETAILS = [
    'tender', 'award', 'direct_award', 'competition', 
    'study_contract', 'participant_selection', 'selective_offering_phase'
]

# ============================================================================
# SUPABASE CLIENT
# ============================================================================

def get_supabase_client() -> Optional['Client']:
    """Erstellt Supabase Client aus Umgebungsvariablen."""
    if not HAS_SUPABASE:
        return None
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        logger.error("SUPABASE_URL und SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY müssen gesetzt sein!")
        return None
    
    return create_client(url, key)

def get_supabase_url() -> Optional[str]:
    """Gibt die Supabase URL zurück."""
    url = os.environ.get("SUPABASE_URL")
    if not url:
        logger.error("SUPABASE_URL muss gesetzt sein!")
        return None
    return url.rstrip('/')

def get_supabase_anon_key() -> Optional[str]:
    """Gibt den Supabase Anon Key zurück (für Edge Function Aufrufe)."""
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")
    if not key:
        logger.error("SUPABASE_ANON_KEY oder SUPABASE_KEY muss gesetzt sein!")
        return None
    return key

# ============================================================================
# EDGE FUNCTION CLIENT
# ============================================================================

def call_edge_function(
    function_name: str,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Ruft eine Supabase Edge Function auf.
    
    Args:
        function_name: Name der Edge Function (z.B. 'SIMAP-Sync')
        params: Query-Parameter als Dictionary
        
    Returns:
        Response JSON als Dictionary
    """
    url = get_supabase_url()
    key = get_supabase_anon_key()
    
    if not url or not key:
        raise ValueError("SUPABASE_URL und SUPABASE_ANON_KEY müssen gesetzt sein!")
    
    edge_function_url = f"{url}/functions/v1/{function_name}"
    
    # Query-Parameter aufbauen
    if params:
        query_string = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])
        if query_string:
            edge_function_url += f"?{query_string}"
    
    logger.info(f"Rufe Edge Function auf: {edge_function_url}")
    
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }
    
    response = requests.post(edge_function_url, headers=headers, timeout=300)
    response.raise_for_status()
    
    return response.json()

# ============================================================================
# SIMAP API CLIENT
# ============================================================================

class SimapClient:
    """Client für SIMAP API."""
    
    def __init__(self, delay: float = 0.15):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'SIMAP-Tools/3.0'
        })
        self.delay = delay
    
    def get_detail(self, project_id: str, publication_id: str) -> Optional[Dict[str, Any]]:
        """Holt Details für ein Projekt."""
        url = f"{SIMAP_API_BASE}{DETAIL_ENDPOINT}/{project_id}/publication-details/{publication_id}"
        
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code in (401, 403, 404):
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"Detail-Fehler für {project_id[:8]}: {e}")
            return None

# ============================================================================
# DATEN-TRANSFORMATION
# ============================================================================

def parse_translation(obj: Any) -> Dict[str, Optional[str]]:
    """Parsed mehrsprachiges Objekt."""
    if not obj or not isinstance(obj, dict):
        return {'de': None, 'fr': None, 'it': None, 'en': None}
    return {
        'de': obj.get('de'),
        'fr': obj.get('fr'),
        'it': obj.get('it'),
        'en': obj.get('en'),
    }

def parse_address(obj: Any) -> Dict[str, Optional[str]]:
    """Parsed Adress-Objekt."""
    if not obj or not isinstance(obj, dict):
        return {'canton': None, 'city': None, 'postal_code': None, 'country': 'CH'}
    
    city = obj.get('city')
    if isinstance(city, dict):
        city = city.get('de') or city.get('fr') or city.get('it')
    
    return {
        'canton': obj.get('cantonId') or obj.get('canton'),
        'city': city,
        'postal_code': obj.get('postalCode'),
        'country': obj.get('countryId') or obj.get('country') or 'CH',
    }

def extract_cpv_code(code: Any) -> Optional[str]:
    """Extrahiert CPV-Code aus verschiedenen Formaten."""
    if not code:
        return None
    if isinstance(code, str):
        return code
    if isinstance(code, dict):
        return code.get('code')
    return None

def parse_codes_array(arr: Any, extractor=extract_cpv_code) -> List[str]:
    """Parsed Array von Codes."""
    if not isinstance(arr, list):
        return []
    return [c for c in (extractor(item) for item in arr) if c]

def enrich_with_detail(project: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    """Reichert Projekt mit Detail-Daten an."""
    procurement = detail.get('procurement', {})
    dates = detail.get('dates', {})
    
    # Description
    order_desc = parse_translation(procurement.get('orderDescription'))
    project['description_de'] = order_desc['de']
    project['description_fr'] = order_desc['fr']
    project['description_it'] = order_desc['it']
    project['description_en'] = order_desc['en']
    
    # CPV Codes
    main_cpv = extract_cpv_code(procurement.get('cpvCode'))
    cpv_codes = [main_cpv] if main_cpv else []
    cpv_codes.extend(parse_codes_array(procurement.get('additionalCpvCodes')))
    
    # Auch aus Lots sammeln
    for lot in detail.get('lots', []):
        lot_cpv = extract_cpv_code(lot.get('cpvCode'))
        if lot_cpv and lot_cpv not in cpv_codes:
            cpv_codes.append(lot_cpv)
        cpv_codes.extend([c for c in parse_codes_array(lot.get('additionalCpvCodes')) if c not in cpv_codes])
    
    project['cpv_code_main'] = main_cpv
    project['cpv_codes'] = list(set(cpv_codes))
    
    # BKP Codes
    bkp_codes = parse_codes_array(procurement.get('bkpCodes'), lambda c: c if isinstance(c, str) else c.get('code') if isinstance(c, dict) else None)
    for lot in detail.get('lots', []):
        bkp_codes.extend([c for c in parse_codes_array(lot.get('bkpCodes'), lambda c: c if isinstance(c, str) else c.get('code') if isinstance(c, dict) else None) if c not in bkp_codes])
    project['bkp_codes'] = list(set(bkp_codes))
    
    # Estimated Value
    est_val = procurement.get('estimatedValue')
    if est_val and isinstance(est_val, dict):
        project['estimated_value'] = est_val.get('amount')
        project['estimated_value_currency'] = est_val.get('currency', 'CHF')
    
    # Dates
    project['submission_deadline'] = dates.get('submissionDeadline')
    project['offer_opening_date'] = dates.get('offerOpeningDate')
    project['execution_start'] = dates.get('executionStart', '')[:10] if dates.get('executionStart') else None
    project['execution_end'] = dates.get('executionEnd', '')[:10] if dates.get('executionEnd') else None
    
    # Award Data
    if project.get('pub_type') in ('award', 'direct_award'):
        award = detail.get('award', {})
        winners = award.get('winners', [])
        
        if winners:
            winner = winners[0]
            project['winner_name'] = winner.get('vendorName')
            winner_addr = winner.get('vendorAddress', {})
            winner_city = winner_addr.get('city')
            if isinstance(winner_city, dict):
                winner_city = winner_city.get('de') or winner_city.get('fr')
            project['winner_city'] = winner_city
            project['winner_canton'] = winner_addr.get('cantonId') or winner_addr.get('canton')
        
        award_price = award.get('awardPrice', {})
        if isinstance(award_price, dict):
            project['award_amount'] = award_price.get('amount')
            project['award_currency'] = award_price.get('currency', 'CHF')
            project['award_vat_type'] = award_price.get('vatType')
        else:
            project['award_amount'] = award.get('awardAmount')
        
        project['number_of_submissions'] = award.get('numberOfOffers') or award.get('numberOfSubmissions')
        project['award_decision_date'] = award.get('awardDecisionDate', '')[:10] if award.get('awardDecisionDate') else None
    
    # Metadata
    project['raw_json_detail'] = detail
    project['detail_fetched_at'] = datetime.utcnow().isoformat()
    
    return project

# ============================================================================
# COMMANDS
# ============================================================================

def cmd_stats(supabase: 'Client'):
    """Zeigt Statistiken zur Datenbank."""
    result = supabase.table('projects').select('id', count='exact').execute()
    total = result.count or 0
    
    # Details
    result_details = supabase.table('projects').select('id', count='exact').not_.is_('detail_fetched_at', 'null').execute()
    with_details = result_details.count or 0
    
    print("\n" + "=" * 50)
    print("SIMAP DATABASE STATISTIKEN")
    print("=" * 50)
    print(f"Total Projekte:        {total:,}")
    if total > 0:
        print(f"Mit Details:           {with_details:,} ({100*with_details/total:.1f}%)")
    else:
        print(f"Mit Details:           0")
    print(f"Ohne Details:          {total - with_details:,}")
    print("=" * 50)

def cmd_export_ml(supabase: 'Client', output: str, limit: Optional[int] = None):
    """Exportiert Daten für ML Training."""
    logger.info(f"Exportiere ML-Daten nach {output}...")
    
    query = supabase.table('projects').select(
        'simap_project_id',
        'title_de',
        'description_de',
        'publication_date',
        'pub_type',
        'project_subtype',
        'process_type',
        'canton',
        'cpv_code_main',
        'cpv_codes',
        'bkp_codes',
        'award_amount',
        'estimated_value',
        'number_of_submissions'
    ).not_.is_('description_de', 'null')
    
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    
    if not result.data:
        logger.warning("Keine Daten gefunden!")
        return
    
    df = pd.DataFrame(result.data)
    
    # Output Format basierend auf Endung
    if output.endswith('.parquet'):
        df.to_parquet(output, index=False)
    elif output.endswith('.csv'):
        df.to_csv(output, index=False)
    else:
        df.to_parquet(output + '.parquet', index=False)
    
    logger.info(f"✓ {len(df)} Zeilen exportiert nach {output}")
    
    # Statistiken
    print(f"\nExport-Statistiken:")
    print(f"  Total: {len(df)}")
    print(f"  Mit Award Amount: {df['award_amount'].notna().sum()}")
    print(f"  Mit CPV Code: {df['cpv_code_main'].notna().sum()}")
    print(f"  Pub Types: {df['pub_type'].value_counts().to_dict()}")

def cmd_fill_details(supabase: 'Client', limit: int = 100, delay: float = 0.2):
    """Füllt fehlende Details für bestehende Projekte."""
    logger.info(f"Fülle Details für bis zu {limit} Projekte...")
    
    # Projekte ohne Details holen
    result = supabase.table('projects').select(
        'simap_project_id', 
        'simap_publication_id',
        'pub_type'
    ).is_('detail_fetched_at', 'null').in_('pub_type', PUB_TYPES_WITH_DETAILS).limit(limit).execute()
    
    if not result.data:
        logger.info("Keine Projekte ohne Details gefunden!")
        return
    
    projects = result.data
    logger.info(f"Gefunden: {len(projects)} Projekte ohne Details")
    
    client = SimapClient(delay=delay)
    success = 0
    errors = 0
    
    for i, project in enumerate(projects):
        pid = project['simap_project_id']
        pub_id = project['simap_publication_id']
        
        detail = client.get_detail(pid, pub_id)
        
        if detail:
            # Enrich und Update
            enriched = enrich_with_detail({'pub_type': project['pub_type']}, detail)
            
            # Nur die Detail-Felder updaten
            update_data = {
                'description_de': enriched.get('description_de'),
                'description_fr': enriched.get('description_fr'),
                'description_it': enriched.get('description_it'),
                'cpv_code_main': enriched.get('cpv_code_main'),
                'cpv_codes': enriched.get('cpv_codes', []),
                'bkp_codes': enriched.get('bkp_codes', []),
                'estimated_value': enriched.get('estimated_value'),
                'submission_deadline': enriched.get('submission_deadline'),
                'raw_json_detail': enriched.get('raw_json_detail'),
                'detail_fetched_at': enriched.get('detail_fetched_at'),
            }
            
            # Award fields
            if project['pub_type'] in ('award', 'direct_award'):
                update_data.update({
                    'winner_name': enriched.get('winner_name'),
                    'winner_city': enriched.get('winner_city'),
                    'winner_canton': enriched.get('winner_canton'),
                    'award_amount': enriched.get('award_amount'),
                    'award_currency': enriched.get('award_currency'),
                    'number_of_submissions': enriched.get('number_of_submissions'),
                    'award_decision_date': enriched.get('award_decision_date'),
                })
            
            supabase.table('projects').update(update_data).eq(
                'simap_project_id', pid
            ).eq(
                'simap_publication_id', pub_id
            ).execute()
            
            success += 1
        else:
            # Markiere als "versucht aber nicht gefunden"
            supabase.table('projects').update({
                'detail_fetched_at': datetime.utcnow().isoformat(),
                'detail_fetch_error': 'Not found or no access'
            }).eq(
                'simap_project_id', pid
            ).eq(
                'simap_publication_id', pub_id
            ).execute()
            
            errors += 1
        
        if (i + 1) % 10 == 0:
            logger.info(f"Progress: {i + 1}/{len(projects)} ({success} success, {errors} errors)")
        
        time.sleep(delay)
    
    logger.info(f"✓ Fertig: {success} Details geholt, {errors} nicht gefunden")

def cmd_full_sync(
    days_back: Optional[int] = None,
    cantons: Optional[List[str]] = None,
    refetch_details: bool = False
):
    """
    Führt einen Full Sync über die Supabase Edge Function durch.
    
    Args:
        days_back: Anzahl Tage zurück (None = 30 Tage bei full_sync)
        cantons: Liste von Kantonen (None = DEFAULT_CANTONS)
        refetch_details: Details auch für bestehende Projekte neu holen
    """
    logger.info("=" * 60)
    logger.info("FULL SYNC über Edge Function")
    logger.info("=" * 60)
    
    params = {
        'full_sync': 'true'
    }
    
    if days_back:
        params['days_back'] = str(days_back)
    
    if cantons:
        params['cantons'] = ','.join(cantons)
    else:
        params['cantons'] = ','.join(DEFAULT_CANTONS)
    
    if refetch_details:
        params['refetch_details'] = 'true'
    
    logger.info(f"Parameter: {params}")
    
    try:
        result = call_edge_function('SIMAP-Sync', params)
        
        if result.get('success'):
            stats = result.get('stats', {})
            logger.info("=" * 60)
            logger.info("✓ SYNC ERFOLGREICH")
            logger.info("=" * 60)
            logger.info(f"  Gefetched:      {stats.get('fetched', 0)}")
            logger.info(f"  Neue Projekte:  {stats.get('new_projects', 0)}")
            logger.info(f"  Aktualisiert:   {stats.get('updated_projects', 0)}")
            logger.info(f"  Details:        {stats.get('details_fetched', 0)}")
            logger.info(f"  Dauer:          {stats.get('duration_seconds', 0):.2f}s")
            logger.info("=" * 60)
        else:
            logger.error(f"Sync fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}")
            sys.exit(1)
            
    except requests.RequestException as e:
        logger.error(f"Fehler beim Aufruf der Edge Function: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}")
        sys.exit(1)

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SIMAP Database Tools v3")
    subparsers = parser.add_subparsers(dest='command', help='Verfügbare Befehle')
    
    # stats
    subparsers.add_parser('stats', help='Zeige Datenbank-Statistiken')
    
    # full-sync
    p_full_sync = subparsers.add_parser('full-sync', help='Full Sync über Edge Function')
    p_full_sync.add_argument('--days', '-d', type=int, help='Tage zurück (default: 30)')
    p_full_sync.add_argument('--cantons', nargs='+', help='Kantone (z.B. ZH BE)')
    p_full_sync.add_argument('--refetch-details', action='store_true', help='Details auch für bestehende Projekte neu holen')
    
    # export-ml
    p_export = subparsers.add_parser('export-ml', help='Exportiere Daten für ML')
    p_export.add_argument('--output', '-o', default='data/ml_training.parquet', help='Output-Datei')
    p_export.add_argument('--limit', '-l', type=int, help='Max. Zeilen')
    
    # fill-details
    p_fill = subparsers.add_parser('fill-details', help='Fülle fehlende Details')
    p_fill.add_argument('--limit', '-l', type=int, default=100, help='Max. Projekte')
    p_fill.add_argument('--delay', type=float, default=0.2, help='Delay zwischen Requests')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Full Sync benötigt keine Supabase Client
    if args.command == 'full-sync':
        cmd_full_sync(
            days_back=args.days,
            cantons=args.cantons,
            refetch_details=args.refetch_details
        )
        return
    
    # Andere Commands benötigen Supabase Client
    supabase = get_supabase_client()
    if not supabase:
        sys.exit(1)
    
    # Execute command
    if args.command == 'stats':
        cmd_stats(supabase)
    elif args.command == 'export-ml':
        cmd_export_ml(supabase, args.output, args.limit)
    elif args.command == 'fill-details':
        cmd_fill_details(supabase, args.limit, args.delay)

if __name__ == '__main__':
    main()


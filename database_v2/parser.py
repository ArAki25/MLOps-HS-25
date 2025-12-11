"""
Parser für SIMAP API Responses.

Transformiert rohe API-Daten in typisierte Pydantic Models.
Fokus auf Effizienz: Nutzt Search-Response direkt ohne Detail-Requests.
"""
from typing import Iterator, Optional
from datetime import date

from .models import Project, Translation, OrderAddress


def parse_search_response(response: dict) -> Iterator[Project]:
    """
    Parsed die /publications/v2/project/project-search Response.
    
    Die Search-Response enthält bereits alle relevanten Felder:
    - id, publicationId, projectNumber, publicationNumber
    - title (Translation), publicationDate, pubType
    - projectType, projectSubType, processType, lotsType
    - procOfficeName (Translation)
    - orderAddress (canton, city, postalCode)
    - lots[] bei lotsType='with'
    
    Args:
        response: Raw JSON Response von der API
        
    Yields:
        Project: Geparstes Projekt
    """
    for entry in response.get("projects", []):
        try:
            yield parse_project_entry(entry)
        except Exception as e:
            # Log but don't crash - ein fehlerhafter Eintrag soll nicht alles stoppen
            import logging
            logging.warning(f"Fehler beim Parsen von Projekt {entry.get('id')}: {e}")
            continue


def parse_project_entry(entry: dict) -> Project:
    """
    Parsed einen einzelnen ProjectsSearchEntry.
    
    Schema basiert auf OpenAPI Spec:
    - BaseProjectsSearchEntry
    - ProjectsSearchEntryLatestPub
    - orderAddress, procOfficeName, lots
    """
    
    # Titel extrahieren
    title = _parse_translation(entry.get("title", {}))
    
    # Proc Office Name
    proc_office_name = _parse_translation(entry.get("procOfficeName", {}))
    
    # Order Address
    order_address = _parse_order_address(entry.get("orderAddress", {}))
    
    # Publication Number (ist ein Objekt mit publicationNumber drin)
    pub_num_obj = entry.get("publicationNumber", {})
    publication_number = pub_num_obj.get("publicationNumber") if isinstance(pub_num_obj, dict) else None
    
    # Lots parsen (falls vorhanden)
    lots = entry.get("lots", [])
    
    # Bei Projekten mit Lots: Adresse aus erstem Lot nehmen falls Haupt-Adresse fehlt
    if not order_address.canton and lots:
        first_lot = lots[0]
        lot_address = first_lot.get("orderAddress", {})
        order_address = _parse_order_address(lot_address)
    
    return Project(
        simap_project_id=entry["id"],
        simap_publication_id=entry["publicationId"],
        project_number=entry.get("projectNumber"),
        publication_number=publication_number,
        title=title,
        publication_date=_parse_date(entry.get("publicationDate")),
        pub_type=entry.get("pubType", "unknown"),
        project_type=entry.get("projectType"),
        project_subtype=entry.get("projectSubType"),
        process_type=entry.get("processType"),
        lots_type=entry.get("lotsType"),
        corrected=entry.get("corrected", False),
        proc_office_name=proc_office_name,
        order_address=order_address,
        lots=lots,
        raw_json=entry,
    )


def _parse_translation(obj: dict | None) -> Translation:
    """Parsed ein Translation-Objekt."""
    if not obj or not isinstance(obj, dict):
        return Translation()
    return Translation(
        de=obj.get("de"),
        fr=obj.get("fr"),
        it=obj.get("it"),
        en=obj.get("en"),
    )


def _parse_order_address(obj: dict | None) -> OrderAddress:
    """
    Parsed ein PubProcurementAddress Objekt.
    
    Das city-Feld kann ein Translation-Objekt oder ein String sein.
    """
    if not obj or not isinstance(obj, dict):
        return OrderAddress()
    
    # City kann Translation oder String sein
    city_obj = obj.get("city")
    if isinstance(city_obj, dict):
        city = city_obj.get("de") or city_obj.get("fr") or city_obj.get("it")
    else:
        city = city_obj
    
    return OrderAddress(
        canton=obj.get("canton"),
        city=city,
        postal_code=obj.get("postalCode"),
        country=obj.get("country", "CH"),
    )


def _parse_date(date_str: str | None) -> date:
    """Parsed ISO-Datum."""
    if not date_str:
        return date.today()
    try:
        return date.fromisoformat(date_str[:10])  # Nur YYYY-MM-DD Teil
    except ValueError:
        return date.today()


def get_pagination_cursor(response: dict) -> Optional[str]:
    """
    Extrahiert den lastItem Cursor für Rolling Pagination.
    
    Format: "<date>|<projectNumber>"
    """
    pagination = response.get("pagination", {})
    return pagination.get("lastItem")


def has_more_pages(response: dict) -> bool:
    """Prüft ob weitere Seiten verfügbar sind."""
    return bool(get_pagination_cursor(response))

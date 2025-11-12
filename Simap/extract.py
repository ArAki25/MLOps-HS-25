"""
Einfache Datenextraktion aus SIMAP API-Responses.

Extrahiert die wichtigsten Felder aus verschachtelten JSON-Strukturen
und flattened sie zu einer flachen Struktur für CSV-Export.
"""
import re
from typing import Any, Dict, Optional


def _get_text(value: Any) -> Optional[str]:
    """
    Extrahiert Text aus verschiedenen Formaten.

    Unterstützt:
    - Einfache Strings
    - Mehrsprachige Dicts ({"de": "...", "fr": "...", "en": "..."})
    - HTML (entfernt Tags)
    """
    if value is None:
        return None

    if isinstance(value, str):
        # HTML-Tags entfernen
        text = re.sub(r'<[^>]+>', '', value)
        return text.strip() or None

    if isinstance(value, dict):
        # Mehrsprachige Felder - versuche DE, dann FR, dann EN
        for lang in ["de", "fr", "en"]:
            if lang in value and value[lang]:
                text = re.sub(r'<[^>]+>', '', str(value[lang]))
                text = text.strip()
                if text:
                    return text

    return None


def _get_price(price_obj: Any) -> Optional[float]:
    """Extrahiert Betrag aus Preis-Objekten."""
    if not isinstance(price_obj, dict):
        return None

    amount = price_obj.get("amount") or price_obj.get("price") or price_obj.get("value")

    if amount is None:
        return None

    try:
        return float(amount)
    except (ValueError, TypeError):
        return None


def _get_currency(price_obj: Any) -> Optional[str]:
    """Extrahiert Währung aus Preis-Objekten."""
    if not isinstance(price_obj, dict):
        return None

    currency = price_obj.get("currency") or price_obj.get("currencyCode")
    return str(currency).upper() if currency else None


def extract_project_data(project: Dict[str, Any], details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrahiert wichtigste Felder aus Projekt und Details.

    Args:
        project: Projekt-Dictionary von der Search-API
        details: Detail-Dictionary von der Details-API

    Returns:
        Flaches Dictionary mit den wichtigsten Feldern
    """
    # Basis-Informationen
    data = {
        "project_id": project.get("id"),
        "publication_id": project.get("publicationId"),
        "publication_date": project.get("publicationDate"),
        "title": _get_text(project.get("title")),
        "project_type": project.get("projectType"),
        "publication_type": project.get("pubType"),
    }

    # Zusätzliche Projektdetails
    data["project_number"] = project.get("projectNumber")
    data["publication_number"] = details.get("base", {}).get("publicationNumber")
    data["project_subtype"] = project.get("projectSubType")
    data["lots_type"] = project.get("lotsType")
    data["creation_language"] = details.get("base", {}).get("creationLanguage")

    # Beschreibung aus Details
    procurement = details.get("procurement", {})
    if isinstance(procurement, dict):
        data["description"] = _get_text(procurement.get("orderDescription"))
        data["order_type"] = procurement.get("orderType")
        data["construction_type"] = procurement.get("constructionType")
        data["construction_category"] = procurement.get("constructionCategory")

    if not data["description"]:
        data["description"] = _get_text(details.get("description"))

    # Auftraggeber
    data["contracting_authority"] = _get_text(project.get("procOfficeName"))

    # Ort (aus orderAddress)
    order_address = project.get("orderAddress", {})
    if isinstance(order_address, dict):
        data["canton"] = order_address.get("cantonId")
        data["city"] = _get_text(order_address.get("city"))
        data["postal_code"] = order_address.get("postalCode")
        data["country"] = order_address.get("countryId")

    # CPV-Code (Klassifizierung)
    if isinstance(procurement, dict):
        data["cpv_code"] = procurement.get("cpvCode")

        # Zusätzliche CPV-Codes
        additional_cpv = procurement.get("additionalCpvCodes", [])
        if additional_cpv:
            data["additional_cpv_codes"] = str(additional_cpv)

        # BKP, EBKP, NPK Codes
        bkp_codes = procurement.get("bkpCodes", [])
        if bkp_codes:
            data["bkp_codes"] = str(bkp_codes)

        ebkph_codes = procurement.get("ebkphCodes", [])
        if ebkph_codes:
            data["ebkph_codes"] = str(ebkph_codes)

        ebkpt_codes = procurement.get("ebkptCodes", [])
        if ebkpt_codes:
            data["ebkpt_codes"] = str(ebkpt_codes)

        npk_codes = procurement.get("npkCodes", [])
        if npk_codes:
            data["npk_codes"] = str(npk_codes)

    # Fristen
    dates = details.get("dates", {})
    if isinstance(dates, dict):
        data["submission_deadline"] = dates.get("offerDeadline")

    # Geschätzter Wert
    terms = details.get("terms", {})
    if isinstance(terms, dict):
        total_price = terms.get("totalPrice")
        data["estimated_amount"] = _get_price(total_price)
        data["estimated_currency"] = _get_currency(total_price)

    # Prozesstyp
    data["process_type"] = project.get("processType")

    # Award/Zuschlag-Informationen (nur bei award-Publikationen)
    decision = details.get("decision", {})
    if isinstance(decision, dict):
        # Zuschlagsdatum
        data["award_decision_date"] = decision.get("awardDecisionDate")

        # Anzahl Eingaben
        data["number_of_submissions"] = decision.get("numberOfSubmissions")

        # Gewinner-Informationen (nur erster Gewinner)
        vendors = decision.get("vendors", [])
        if vendors and isinstance(vendors, list) and len(vendors) > 0:
            winner = vendors[0]
            data["winner_name"] = winner.get("vendorName")

            # Gewinner-Adresse (ohne persönliche Daten)
            winner_address = winner.get("vendorAddress", {})
            if isinstance(winner_address, dict):
                data["winner_city"] = winner_address.get("city")
                data["winner_postal_code"] = winner_address.get("postalCode")
                data["winner_canton"] = winner_address.get("cantonId")
                data["winner_country"] = winner_address.get("countryId")

            # Zuschlagspreis
            winner_price = winner.get("price", {})
            if isinstance(winner_price, dict):
                data["award_amount"] = _get_price(winner_price)
                data["award_currency"] = _get_currency(winner_price)
                data["award_vat_type"] = winner_price.get("vatType")

    return data

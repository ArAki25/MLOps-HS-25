"""
CSV-Exporter für SIMAP-Daten.

Einfacher Exporter der Projekte von der API holt und als CSV speichert.
"""
import csv
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from .api import SimapClient, SimapApiError
from .extract import extract_project_data


def print_export_statistics(records: List[Dict[str, Any]]) -> None:
    """
    Gibt wichtige Statistiken über die exportierten Daten aus.

    Args:
        records: Liste der exportierten Projekt-Records
    """
    if not records:
        logging.warning("Keine Daten für Statistiken vorhanden.")
        return

    total = len(records)

    # Basis-Felder zählen
    with_title = sum(1 for r in records if r.get('title'))
    with_canton = sum(1 for r in records if r.get('canton'))
    with_city = sum(1 for r in records if r.get('city'))
    with_postal = sum(1 for r in records if r.get('postal_code'))

    # Award-Informationen zählen
    with_award_price = sum(1 for r in records if r.get('award_amount'))
    with_winner = sum(1 for r in records if r.get('winner_name'))
    with_submissions = sum(1 for r in records if r.get('number_of_submissions'))

    # Projektdetails zählen
    with_project_number = sum(1 for r in records if r.get('project_number'))
    with_construction_type = sum(1 for r in records if r.get('construction_type'))

    # Publikationstypen zählen
    pub_type_counts = {}
    for r in records:
        pub_type = r.get('publication_type', 'unknown')
        pub_type_counts[pub_type] = pub_type_counts.get(pub_type, 0) + 1

    # Sprachen zählen
    lang_counts = {}
    for r in records:
        lang = r.get('creation_language', 'unknown')
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    # Kantone zählen (Top 5)
    canton_counts = {}
    for r in records:
        canton = r.get('canton')
        if canton:
            canton_counts[canton] = canton_counts.get(canton, 0) + 1

    # Ausgabe
    logging.info("=" * 60)
    logging.info("EXPORT-STATISTIKEN")
    logging.info("=" * 60)
    logging.info(f"Total Projekte: {total}")
    logging.info("")

    # Publikationstypen
    logging.info("Publikationstypen:")
    for pub_type, count in sorted(pub_type_counts.items(), key=lambda x: x[1], reverse=True):
        type_name = {
            'tender': 'Ausschreibungen',
            'award': 'Zuschläge',
            'cancellation': 'Stornierungen',
            'change': 'Änderungen'
        }.get(pub_type, pub_type)
        logging.info(f"  {type_name:20s}: {count:3d} ({count/total*100:5.1f}%)")
    logging.info("")

    # Sprachen
    logging.info("Sprachen:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True):
        lang_name = {'de': 'Deutsch', 'fr': 'Französisch', 'it': 'Italienisch', 'en': 'Englisch'}.get(lang, lang)
        logging.info(f"  {lang_name:15s}: {count:3d} ({count/total*100:5.1f}%)")
    logging.info("")

    # Top Kantone
    if canton_counts:
        logging.info("Top 5 Kantone:")
        for canton, count in sorted(canton_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            logging.info(f"  {canton:5s}: {count:3d} ({count/total*100:5.1f}%)")
        logging.info("")

    logging.info("Basis-Felder:")
    logging.info(f"  Titel vorhanden:        {with_title:3d} ({with_title/total*100:5.1f}%)")
    logging.info(f"  Kanton vorhanden:       {with_canton:3d} ({with_canton/total*100:5.1f}%)")
    logging.info(f"  Stadt vorhanden:        {with_city:3d} ({with_city/total*100:5.1f}%)")
    logging.info(f"  PLZ vorhanden:          {with_postal:3d} ({with_postal/total*100:5.1f}%)")
    logging.info("")

    logging.info("Award-Informationen (Zuschläge):")
    logging.info(f"  Zuschlagspreis:         {with_award_price:3d} ({with_award_price/total*100:5.1f}%)")
    logging.info(f"  Gewinner-Name:          {with_winner:3d} ({with_winner/total*100:5.1f}%)")
    logging.info(f"  Anzahl Eingaben:        {with_submissions:3d} ({with_submissions/total*100:5.1f}%)")
    logging.info("")

    logging.info("Projektdetails:")
    logging.info(f"  Projektnummer:          {with_project_number:3d} ({with_project_number/total*100:5.1f}%)")
    logging.info(f"  Bautyp:                 {with_construction_type:3d} ({with_construction_type/total*100:5.1f}%)")
    logging.info("=" * 60)


def export_to_csv(
    output_file: str,
    days_back: int = None,
    start_date: str = None,
    max_pages: int = None,
    max_projects: int = None,
    publication_types: Optional[Union[str, List[str]]] = None,
    cantons: List[str] = None,
    languages: List[str] = None,
    process_types: List[str] = None,
    api_delay: float = 0.1
) -> None:
    """
    Exportiert SIMAP-Projekte als CSV mit optionalen Filtern.

    Args:
        output_file: Pfad zur CSV-Datei (z.B. "output/projects.csv")
        days_back: Wie viele Tage zurück (z.B. 30 für letzte 30 Tage)
        start_date: ODER genaues Startdatum als String (z.B. "2024-11-01")
                   Wenn gesetzt, wird days_back ignoriert!
        max_pages: Maximum Anzahl von API-Seiten (None = unbegrenzt)
        max_projects: Maximum Anzahl von Projekten (None = alle)
        publication_types: Filter für Publikationstypen - String oder Liste
                          (z.B. "tender" oder ["tender", "award"])
        cantons: Filter für Kantone (z.B. ["ZH", "BE", "GE"])
        languages: Filter für Sprachen (z.B. ["de", "fr", "it"])
        process_types: Filter für Prozesstypen (z.B. ["open", "selective"])
        api_delay: Wartezeit zwischen API-Requests in Sekunden (default 0.1)

    Beispiele:
        # Mit Tagen zurück (klassisch)
        export_to_csv("projects.csv", days_back=30)

        # Mit genauen Startdatum (neu)
        export_to_csv("projects.csv", start_date="2024-11-01")

        # Mit Filtern
        export_to_csv("awards.csv", start_date="2024-01-01", publication_types=["award"])
    """
    logging.info("Starte SIMAP Export...")

    # Normalisiere publication_types zu Liste
    if publication_types is not None:
        if isinstance(publication_types, str):
            publication_types = [publication_types]

    # Bestimme das Startdatum
    if start_date:
        # Nutze das übergebene Startdatum
        try:
            since = datetime.strptime(start_date, "%Y-%m-%d")
            logging.info(f"Nutze Startdatum: {start_date}")
        except ValueError:
            logging.error(f"Ungültiges Datumsformat: {start_date}. Nutze stattdessen YYYY-MM-DD!")
            raise
    elif days_back:
        # Berechne aus Tagen zurück
        since = datetime.now() - timedelta(days=days_back)
        logging.info(f"Parameter: days_back={days_back}, max_pages={max_pages}, max_projects={max_projects}")
    else:
        # Standard: 30 Tage
        days_back = 30
        since = datetime.now() - timedelta(days=days_back)
        logging.info(f"Standard: days_back=30, max_pages={max_pages}, max_projects={max_projects}")

    # Filter-Info ausgeben
    if publication_types:
        logging.info(f"Filter: Publikationstypen = {', '.join(publication_types)}")
    if cantons:
        logging.info(f"Filter: Kantone = {', '.join(cantons)}")
    if languages:
        logging.info(f"Filter: Sprachen = {', '.join(languages)}")
    if process_types:
        logging.info(f"Filter: Prozesstypen = {', '.join(process_types)}")

    # API-Client erstellen
    client = SimapClient()

    # Zeitraum berechnen
    params = {
        "newestPublicationFrom": since.strftime("%Y-%m-%d")
    }

    # API-Filter setzen (von SIMAP unterstützt)
    if cantons:
        # API unterstützt Kantone als Filter
        params["cantonId"] = ",".join(cantons)

    logging.info(f"Hole Projekte seit: {params['newestPublicationFrom']}")
    logging.info(f"API Delay: {api_delay}s zwischen Requests")

    # Daten sammeln
    records: List[Dict[str, Any]] = []
    project_count = 0
    filtered_count = 0

    try:
        for project in client.get_projects(params, max_pages=max_pages, delay=api_delay):
            project_count += 1

            # Limit prüfen
            if max_projects and len(records) >= max_projects:
                logging.info(f"Maximum von {max_projects} Projekten erreicht.")
                break

            # Filter anwenden (Post-Fetch)
            # Publikationstyp-Filter
            if publication_types:
                pub_type = project.get("pubType")
                if pub_type not in publication_types:
                    filtered_count += 1
                    continue

            # Prozesstyp-Filter
            if process_types:
                proc_type = project.get("processType")
                if proc_type not in process_types:
                    filtered_count += 1
                    continue

            # Projekt-IDs
            project_id = project.get("id")
            publication_id = project.get("publicationId")

            if not project_id or not publication_id:
                logging.warning(f"Projekt ohne IDs übersprungen: {project}")
                continue

            try:
                # Details holen
                details = client.get_project_details(project_id, publication_id)

                # Daten extrahieren
                record = extract_project_data(project, details)

                # Sprach-Filter (nach Extraktion)
                if languages:
                    creation_lang = record.get("creation_language")
                    if creation_lang not in languages:
                        filtered_count += 1
                        continue

                records.append(record)

                logging.info(f"✓ Projekt {len(records)}: {record['title'][:50] if record.get('title') else 'Ohne Titel'}")

                # Kleine Pause zwischen Requests
                time.sleep(api_delay)

            except SimapApiError as e:
                logging.error(f"✗ Fehler bei Projekt {project_id}: {e}")
                continue

    except SimapApiError as e:
        logging.error(f"API-Fehler beim Abrufen der Projekte: {e}")
        raise

    # Prüfe ob Daten vorhanden
    if not records:
        logging.warning("Keine Projekte gefunden!")
        return

    logging.info(f"Insgesamt {len(records)} Projekte gesammelt.")
    if filtered_count > 0:
        logging.info(f"{filtered_count} Projekte durch Filter ausgeschlossen.")

    # CSV schreiben
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Logische Reihenfolge der Spalten definieren
    ordered_fields = [
        # IDs
        "project_id",
        "publication_id",
        "project_number",
        "publication_number",

        # Basis-Informationen
        "title",
        "description",
        "publication_date",
        "publication_type",
        "project_type",
        "project_subtype",

        # Auftraggeber
        "contracting_authority",

        # Ort
        "canton",
        "city",
        "postal_code",
        "country",

        # Fristen & Prozess
        "submission_deadline",
        "process_type",
        "lots_type",

        # Geschätzte Preise
        "estimated_amount",
        "estimated_currency",

        # Award-Informationen (Zuschläge)
        "award_decision_date",
        "number_of_submissions",
        "winner_name",
        "winner_city",
        "winner_canton",
        "winner_postal_code",
        "winner_country",
        "award_amount",
        "award_currency",
        "award_vat_type",

        # Klassifizierungen
        "cpv_code",
        "additional_cpv_codes",
        "bkp_codes",
        "ebkph_codes",
        "ebkpt_codes",
        "npk_codes",

        # Weitere Details
        "order_type",
        "construction_type",
        "construction_category",
        "creation_language",
    ]

    # Alle tatsächlich vorhandenen Felder sammeln
    all_fields = set()
    for record in records:
        all_fields.update(record.keys())

    # Felder in definierter Reihenfolge, dann alphabetisch sortierte restliche Felder
    fieldnames = []
    for field in ordered_fields:
        if field in all_fields:
            fieldnames.append(field)
            all_fields.remove(field)

    # Restliche Felder alphabetisch anhängen (falls neue Felder hinzukommen)
    fieldnames.extend(sorted(all_fields))

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    logging.info(f"✓ CSV erfolgreich gespeichert: {output_path.absolute()}")
    logging.info(f"  - Anzahl Zeilen: {len(records)}")
    logging.info(f"  - Anzahl Spalten: {len(fieldnames)}")
    logging.info("")

    # Statistiken ausgeben
    print_export_statistics(records)

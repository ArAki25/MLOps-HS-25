"""
Label-Mappings und Code-Lookups für den Text-Builder der Tabelle public.embeddings.

Quellen:
  - cpv_de.json  : offizielles EU-CPV-2008-Vokabular (samhallskod/cpv-eu), DE/FR/IT/EN
  - bkp_de.json  : CRB Baukostenplan (CH-Standard) – Standard-Hauptpositionen
  - Rest inline  : Enums aus public.archive / public.projects (pub_type, order_type, …)

Alle Label-Funktionen liefern `None`, wenn kein sinnvolles Label gefunden wurde –
der Text-Builder entscheidet dann, ob der Rohcode eingebettet oder weggelassen wird.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# CPV
# ---------------------------------------------------------------------------

# CPV-2003 → CPV-2008 Mapping für die ~57 Legacy-Codes, die in archive-Altdaten
# auftauchen. Quelle: CPV-Regulation 213/2008 Anhang II (vereinfachte Auswahl).
# Codes, die nicht im Mapping stehen, fallen auf den Prefix-Fallback zurück.
_CPV_LEGACY_2003_TO_2008 = {
    "74000000": "79000000",  # Unternehmensdienstleistungen (Recht, Marketing, Beratung)
    "74100000": "79400000",  # Rechts- und Rechnungsberatung
    "74200000": "71000000",  # Architektur-/Ingenieurdienstleistungen
    "74220000": "71240000",  # Architekturdienstleistungen
    "74230000": "71300000",  # Ingenieurdienstleistungen
    "74231000": "71310000",
    "74231100": "71311100",
    "74231800": "71313400",  # Umweltvertraegliche Planung
    "74232200": "71321300",  # Heizung-/Luftungsplanung
    "74233000": "71322000",
    "74264000": "71520000",  # Bauueberwachung
    "74264100": "71520000",
    "74276000": "71620000",  # Technische Analyse
    "74400000": "79340000",  # Werbe- und Marketingdienste
    "74500000": "79600000",  # Personaldienstleistungen
    "74700000": "90910000",  # Reinigungsdienste
    "74710000": "79992000",
    "74730000": "90900000",
    "74740000": "90720000",
    "75000000": "75000000",  # unverändert
    "80420000": "80500000",  # Ausbildung
    "80422100": "80500000",
    "02100000": "03400000",  # Forstwirtschaftliche Erzeugnisse
    "20200000": "03410000",  # Bauholz
    "21221000": "03445000",  # Verpackungsholz
    "23111200": "09132000",
    "23121200": "09134000",
    "23123400": "09130000",
    "29500000": "42000000",  # Industrielle Maschinen
    "30240000": "30230000",  # Computer-Hardware
    "30244000": "30233000",
    "33200000": "33100000",
    "33253000": "33124000",
    "33253200": "33124200",
    "33253300": "33124300",
    "33253310": "33124310",
    "33434000": "31711200",
    "33711500": "33700000",
    "35222200": "35125300",
    "50531200": "50532200",
    "67220000": "66100000",
    "80422100": "80530000",
    "90300000": "90910000",
    "93000000": "98300000",
    "01122100": "03211300",
}

# Deutsche Divisions-Namen für rein numerische 2-stellige Fallbacks, falls
# der 8-stellige Code fehlt UND auch keine längere Übereinstimmung existiert.
_CPV_DIVISION_DE = {
    "03": "Landwirtschaftliche, fischwirtschaftliche und forstwirtschaftliche Erzeugnisse",
    "09": "Erdöl, Brennstoffe, Elektrizität und andere Energiequellen",
    "14": "Bergbauerzeugnisse, Grundmetalle und zugehörige Produkte",
    "15": "Nahrungsmittel, Getränke, Tabak und zugehörige Produkte",
    "16": "Landwirtschaftliche Maschinen",
    "18": "Bekleidung, Schuhe, Reiseartikel",
    "19": "Leder- und Textilgewebe, Kunststoff und Gummi",
    "22": "Drucksachen, Publikationen",
    "24": "Chemische Erzeugnisse",
    "30": "Büromaschinen, Datenverarbeitung, Druck- und Reproduktionsgeräte",
    "31": "Elektrische Maschinen, Geräte und Anlagen",
    "32": "Rundfunk-, Fernseh-, Nachrichten- und Informationsanlagen",
    "33": "Medizinische Geräte, Arzneimittel und Körperpflegeartikel",
    "34": "Transportmittel und Nebenprodukte",
    "35": "Sicherheits-, Rettungs- und Verteidigungsausrüstungen",
    "37": "Musikinstrumente, Sport-, Spiel-, Kunstgewerbeartikel",
    "38": "Labor-, optische und Präzisionsgeräte",
    "39": "Möbel, Ausstattung, Haushaltsgeräte, Reinigungsmittel",
    "41": "Gesammelte und gereinigte Wasser",
    "42": "Industrielle Maschinen",
    "43": "Bergbau-, Steinbruch- und Baumaschinen",
    "44": "Baukonstruktionen, Baumaterialien, Nebenprodukte",
    "45": "Bauarbeiten",
    "48": "Software und Informationssysteme",
    "50": "Reparatur- und Wartungsdienste",
    "51": "Installationsdienste (ausgenommen Software)",
    "55": "Dienstleistungen des Hotel- und Gaststättengewerbes",
    "60": "Transport- (ohne Abfall) und Logistikdienste",
    "63": "Hilfs- und Nebentätigkeiten im Verkehr, Reisebüros",
    "64": "Post- und Telekommunikationsdienste",
    "65": "Öffentliche Versorgung",
    "66": "Finanz- und Versicherungsdienstleistungen",
    "70": "Immobiliendienste",
    "71": "Dienstleistungen von Architektur-, Ingenieur- und Planungsbüros",
    "72": "IT-Dienste: Beratung, Software-Entwicklung, Internet",
    "73": "Forschung und Entwicklung",
    "75": "Dienstleistungen der öffentlichen Verwaltung, Verteidigung, Sozialversicherung",
    "76": "Erdöl- und Gasindustriedienstleistungen",
    "77": "Dienstleistungen in Land-, Forstwirtschaft, Gartenbau, Aquakultur und Imkerei",
    "79": "Unternehmensdienstleistungen: Recht, Marketing, Beratung, Personalvermittlung",
    "80": "Dienstleistungen im Bildungs- und Unterrichtswesen",
    "85": "Dienstleistungen des Gesundheits- und Sozialwesens",
    "90": "Dienstleistungen im Bereich Abwasser, Abfall, Reinigung und Umweltschutz",
    "92": "Erholung, Kultur und Sport",
    "98": "Sonstige gemeinschaftliche, soziale und persönliche Dienstleistungen",
}


@lru_cache(maxsize=1)
def _load_cpv() -> dict:
    path = _HERE / "cpv_de.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cpv_label(code: Optional[str], lang: str = "de") -> Optional[str]:
    """
    Liefert ein menschenlesbares Label für einen 8-stelligen CPV-Code.

    Fallback-Kaskade:
      1. Legacy-Mapping CPV-2003 → CPV-2008
      2. Direkter 8-stelliger Lookup
      3. Prefix-Fallback 7 → 6 → 5 → 4 → 3 (angereichert mit Suffix 0en)
      4. 2-stellige Division (aus internem Dict)
      5. None
    """
    if not code:
        return None
    code = str(code).strip()
    if not code.isdigit():
        return None

    cpv = _load_cpv()

    # (1) Legacy-Mapping
    if code in _CPV_LEGACY_2003_TO_2008:
        mapped = _CPV_LEGACY_2003_TO_2008[code]
        if mapped in cpv:
            label = cpv[mapped].get(lang) or cpv[mapped].get("de")
            if label:
                return label

    # (2) Direkter Treffer
    if code in cpv:
        return cpv[code].get(lang) or cpv[code].get("de")

    # (3) Prefix-Fallback: eigenem Code immer mit 0en auf 8 Stellen auffüllen
    for n in range(len(code) - 1, 1, -1):
        prefix = code[:n].ljust(8, "0")
        if prefix in cpv:
            return cpv[prefix].get(lang) or cpv[prefix].get("de")

    # (4) Divisionsebene
    return _CPV_DIVISION_DE.get(code[:2])


# ---------------------------------------------------------------------------
# BKP (CRB Baukostenplan)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_bkp() -> dict:
    path = _HERE / "bkp_de.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_meta", None)
    return d


def bkp_label(code: Optional[str]) -> Optional[str]:
    """
    Liefert das BKP-Label. Kaskadiert rückwärts bis zur 1-stelligen Hauptgruppe.
    Freitext-BKP-Einträge (>4 Zeichen) werden 1:1 zurückgegeben.
    """
    if not code:
        return None
    code = str(code).strip()
    if not code:
        return None

    bkp = _load_bkp()

    # Lange / nicht-numerische Einträge = Freitext (in DB vorhanden) → direkt nutzen
    if not code.isdigit() or len(code) > 4:
        return code

    if code in bkp:
        return bkp[code]
    for n in range(len(code) - 1, 0, -1):
        if code[:n] in bkp:
            return bkp[code[:n]]
    return None


# ---------------------------------------------------------------------------
# Kanton
# ---------------------------------------------------------------------------

CANTON_DE = {
    "ZH": "Zürich",       "BE": "Bern",        "LU": "Luzern",
    "UR": "Uri",          "SZ": "Schwyz",      "OW": "Obwalden",
    "NW": "Nidwalden",    "GL": "Glarus",      "ZG": "Zug",
    "FR": "Freiburg",     "SO": "Solothurn",   "BS": "Basel-Stadt",
    "BL": "Basel-Landschaft", "SH": "Schaffhausen", "AR": "Appenzell Ausserrhoden",
    "AI": "Appenzell Innerrhoden", "SG": "St. Gallen", "GR": "Graubünden",
    "AG": "Aargau",       "TG": "Thurgau",     "TI": "Tessin",
    "VD": "Waadt",        "VS": "Wallis",      "NE": "Neuenburg",
    "GE": "Genf",         "JU": "Jura",
    "CH": "Schweiz",      "FL": "Fürstentum Liechtenstein",
}


def canton_label(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return CANTON_DE.get(str(code).strip().upper())


# ---------------------------------------------------------------------------
# pub_type (Publikationstyp SIMAP)
# ---------------------------------------------------------------------------

# archive.pub_type nutzt SIMAP-Legacy-Codes OB00..OB09.
# projects.pub_type nutzt String-Labels (award, tender, abandonment, ...).
# Beide Varianten werden gemappt + semantisch aequiv. klassifiziert (AWARD/TENDER/…)
PUB_TYPE_DE = {
    # archive (SIMAP v1)
    "OB00": "Vorankündigung",
    "OB01": "Ausschreibung",
    "OB02": "Zuschlag",
    "OB03": "Vorinformation über die Verhandlung",
    "OB04": "Meldung über die Vorbereitung einer Publikation",
    "OB05": "Widerruf / Abbruch einer Ausschreibung",
    "OB06": "Berichtigung / Änderung der Ausschreibung",
    "OB07": "Berichtigung / Änderung des Zuschlags",
    "OB08": "Freihändige Vergabe",
    "OB09": "Sonstige Publikation",
    "OB10": "Wettbewerbsbekanntmachung",
    "OB11": "Wettbewerbsergebnis",
    # projects (simap.ch v2)
    "tender":                  "Ausschreibung",
    "award":                   "Zuschlag",
    "abandonment":             "Widerruf / Abbruch",
    "advance_notice":          "Vorankündigung",
    "competition":             "Wettbewerbsbekanntmachung",
    "participant_selection":   "Teilnehmerauswahl",
    "study_contract":          "Studienauftrag",
    "request_for_information": "Markterkundung (RFI)",
    "revocation":              "Widerruf einer Publikation",
}

# Generic-Kategorie pro pub_type – unabhängig vom Dialekt (OB0x vs. simap v2).
# Ermöglicht einheitliche Entscheidungen im Text-Builder ("Ist das ein Zuschlag?").
PUB_TYPE_CATEGORY = {
    "OB00": "advance_notice", "OB01": "tender",  "OB02": "award",
    "OB03": "tender",         "OB04": "other",   "OB05": "abandonment",
    "OB06": "tender",         "OB07": "award",   "OB08": "award",
    "OB09": "other",          "OB10": "competition", "OB11": "competition",
    "tender": "tender", "award": "award", "abandonment": "abandonment",
    "advance_notice": "advance_notice", "competition": "competition",
    "participant_selection": "tender", "study_contract": "study",
    "request_for_information": "rfi", "revocation": "abandonment",
}


def pub_type_label(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    key = str(code).strip()
    return PUB_TYPE_DE.get(key) or PUB_TYPE_DE.get(key.upper())


def pub_type_category(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    key = str(code).strip()
    return PUB_TYPE_CATEGORY.get(key) or PUB_TYPE_CATEGORY.get(key.upper())


# ---------------------------------------------------------------------------
# Enum-Mappings (ACHTUNG: archive und projects nutzen unterschiedliche Vokabulare!)
#
# Gemessen per SELECT DISTINCT am 2026-04-17:
#   archive.order_type:    WORKS | SERVICES | SUPPLIES | ARCHITECT | CONTEST | ENGINEER | OTHER | NOT_SPECIFIED
#   archive.process_type:  OPEN | RESTRICTED | INVITATION | OTHER
#   archive.project_type:  MUNICIPALITY | CANTON | FEDERATION | CANTON_OTHER | UTILITY | MUNICIPALITY_OTHER | FOREIGN | OTHER
#
#   projects.order_type:    construction | service | supply
#   projects.process_type:  open | selective | invitation | no_process
#   projects.project_type:  tender | competition | study_contract | request_for_information
#   projects.project_subtype: construction | service | supply | project_competition | project_study |
#                             request_for_information | overall_performance_competition |
#                             overall_performance_study | idea_study | idea_competition
#   projects.construction_category: structural_engineering | civil_engineering | not_specified
#   projects.construction_type:     execution | planning_and_execution
# ---------------------------------------------------------------------------

# Auftragstyp (wofür wird beschafft)
ORDER_TYPE_DE = {
    # archive (UPPERCASE, SIMAP-Enum)
    "WORKS":         "Bauauftrag",
    "SERVICES":      "Dienstleistungsauftrag",
    "SUPPLIES":      "Lieferauftrag",
    "ARCHITECT":     "Architekturauftrag",
    "ENGINEER":      "Ingenieurauftrag",
    "CONTEST":       "Wettbewerb / Studienauftrag",
    "OTHER":         "Sonstige Beschaffung",
    "NOT_SPECIFIED": None,  # kein semantischer Gehalt → weglassen
    # projects (lowercase, UI-Enum)
    "construction":  "Bauauftrag",
    "service":       "Dienstleistungsauftrag",
    "supply":        "Lieferauftrag",
}

# project_type hat in archive eine völlig andere Semantik als in projects:
#   archive  → wer beschafft (Auftraggeber-Kategorie)
#   projects → Form der Beschaffung (Ausschreibung vs. Wettbewerb)
# Deshalb zwei getrennte Lookups.

# archive.project_type
PROCURER_TYPE_DE = {
    "FEDERATION":          "Bundesverwaltung",
    "CANTON":              "Kantonale Verwaltung",
    "CANTON_OTHER":        "Kantonsnahe Institution",
    "MUNICIPALITY":        "Gemeindeverwaltung",
    "MUNICIPALITY_OTHER":  "Gemeindenahe Institution",
    "UTILITY":             "Öffentlicher Versorgungsbetrieb (Sektorenauftraggeber)",
    "FOREIGN":             "Ausländischer Auftraggeber",
    "OTHER":               "Sonstiger öffentlicher Auftraggeber",
}

# projects.project_type
PROJECT_TYPE_DE = {
    "tender":                  "Öffentliche Ausschreibung",
    "competition":             "Planungs- oder Ideenwettbewerb",
    "study_contract":          "Studienauftrag",
    "request_for_information": "Markterkundung (RFI)",
}

# Verfahrensart
PROCESS_TYPE_DE = {
    # archive (UPPERCASE)
    "OPEN":       "Offenes Verfahren",
    "RESTRICTED": "Selektives Verfahren",
    "INVITATION": "Einladungsverfahren",
    "OTHER":      "Sonstiges Verfahren",
    # projects (lowercase)
    "open":       "Offenes Verfahren",
    "selective":  "Selektives Verfahren",
    "invitation": "Einladungsverfahren",
    "no_process": "Freihändige Vergabe / kein formelles Verfahren",
}

PROJECT_SUBTYPE_DE = {
    "construction":                   "Bauvorhaben",
    "service":                        "Dienstleistungsvorhaben",
    "supply":                         "Lieferungsvorhaben",
    "project_competition":            "Projektwettbewerb",
    "project_study":                  "Projektstudie",
    "request_for_information":        "Markterkundung (RFI)",
    "overall_performance_competition": "Gesamtleistungswettbewerb",
    "overall_performance_study":      "Gesamtleistungsstudie",
    "idea_study":                     "Ideenstudie",
    "idea_competition":               "Ideenwettbewerb",
}

CONSTRUCTION_CATEGORY_DE = {
    "structural_engineering": "Hochbau",
    "civil_engineering":      "Tiefbau",
    "not_specified":          None,
}

CONSTRUCTION_TYPE_DE = {
    "execution":              "Ausführung (Realisierung)",
    "planning_and_execution": "Planung und Ausführung (Gesamtleistung)",
}

LANGUAGE_DE = {
    "de": "Deutsch", "DE": "Deutsch",
    "fr": "Französisch", "FR": "Französisch",
    "it": "Italienisch", "IT": "Italienisch",
    "en": "Englisch", "EN": "Englisch",
    "rm": "Rätoromanisch", "RM": "Rätoromanisch",
}


def _label_or(d: dict, code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    v = d.get(str(code).strip())
    return v if v else None


def order_type_label(code):         return _label_or(ORDER_TYPE_DE, code)
def procurer_type_label(code):      return _label_or(PROCURER_TYPE_DE, code)
def project_type_label(code):       return _label_or(PROJECT_TYPE_DE, code)
def process_type_label(code):       return _label_or(PROCESS_TYPE_DE, code)
def project_subtype_label(code):    return _label_or(PROJECT_SUBTYPE_DE, code)
def construction_category_label(c): return _label_or(CONSTRUCTION_CATEGORY_DE, c)
def construction_type_label(c):     return _label_or(CONSTRUCTION_TYPE_DE, c)
def language_label(c):              return _label_or(LANGUAGE_DE, c)

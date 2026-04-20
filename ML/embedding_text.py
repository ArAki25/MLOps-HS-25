from __future__ import annotations

import hashlib
import html
import re
from typing import Any

# ============================================================================
# Gemeinsame Embedding-Textlogik
# ============================================================================
# Wichtig:
# - Diese Datei soll von allen Embedding-Pipelines genutzt werden.
# - Wenn sich hier etwas ändert, müssen alle bereits gespeicherten Embeddings
#   per Force-Run (-f/--force-all) neu erzeugt werden.
# ============================================================================

# Label-Mappings (strukturierte Felder → deutsche Klartext-Anker)
ORDER_TYPE_LABELS: dict[str, str] = {
    "construction": "Bauauftrag",
    "WORKS": "Bauauftrag",
    "service": "Dienstleistungsauftrag",
    "SERVICES": "Dienstleistungsauftrag",
    "supply": "Lieferauftrag",
    "SUPPLIES": "Lieferauftrag",
}

# CPV-Division (erste 2 Stellen) → Klartext.
CPV_DIVISION_LABELS: dict[str, str] = {
    "03": "Landwirtschaft und Forstwirtschaft",
    "09": "Erdöl Gas Strom",
    "14": "Bergbau Steine Erze",
    "15": "Nahrungsmittel Getränke",
    "16": "Landmaschinen",
    "18": "Bekleidung Textilien",
    "19": "Leder Textilwaren",
    "22": "Druckerzeugnisse",
    "24": "Chemische Erzeugnisse",
    "30": "Büromaschinen IT-Ausstattung",
    "31": "Elektrische Maschinen Geräte",
    "32": "Nachrichten Rundfunk",
    "33": "Medizinische Geräte Arzneimittel",
    "34": "Fahrzeuge Transportausrüstung",
    "35": "Sicherheit Militär",
    "37": "Musikinstrumente Sportartikel",
    "38": "Labor Messgeräte",
    "39": "Möbel Haushalt",
    "41": "Wasseraufbereitung",
    "42": "Industrieausrüstung",
    "43": "Maschinen Bergbau Bau",
    "44": "Baustoffe Bauprodukte",
    "45": "Bauarbeiten",
    "48": "Software IT-Systeme",
    "50": "Reparatur Wartung",
    "51": "Installation",
    "55": "Hotel Gastronomie",
    "60": "Transport Logistik",
    "63": "Unterstützungsdienste Verkehr",
    "64": "Post Telekommunikation",
    "65": "Öffentliche Versorgung",
    "66": "Finanzen Versicherung",
    "70": "Immobiliendienstleistungen",
    "71": "Planung Architektur Ingenieur",
    "72": "IT-Dienstleistungen",
    "73": "Forschung Entwicklung",
    "75": "Öffentliche Verwaltung",
    "76": "Erdölindustrie-Dienste",
    "77": "Landwirtschaftsdienste",
    "79": "Unternehmensdienste Rechtsdienste",
    "80": "Bildung Ausbildung",
    "85": "Gesundheit Soziales",
    "90": "Abwasser Abfall Umwelt",
    "92": "Kultur Sport Freizeit",
    "98": "Sonstige Dienstleistungen",
}

LANG_PRIORITY: tuple[str, ...] = ("DE", "FR", "IT", "EN")

_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None, max_chars: int | None = None) -> str:
    """HTML/Whitespace-Cleanup + optionale Trunkierung (zeichenbasiert)."""
    if not text:
        return ""
    t = html.unescape(str(text))
    t = _HTML_TAG_RE.sub(" ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    if max_chars and len(t) > max_chars:
        cut = t[:max_chars]
        last_space = cut.rfind(" ")
        if last_space > max_chars * 0.8:
            cut = cut[:last_space]
        t = cut
    return t


def _cpv_division_label(cpv_code_main: str | None) -> str:
    if not cpv_code_main:
        return ""
    code = str(cpv_code_main).strip()
    if len(code) < 2:
        return ""
    return CPV_DIVISION_LABELS.get(code[:2], "")


def _pick_title_and_desc(row: dict[str, Any]) -> tuple[str, str, str]:
    """Wählt Titel + Beschreibung + Quellsprache nach LANG_PRIORITY."""
    candidates: dict[str, tuple[str, str]] = {
        "DE": (_clean(row.get("title_de")), _clean(row.get("description_de"))),
        "FR": (_clean(row.get("title_fr")), _clean(row.get("description_fr"))),
    }

    cl = (row.get("creation_language") or "").upper()
    order: list[str] = []
    if cl in candidates:
        order.append(cl)
    for l in LANG_PRIORITY:
        if l in candidates and l not in order:
            order.append(l)

    for lang in order:
        title, desc = candidates[lang]
        if title or desc:
            return title, desc, lang
    return "", "", "DE"


def build_archive_embedding_text(
    row: dict[str, Any],
    *,
    max_chars_title: int = 500,
    max_chars_description: int = 1600,
) -> tuple[str, str]:
    """Baut den Rohtext für ein Archiv-Projekt und liefert (text, source_lang).

    Struktur:
        [Auftragsart-Label]. [CPV-Division-Label]. [CPV-Main]. [Titel]. [Beschreibung]
    """
    parts: list[str] = []

    order_label = ORDER_TYPE_LABELS.get(str(row.get("order_type") or "").strip(), "")
    if order_label:
        parts.append(order_label)

    cpv_label = _cpv_division_label(row.get("cpv_code_main"))
    if cpv_label:
        parts.append(cpv_label)

    cpv_main = str(row.get("cpv_code_main") or "").strip()
    if cpv_main and len(cpv_main) >= 4:
        parts.append(f"CPV {cpv_main}")

    title, desc, lang = _pick_title_and_desc(row)
    title = _clean(title, max_chars_title)
    desc = _clean(desc, max_chars_description)
    if title:
        parts.append(title)
    if desc:
        parts.append(desc)

    text = ". ".join(p for p in parts if p).strip()
    return (text, lang) if text else ("", lang)


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


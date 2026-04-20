"""
Text-Builder für die unified Tabelle public.embeddings.

Nimmt eine Row aus `public.archive` oder `public.projects` (Schemas sind praktisch
identisch) und erzeugt einen stabilen, menschenlesbaren Rohtext, der anschliessend
von BAAI/bge-m3 eingebettet wird.

Design-Prinzipien:
  * pub_type-bewusst: leere/unsinnige Blöcke werden ausgelassen statt mit None
    gefüllt, damit der Embedding-Vektor nicht durch Boilerplate verwässert wird.
  * Keine 800-char-Beschränkung mehr (bge-m3 erlaubt 8192 Tokens).
  * Kein "passage: "-Prefix (bge-m3 braucht keinen).
  * Spracheauswahl-Kaskade DE > FR > IT > EN.
  * HTML wird gestrippt, Whitespace normalisiert.
  * Output ist deterministisch → MD5-Hash als Invalidations-Schlüssel.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .dicts import (
    bkp_label,
    canton_label,
    construction_category_label,
    construction_type_label,
    cpv_label,
    order_type_label,
    procurer_type_label,
    process_type_label,
    project_subtype_label,
    project_type_label,
    pub_type_category,
    pub_type_label,
)

# Kategorien (dialektneutral), bei denen Winner/Award-Infos semantisch relevant sind.
_AWARD_CATEGORIES = {"award"}


# ---------------------------------------------------------------------------
# Text-Hygiene
# ---------------------------------------------------------------------------

_HTML_TAG_RE  = re.compile(r"<[^>]+>")
_WS_RE        = re.compile(r"[ \t\u00a0\u200b]+")
_MULTI_NL_RE  = re.compile(r"\n{3,}")


def _clean(text: Optional[str]) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _nonempty(*values: Optional[str]) -> Optional[str]:
    """Erste nichtleere, bereinigte Zeichenkette (Spracheauswahl-Kaskade)."""
    for v in values:
        c = _clean(v)
        if c:
            return c
    return None


def _join(parts: Iterable[Optional[str]], sep: str = ". ") -> str:
    return sep.join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Blöcke
# ---------------------------------------------------------------------------


def _block_type(row: dict) -> Optional[str]:
    """Block A — Publikations-/Auftragstyp."""
    parts = [
        pub_type_label(row.get("pub_type")),
        order_type_label(row.get("order_type")),
        # project_type hat in archive/projects unterschiedliche Semantik.
        # Versuche zuerst den Beschaffungsform-Lookup (projects), dann den
        # Auftraggeber-Typ (archive). Beide Dicts sind disjoint, deshalb greift
        # immer höchstens einer.
        project_type_label(row.get("project_type"))
            or procurer_type_label(row.get("project_type")),
        process_type_label(row.get("process_type")),
        project_subtype_label(row.get("project_subtype")),
        construction_category_label(row.get("construction_category")),
        construction_type_label(row.get("construction_type")),
    ]
    text = _join(parts, sep=". ")
    if not text:
        return None
    return f"Publikation: {text}."


def _block_geo(row: dict) -> Optional[str]:
    canton = canton_label(row.get("canton"))
    city   = _clean(row.get("city"))
    country = _clean(row.get("country"))
    loc_parts = []
    if canton:
        loc_parts.append(canton)
    if city:
        loc_parts.append(city)
    if country and country.upper() not in {"CH", "SUI", "SWITZERLAND", "SCHWEIZ"}:
        loc_parts.append(country)
    if not loc_parts:
        return None
    return "Standort: " + ", ".join(loc_parts) + "."


def _block_procurement_office(row: dict) -> Optional[str]:
    name = _nonempty(
        row.get("proc_office_name_de"),
        row.get("proc_office_name_fr"),
        row.get("proc_office_name_it"),
        row.get("proc_office_name_en"),
    )
    if not name:
        return None
    city = _clean(row.get("proc_office_city"))
    canton = canton_label(row.get("proc_office_canton"))
    extras = [x for x in [city, canton] if x]
    if extras:
        return f"Beschaffungsstelle: {name} ({', '.join(extras)})."
    return f"Beschaffungsstelle: {name}."


def _iter_cpv_codes(row: dict) -> Iterable[str]:
    """Hauptcode zuerst, dann Sekundärcodes (dedupliziert, Reihenfolge erhalten)."""
    seen: set = set()
    main = row.get("cpv_code_main")
    if main:
        code = str(main).strip()
        if code and code not in seen:
            seen.add(code)
            yield code
    for c in (row.get("cpv_codes") or []):
        code = str(c).strip()
        if code and code not in seen:
            seen.add(code)
            yield code


def _iter_bkp_codes(row: dict) -> Iterable[str]:
    seen: set = set()
    for c in (row.get("bkp_codes") or []):
        code = str(c).strip()
        if code and code not in seen:
            seen.add(code)
            yield code


def _block_codes(row: dict) -> Optional[str]:
    cpv_labels = []
    for code in _iter_cpv_codes(row):
        lab = cpv_label(code)
        cpv_labels.append(f"{code} {lab}" if lab else f"CPV {code}")

    bkp_labels = []
    for code in _iter_bkp_codes(row):
        lab = bkp_label(code)
        bkp_labels.append(f"BKP {code} {lab}" if lab else f"BKP {code}")

    parts = []
    if cpv_labels:
        parts.append("Branchen/CPV: " + "; ".join(cpv_labels) + ".")
    if bkp_labels:
        parts.append("Bau-Kostengruppen (BKP): " + "; ".join(bkp_labels) + ".")
    if not parts:
        return None
    return " ".join(parts)


def _block_content(row: dict) -> Optional[str]:
    title = _nonempty(
        row.get("title_de"),
        row.get("title_fr"),
        row.get("title_it"),
        row.get("title_en"),
    )
    desc = _nonempty(
        row.get("description_de"),
        row.get("description_fr"),
        row.get("description_it"),
        row.get("description_en"),
    )
    parts = []
    if title:
        parts.append(f"Titel: {title}.")
    if desc:
        parts.append(f"Beschreibung: {desc}")
    return " ".join(parts) if parts else None


def _block_award(row: dict) -> Optional[str]:
    if pub_type_category(row.get("pub_type")) not in _AWARD_CATEGORIES:
        return None

    winner_name = _clean(row.get("winner_name"))
    winner_city = _clean(row.get("winner_city"))
    winner_canton = canton_label(row.get("winner_canton"))

    award_justification = _nonempty(
        row.get("award_justification_de"),
        row.get("award_justification_fr"),
    )

    all_winners_text: Optional[str] = None
    all_winners = row.get("all_winners")
    if isinstance(all_winners, list) and len(all_winners) > 1:
        extra = []
        for w in all_winners[:10]:
            if not isinstance(w, dict):
                continue
            nm = _clean(w.get("name") or w.get("winner_name"))
            ct = _clean(w.get("city") or w.get("winner_city"))
            if nm and nm != winner_name:
                extra.append(f"{nm}" + (f" ({ct})" if ct else ""))
        if extra:
            all_winners_text = "Weitere Zuschlagsempfänger: " + ", ".join(extra) + "."

    parts = []
    if winner_name:
        loc = ", ".join(x for x in [winner_city, winner_canton] if x)
        parts.append(f"Zuschlag an: {winner_name}" + (f" ({loc})" if loc else "") + ".")
    if all_winners_text:
        parts.append(all_winners_text)
    if award_justification:
        parts.append(f"Begründung: {award_justification}")

    return " ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Sprache ableiten (nur fürs Monitoring, nicht für Einbettung)
# ---------------------------------------------------------------------------

def _detect_language(row: dict) -> str:
    # 1) explizites Feld
    cl = (row.get("creation_language") or "").strip().lower()
    if cl in {"de", "fr", "it", "en", "rm"}:
        return cl
    # 2) welcher title/description ist gesetzt?
    for l in ("de", "fr", "it", "en"):
        if _clean(row.get(f"title_{l}")) or _clean(row.get(f"description_{l}")):
            return l
    return "de"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class BuiltText:
    raw_text: str
    text_hash: str
    language: str

    @property
    def preview(self) -> str:
        return self.raw_text[:500]


def build_text(row: dict, source: str) -> BuiltText:
    """
    Baut den Rohtext für eine archive- oder projects-Row.
    `source` ∈ {'archive','project'}.
    """
    if source not in ("archive", "project"):
        raise ValueError(f"unknown source: {source}")

    blocks = [
        _block_type(row),
        _block_geo(row),
        _block_procurement_office(row),
        _block_codes(row),
        _block_content(row),
        _block_award(row),
    ]
    raw_text = "\n".join(b for b in blocks if b).strip()

    # Fallback für (theoretisch) komplett leere Rows: wenigstens IDs einbetten,
    # damit der Hash stabil != '' ist und das Embedding nicht kollabiert.
    if not raw_text:
        ident = row.get("simap_publication_id") or row.get("id") or ""
        raw_text = f"SIMAP-Publikation {ident}".strip()

    h = hashlib.md5(raw_text.encode("utf-8")).hexdigest()
    return BuiltText(raw_text=raw_text, text_hash=h, language=_detect_language(row))

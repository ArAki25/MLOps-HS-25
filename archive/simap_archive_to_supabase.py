#!/usr/bin/env python3
"""
SIMAP Archive → Supabase "archive" table.

Einmaliges Migrations-Skript: Alle ~275k Publikationen aus archiv.simap.ch
in die Supabase-Tabelle "archive" laden – Schema analog zu "projects".

Phase 1 – Search-Scan:
    Paginiert /search aufrufen → Basisdaten + raw_json_search upserten
    (~275 Seiten à 1000 Einträge, dauert ~3 Min)

Phase 2 – Detail-Enrichment:
    Für jede Publikation /detail holen → Felder extrahieren + raw_json_detail
    (parallel mit 20 Workers, dauert ~1-2 Stunden)

Usage:
    export SUPABASE_URL=https://rkfwuxocuojkjswigoss.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
    python3 simap_archive_to_supabase.py               # beide Phasen
    python3 simap_archive_to_supabase.py --phase 1      # nur Search
    python3 simap_archive_to_supabase.py --phase 2      # nur Details (Resume)
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════
SIMAP_BASE = "https://archiv.simap.ch/api"
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://rkfwuxocuojkjswigoss.supabase.co"
)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

SEARCH_PAGE_SIZE = 1000
UPSERT_BATCH = 400
DETAIL_WORKERS = 20
DETAIL_UPDATE_BATCH = 200

DATE_FROM = "2005-01-01"
DATE_TO = "2026-12-31"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("simap")


# ═══════════════════════════════════════════════════════════════════
# Supabase REST helpers
# ═══════════════════════════════════════════════════════════════════
def _sb_headers(prefer: str = "") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        **({"Prefer": prefer} if prefer else {}),
    }


def sb_upsert(rows: list[dict]) -> None:
    """Upsert into archive via PostgREST (merge on simap_publication_id).

    PostgREST requires every object in a batch to have identical keys.
    We strip None values first (avoids overwriting NOT-NULL columns),
    then group rows by key-set so each group is homogeneous.
    """
    if not rows:
        return
    from collections import defaultdict

    groups: dict[frozenset, list[dict]] = defaultdict(list)
    for row in rows:
        clean = {k: v for k, v in row.items() if v is not None}
        groups[frozenset(clean.keys())].append(clean)

    url = f"{SUPABASE_URL}/rest/v1/archive?on_conflict=simap_publication_id"
    for _keyset, group in groups.items():
        resp = requests.post(
            url,
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            json=group,
            timeout=120,
        )
        if resp.status_code not in (200, 201):
            log.error("Upsert %d: %s", resp.status_code, resp.text[:800])
            raise RuntimeError(f"Upsert failed ({resp.status_code})")


def sb_select_pending_detail(limit: int = 2000) -> list[dict]:
    """Return records that still need detail fetching, including NOT-NULL cols."""
    url = (
        f"{SUPABASE_URL}/rest/v1/archive"
        f"?select=simap_publication_id,simap_project_id,publication_date,pub_type"
        f"&detail_fetched_at=is.null"
        f"&order=simap_publication_id.asc"
        f"&limit={limit}"
    )
    resp = requests.get(url, headers=_sb_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


def sb_count_total() -> int:
    url = (
        f"{SUPABASE_URL}/rest/v1/archive"
        f"?select=simap_publication_id"
    )
    resp = requests.head(
        url,
        headers={**_sb_headers(), "Prefer": "count=exact"},
        timeout=30,
    )
    cr = resp.headers.get("content-range", "")
    # format: "0-N/TOTAL"  or "*/TOTAL"
    if "/" in cr:
        return int(cr.split("/")[1])
    return 0


def sb_count_enriched_pending() -> tuple[int, int]:
    """Return (enriched, pending) counts for the archive table."""
    url = f"{SUPABASE_URL}/rest/v1/archive?select=detail_fetched_at"
    resp = requests.head(
        url,
        headers={**_sb_headers(), "Prefer": "count=exact"},
        timeout=30,
    )
    cr = resp.headers.get("content-range", "")
    total = int(cr.split("/")[1]) if "/" in cr else 0

    # Count enriched only (detail_fetched_at NOT NULL)
    url2 = (
        f"{SUPABASE_URL}/rest/v1/archive"
        f"?select=detail_fetched_at&detail_fetched_at=not.is.null"
    )
    resp2 = requests.head(
        url2,
        headers={**_sb_headers(), "Prefer": "count=exact"},
        timeout=30,
    )
    cr2 = resp2.headers.get("content-range", "")
    enriched = int(cr2.split("/")[1]) if "/" in cr2 else 0
    return enriched, max(0, total - enriched)


# ═══════════════════════════════════════════════════════════════════
# SIMAP API helpers
# ═══════════════════════════════════════════════════════════════════
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=25, pool_maxsize=25, max_retries=0
)
_session = requests.Session()
_session.headers.update({"Accept": "application/json"})
_session.mount("https://", _adapter)


def simap_search(page: int) -> dict:
    for attempt in range(3):
        try:
            r = _session.post(
                f"{SIMAP_BASE}/search",
                params={
                    "pageNo": page,
                    "recordsPerPage": SEARCH_PAGE_SIZE,
                    "sort": "DATUM",
                    "sortOrder": "ASC",
                },
                json={"stat_tm_1": DATE_FROM, "stat_tm_2": DATE_TO},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("Search page %d attempt %d: %s", page, attempt + 1, e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Search page {page} failed after 3 attempts")


def simap_detail(mid: int) -> dict | None:
    for attempt in range(3):
        try:
            r = _session.get(
                f"{SIMAP_BASE}/detail",
                params={"meldungsnummer": mid},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                log.warning("Detail %d failed: %s", mid, e)
                return None
            time.sleep(1)
    return None


# ═══════════════════════════════════════════════════════════════════
# Parsing helpers
# ═══════════════════════════════════════════════════════════════════
def _g(d, *keys, default=None):
    """Safe nested dict access; treats empty strings as None."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d if d not in ("", None) else default


def _parse_chf(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace("\u2019", "").replace("'", "").replace("'", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_dmy(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _find_ob(detail: dict) -> tuple[str, dict]:
    for k, v in detail.items():
        if k.startswith("OB") and isinstance(v, dict):
            return k, v
    return "", {}


def _contract_block(ob_type: str, ob: dict) -> dict:
    spec = ob.get(f"{ob_type}.SPEC", {})
    contract = spec.get(f"{ob_type}.CONTRACT", {})
    for sub in (
        "CONT.SERVICES", "CONT.SUPPLIES", "CONT.WORKS", "CONT.CONTEST",
        f"{ob_type}.CONT.OBJ",
    ):
        block = contract.get(sub, {})
        if isinstance(block, dict) and block:
            return block
    return contract


def _cpv_list(block: dict) -> list[str]:
    cl = _g(block, "CONT.CPV.LIST", default={})
    if not cl or not isinstance(cl, dict):
        return []
    items = cl.get("CONT.CPV", [])
    if isinstance(items, dict):
        items = [items]
    return [i["CODE"] for i in items if isinstance(i, dict) and i.get("CODE")]


def _bkp_list(block: dict) -> list[str]:
    cl = _g(block, "CONT.BKP.LIST", default={})
    if not cl or not isinstance(cl, dict):
        return []
    items = cl.get("CONT.BKP", [])
    if isinstance(items, dict):
        items = [items]
    return [i["CODE"] for i in items if isinstance(i, dict) and i.get("CODE")]


def _contractors(ob_type: str, ob: dict) -> list[dict]:
    award = _g(ob, f"{ob_type}.SPEC", f"{ob_type}.AWARD", default={})
    if not isinstance(award, dict):
        return []
    cl = award.get("PRIM.CONTRACTOR.LIST", {})
    if not isinstance(cl, dict):
        return []
    cs = cl.get("PRIM.CONTRACTOR", [])
    return [cs] if isinstance(cs, dict) else (cs if isinstance(cs, list) else [])


# ═══════════════════════════════════════════════════════════════════
# Row mapping
# ═══════════════════════════════════════════════════════════════════
def map_search(pub: dict) -> dict:
    lang = (pub.get("lang") or "DE").upper()
    cpv_raw = pub.get("cpv") or ""
    cpvs = [c.strip() for c in cpv_raw.split(",") if c.strip()]
    bkp_raw = pub.get("bkp") or ""
    bkps = [c.strip() for c in bkp_raw.split(",") if c.strip()]
    lots = pub.get("lot") or []

    row: dict = {
        "simap_project_id": str(pub["projectid"]),
        "simap_publication_id": str(pub["id"]),
        "publication_date": pub.get("publicationDate"),
        "pub_type": pub.get("type"),
        "order_type": pub.get("contType"),
        "process_type": pub.get("proc"),
        "creation_language": lang,
        "cpv_code_main": cpvs[0] if cpvs else None,
        "cpv_codes": cpvs or [],
        "bkp_codes": bkps or [],
        "lots_count": len(lots),
        "raw_json_search": pub,
    }

    desc = pub.get("description")
    auth = pub.get("authName")
    if lang == "FR":
        row["title_fr"] = desc
        row["proc_office_name_fr"] = auth
    else:
        row["title_de"] = desc
        row["proc_office_name_de"] = auth

    dl = pub.get("deadline")
    if dl:
        row["submission_deadline"] = f"{dl}T23:59:59+02:00"

    row["city"] = pub.get("contLoc")
    return row


def map_detail(detail: dict) -> dict:
    """Extract structured fields from the /detail response."""
    ob_type, ob = _find_ob(detail)
    if not ob_type:
        return {"detail_fetch_error": "no_ob_block"}

    contract = _contract_block(ob_type, ob)
    auth_contact = _g(ob, "AUTHORITY", "AUTH.CONTACT", default={})
    auth_addr = auth_contact.get("ADDRESS", {}) if isinstance(auth_contact, dict) else {}
    auth_type_block = _g(ob, "AUTHORITY", "AUTH.TYPE", default={})
    lang = (detail.get("LANG") or "DE").upper()

    f: dict = {}

    # ── Titel & Beschreibung ──
    name = _g(contract, "CONT.NAME")
    descr = _g(contract, "CONT.DESCR")
    if lang == "FR":
        if name:
            f["title_fr"] = name
        if descr:
            f["description_fr"] = descr
    else:
        if name:
            f["title_de"] = name
        if descr:
            f["description_de"] = descr

    # ── Beschaffungsstelle ──
    aname = _g(auth_contact, "AUTH.NAME")
    if aname:
        if lang == "FR":
            f["proc_office_name_fr"] = aname
        else:
            f["proc_office_name_de"] = aname

    f["proc_office_contact"] = _g(auth_addr, "CO")
    f["proc_office_street"] = _g(auth_addr, "STREET")
    f["proc_office_city"] = _g(auth_addr, "CITY")
    f["proc_office_postal_code"] = _g(auth_addr, "ZIPCODE")
    f["proc_office_canton"] = _g(auth_contact, "AUTH.CANTONCODE")
    f["proc_office_country"] = _g(auth_addr, "COUNTRY")
    f["proc_office_email"] = _g(auth_addr, "EMAIL")
    f["proc_office_phone"] = _g(auth_addr, "PHONE")
    f["canton"] = _g(auth_contact, "AUTH.CANTONCODE")

    # ── Ort ──
    loc = _g(contract, "CONT.LOC")
    if loc:
        f["city"] = loc

    # ── CPV / BKP ──
    cpvs = _cpv_list(contract)
    if cpvs:
        f["cpv_codes"] = cpvs
        f["cpv_code_main"] = cpvs[0]
    bkps = _bkp_list(contract)
    if bkps:
        f["bkp_codes"] = bkps

    # ── Typ / Verfahren ──
    ct = _g(contract, "CONT.TYPE")
    if isinstance(ct, dict):
        f["order_type"] = ct.get("TYPE")

    wto = _g(ob, "OB.WTO", "VALUE")
    f["publication_ted"] = wto == "YES"

    ted = _g(ob, "TED.EXPORT", "VALUE")
    if ted == "YES":
        f["publication_ted"] = True

    proc = _g(ob, "OB.PROC", "VALUE")
    if proc:
        f["process_type"] = proc

    at_val = _g(auth_type_block, "VALUE") if isinstance(auth_type_block, dict) else None
    if at_val:
        f["project_type"] = at_val

    # ── Zuschlag (OB02/OB08) ──
    if ob_type in ("OB02", "OB08"):
        cs = _contractors(ob_type, ob)
        spec = ob.get(f"{ob_type}.SPEC", {})
        info = spec.get(f"{ob_type}.INFORMATION", {}) if isinstance(spec, dict) else {}

        if cs:
            first = cs[0]
            f["winner_name"] = _g(first, "CONTRACTOR.NAME")
            f["winner_id"] = _g(first, "CONTRACTOR.COMPANYID")
            wa = first.get("ADDRESS", {})
            if isinstance(wa, dict):
                f["winner_street"] = _g(wa, "STREET")
                f["winner_city"] = _g(wa, "CITY")
                f["winner_postal_code"] = _g(wa, "ZIPCODE")

            price = first.get("CONTRACTOR.PRICE", {})
            if isinstance(price, dict):
                f["award_amount"] = _parse_chf(
                    _g(price, "CONTRACTOR.PRICE.FROM")
                )
                f["award_currency"] = _g(price, "CURRENCY") or "CHF"
                f["award_vat_type"] = _g(price, "VAT")

            f["all_winners"] = [
                {
                    "name": _g(c, "CONTRACTOR.NAME"),
                    "company_id": _g(c, "CONTRACTOR.COMPANYID"),
                    "city": _g(c, "ADDRESS", "CITY"),
                    "amount": _parse_chf(
                        _g(c, "CONTRACTOR.PRICE", "CONTRACTOR.PRICE.FROM")
                    ),
                    "currency": _g(c, "CONTRACTOR.PRICE", "CURRENCY"),
                }
                for c in cs
            ]

        n_offers = _g(info, f"{ob_type}.INFO.NUMBER.OFFERS")
        if n_offers:
            try:
                f["number_of_submissions"] = int(n_offers)
            except (ValueError, TypeError):
                pass

        f["award_decision_date"] = _parse_dmy(
            _g(info, f"{ob_type}.INFO.AWARD.DATE")
        )

        award_block = spec.get(f"{ob_type}.AWARD", {}) if isinstance(spec, dict) else {}
        f["award_justification_de"] = _g(
            award_block, f"{ob_type}.AWARD.REASON"
        )
        f["remedies_notice_de"] = _g(info, f"{ob_type}.INFO.LEGAL")

    # ── Deadline (OB00/OB01/OB05/OB07) ──
    if ob_type in ("OB00", "OB01", "OB05", "OB07"):
        spec = ob.get(f"{ob_type}.SPEC", {})
        conds = spec.get(f"{ob_type}.CONDITIONS", {}) if isinstance(spec, dict) else {}
        dl_block = conds.get(f"{ob_type}.COND.SEND.DEADLINE", {})
        if isinstance(dl_block, dict):
            dl_date = _g(dl_block, f"{ob_type}.COND.SEND.DEADLINE.DATE")
            dl_hour = _g(dl_block, f"{ob_type}.COND.SEND.DEADLINE.HOUR")
            d = _parse_dmy(dl_date)
            if d:
                h = dl_hour or "23:59"
                f["submission_deadline"] = f"{d}T{h}:00+02:00"

    # ── Lots ──
    if ob_type in ("OB02", "OB08"):
        spec = ob.get(f"{ob_type}.SPEC", {})
        cont = spec.get(f"{ob_type}.CONTRACT", {}) if isinstance(spec, dict) else {}
        lot_block = cont.get(f"{ob_type}.CONT.LOT", {})
        if isinstance(lot_block, dict) and lot_block:
            kind = lot_block.get("KIND")
            if kind:
                f["lots_type"] = kind

    return {k: v for k, v in f.items() if v is not None}


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Search-Scan
# ═══════════════════════════════════════════════════════════════════
def phase1():
    log.info("═══ Phase 1: Search-Scan ═══")
    first = simap_search(1)
    total = first["total"]
    total_pages = -(-total // SEARCH_PAGE_SIZE)  # ceil division
    log.info("Gesamt: %d Publikationen  →  %d Seiten", total, total_pages)

    buf: list[dict] = []
    upserted = 0

    def flush():
        nonlocal buf, upserted
        if not buf:
            return
        sb_upsert(buf)
        upserted += len(buf)
        buf = []

    for page in range(1, total_pages + 1):
        data = first if page == 1 else simap_search(page)
        pubs = data.get("publication", [])
        for p in pubs:
            buf.append(map_search(p))
            if len(buf) >= UPSERT_BATCH:
                flush()
                log.info(
                    "  Seite %d/%d  |  %d / %d upserted",
                    page, total_pages, upserted, total,
                )
        if page > 1 and page % 20 == 0:
            time.sleep(0.2)

    flush()
    log.info("Phase 1 fertig: %d Publikationen geladen.", upserted)
    return upserted


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Detail-Enrichment
# ═══════════════════════════════════════════════════════════════════
def phase2():
    log.info("═══ Phase 2: Detail-Enrichment ═══")

    total_ok = 0
    total_err = 0
    round_nr = 0
    t0 = time.time()
    last_progress_log_at = 0.0
    last_progress_enriched = None
    last_progress_ts = None

    while True:
        pending = sb_select_pending_detail(limit=2000)
        if not pending:
            break
        round_nr += 1
        first_id = pending[0]["simap_publication_id"]
        log.info(
            "Runde %d: %d Details abrufen (ab ID %s)…",
            round_nr, len(pending), first_id,
        )

        # Build lookup for NOT-NULL base fields
        base_lookup = {
            r["simap_publication_id"]: r for r in pending
        }

        updates: list[dict] = []

        def _fetch(rec: dict) -> dict:
            mid = int(rec["simap_publication_id"])
            now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ")

            # Always carry the NOT-NULL columns from the existing row
            base = {
                "simap_publication_id": rec["simap_publication_id"],
                "simap_project_id": rec["simap_project_id"],
                "publication_date": rec["publication_date"],
                "pub_type": rec["pub_type"],
            }

            detail = simap_detail(mid)
            if detail is None:
                return {
                    **base,
                    "detail_fetch_error": "fetch_failed",
                    "detail_fetched_at": now,
                    "updated_at": now,
                }
            fields = map_detail(detail)
            fields.update(base)
            fields["raw_json_detail"] = detail
            fields["detail_fetched_at"] = now
            fields["updated_at"] = now
            fields["content_hash"] = hashlib.md5(
                json.dumps(detail, sort_keys=True).encode()
            ).hexdigest()
            return fields

        def _safe_upsert(batch: list[dict]):
            nonlocal total_ok, total_err
            try:
                sb_upsert(batch)
                total_ok += len(batch)
            except Exception:
                log.warning("Batch-Upsert fehlgeschlagen, versuche Einzel-Upsert…")
                for row in batch:
                    try:
                        sb_upsert([row])
                        total_ok += 1
                    except Exception as e2:
                        total_err += 1
                        log.error(
                            "  Einzel-Upsert %s: %s",
                            row.get("simap_publication_id"), str(e2)[:200],
                        )

        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            futs = {pool.submit(_fetch, rec): rec for rec in pending}
            for fut in as_completed(futs):
                try:
                    updates.append(fut.result())
                except Exception as exc:
                    total_err += 1
                    rec = futs[fut]
                    log.error(
                        "Detail %s exception: %s",
                        rec.get("simap_publication_id"), exc,
                    )

                if len(updates) >= DETAIL_UPDATE_BATCH:
                    _safe_upsert(updates[:DETAIL_UPDATE_BATCH])
                    updates = updates[DETAIL_UPDATE_BATCH:]
                    log.info("  OK: %d  |  Fehler: %d", total_ok, total_err)

                    # Global progress snapshot every ~60s
                    now_s = time.time()
                    if now_s - last_progress_log_at >= 60:
                        enriched, pending_cnt = sb_count_enriched_pending()
                        total = enriched + pending_cnt
                        if last_progress_enriched is None or last_progress_ts is None:
                            rate = 0.0
                        else:
                            dt = max(1.0, now_s - last_progress_ts)
                            rate = max(0.0, (enriched - last_progress_enriched) / dt)  # rows/sec
                        eta_s = (pending_cnt / rate) if rate > 0 else float("inf")
                        eta_min = int(eta_s // 60) if eta_s != float("inf") else -1
                        log.info(
                            "  Fortschritt: %d/%d enriched (%.2f%%) | pending=%d | ETA≈%d min | rate=%.1f rows/s",
                            enriched,
                            total,
                            (enriched / total * 100.0) if total else 0.0,
                            pending_cnt,
                            eta_min,
                            rate,
                        )
                        last_progress_log_at = now_s
                        last_progress_enriched = enriched
                        last_progress_ts = now_s

        if updates:
            _safe_upsert(updates)

        log.info(
            "Runde %d fertig  |  OK: %d  |  Fehler: %d",
            round_nr, total_ok, total_err,
        )

    log.info("Phase 2 fertig: %d Details, %d Fehler.", total_ok, total_err)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    if not SUPABASE_KEY:
        print(
            "SUPABASE_SERVICE_ROLE_KEY nicht gesetzt.\n"
            "  export SUPABASE_SERVICE_ROLE_KEY=<your-key>",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="SIMAP Archive → Supabase")
    parser.add_argument(
        "--phase", type=int, choices=[1, 2], default=None,
        help="Nur Phase 1 (Search) oder Phase 2 (Details) ausführen",
    )
    args = parser.parse_args()

    log.info("╔══════════════════════════════════════════════╗")
    log.info("║  SIMAP Archive → Supabase 'archive' Table   ║")
    log.info("╚══════════════════════════════════════════════╝")
    log.info("SIMAP API:   %s", SIMAP_BASE)
    log.info("Supabase:    %s", SUPABASE_URL)

    t0 = time.time()

    if args.phase in (None, 1):
        phase1()

    if args.phase in (None, 2):
        phase2()

    elapsed = time.time() - t0
    log.info("═══ Fertig in %.1f Minuten ═══", elapsed / 60)


if __name__ == "__main__":
    main()

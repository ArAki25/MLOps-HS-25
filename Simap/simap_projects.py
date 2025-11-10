"""
Fetch selected SIMAP publication fields tailored for training a classification model.

The script queries the public project search endpoint, enriches each project with
publication details, and exports the aggregated data to a CSV file.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import requests
from requests import Response, Session


BASE_URL = "https://www.simap.ch/api"
SEARCH_ENDPOINT = "/publications/v2/project/project-search"
DETAIL_ENDPOINT = "/publications/v1/project/{project_id}/publication-details/{publication_id}"
LANGUAGE_FALLBACK = ("de", "fr", "en")
DEFAULT_USER_AGENT = "MLOps-HS-25-data-pipeline/1.0"


HTML_TAG_RE = re.compile(r"<[^>]+>")


class SimapApiError(RuntimeError):
    """Raised when the SIMAP API returns unrecoverable errors."""


def strip_html(value: Optional[str]) -> Optional[str]:
    """Remove simple HTML tags from text blocks."""

    if not value:
        return value
    return HTML_TAG_RE.sub("", value)


def select_translation(data: Any, languages: Sequence[str] = LANGUAGE_FALLBACK) -> Optional[str]:
    """Pick the first available translation (de -> fr -> en)."""

    if data is None:
        return None
    if isinstance(data, str):
        return strip_html(data).strip() or None
    if isinstance(data, dict):
        for lang in languages:
            text = strip_html(data.get(lang))
            if text:
                text = text.strip()
                if text:
                    return text
        for candidate in data.values():
            text = strip_html(candidate)
            if text:
                text = text.strip()
                if text:
                    return text
    return None


def format_price(price: Optional[Dict[str, Any]]) -> Optional[str]:
    """Format a price object into an easily readable string."""

    if not isinstance(price, dict):
        return None
    amount = price.get("price") or price.get("amount") or price.get("value")
    currency = price.get("currency") or price.get("currencyCode") or price.get("currencyId")
    if amount is None:
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if currency:
        return f"{currency.upper()} {amount:,.2f}"
    return f"{amount:,.2f}"


def format_criteria(items: Optional[Iterable[Dict[str, Any]]]) -> Optional[str]:
    """Convert award/qualification criteria to a compact text representation."""

    if not items:
        return None

    formatted: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = select_translation(item.get("title")) or "-"
        weighting = item.get("weighting")
        note_parts: List[str] = []
        if weighting is not None:
            try:
                weighting_val = int(weighting)
                note_parts.append(f"{weighting_val}%")
            except (TypeError, ValueError):
                note_parts.append(str(weighting))
        if item.get("isPriceCriterion"):
            note_parts.append("Preis")
        note = ", ".join(note_parts)
        formatted.append(f"{title} [{note}]" if note else title)
    return "; ".join(formatted) if formatted else None


def deduplicate_join(values: Iterable[str]) -> Optional[str]:
    """Join unique, truthy values with '; ' preserving insert order."""

    seen = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.append(value)
    return "; ".join(seen) if seen else None


def extract_codes(detail: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Collect classification codes from procurement and lot blocks."""

    buckets: Dict[str, List[str]] = {
        "cpv": [],
        "bkp": [],
        "npk": [],
        "oag": [],
        "ebkp-h": [],
        "ebkp-t": [],
    }

    def add_code(bucket: str, value: Any) -> None:
        if isinstance(value, str):
            buckets[bucket].append(value)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            for entry in value:
                if isinstance(entry, str):
                    buckets[bucket].append(entry)

    def harvest(node: Optional[Dict[str, Any]]) -> None:
        if not isinstance(node, dict):
            return
        add_code("cpv", node.get("cpvCode"))
        add_code("cpv", node.get("additionalCpvCodes"))
        add_code("bkp", node.get("bkpCodes"))
        add_code("npk", node.get("npkCodes"))
        add_code("oag", node.get("oagCodes"))
        add_code("ebkp-h", node.get("ebkphCodes"))
        add_code("ebkp-t", node.get("ebkptCodes"))

    harvest(detail.get("procurement"))
    for lot in detail.get("lots", []) or []:
        if isinstance(lot, dict):
            harvest(lot.get("procurement") or lot)
    return {key: deduplicate_join(values) for key, values in buckets.items()}


def extract_location(project: Dict[str, Any], detail: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Use project order address first and fall back to publication detail data."""

    candidate_nodes: List[Dict[str, Any]] = []
    if isinstance(project.get("orderAddress"), dict):
        candidate_nodes.append(project["orderAddress"])
    procurement = detail.get("procurement")
    if isinstance(procurement, dict) and isinstance(procurement.get("orderAddress"), dict):
        candidate_nodes.append(procurement["orderAddress"])
    for lot in detail.get("lots", []) or []:
        if isinstance(lot, dict):
            order_address = lot.get("orderAddress")
            if isinstance(order_address, dict):
                candidate_nodes.append(order_address)

    country = canton = city = None
    for node in candidate_nodes:
        country = country or node.get("countryId")
        canton = canton or node.get("cantonId")
        city = city or select_translation(node.get("city"))
        if country and city:
            break
    return country, canton, city


def flatten_vendor_prices(detail: Dict[str, Any]) -> Optional[str]:
    """Gather awarded vendor prices for award publications."""

    decision = detail.get("decision")
    if not isinstance(decision, dict):
        return None
    vendors = decision.get("vendors")
    if not isinstance(vendors, list):
        return None
    prices = [
        format_price(vendor.get("price"))
        for vendor in vendors
        if isinstance(vendor, dict)
    ]
    return deduplicate_join(price for price in prices if price)


def get_order_type(project: Dict[str, Any], detail: Dict[str, Any]) -> Optional[str]:
    """Extract order type from project search or detail structures."""

    project_info = detail.get("project-info")
    for source in (project, project_info, detail.get("procurement")):
        if isinstance(source, dict):
            order_type = source.get("orderType")
            if order_type:
                return order_type
    return None


def resolve_description(detail: Dict[str, Any]) -> Optional[str]:
    """Prefer structured order descriptions and fall back to generic text."""

    procurement = detail.get("procurement")
    description = select_translation(procurement.get("orderDescription")) if isinstance(procurement, dict) else None
    if description:
        return description
    return select_translation(detail.get("description"))


@dataclass
class SimapClient:
    """Small helper to handle retries and pagination against the SIMAP API."""

    base_url: str = BASE_URL
    timeout: int = 20
    max_retries: int = 4
    backoff_factor: float = 1.5
    session: Session = Session()

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.session.headers.setdefault("Accept", "application/json")
        self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        """Issue an HTTP request with retry handling for transient issues."""

        url = f"{self.base_url}{path}"
        retries = self.max_retries

        for attempt in range(1, retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.Timeout as exc:
                if attempt == retries:
                    raise SimapApiError(f"Request timeout after {retries} attempts: {url}") from exc
                sleep_secs = self.backoff_factor ** attempt
                logging.warning("Timeout contacting %s. Retrying in %.1fs.", url, sleep_secs)
                time.sleep(sleep_secs)
                continue

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else self.backoff_factor ** attempt
                except ValueError:
                    wait = self.backoff_factor ** attempt
                logging.warning("Rate limited by SIMAP. Waiting %.1fs before retrying.", wait)
                time.sleep(wait)
                continue

            if response.status_code >= 500:
                if attempt == retries:
                    raise SimapApiError(f"Server error {response.status_code} for {url}")
                sleep_secs = self.backoff_factor ** attempt
                logging.warning(
                    "Server error %s for %s. Retrying in %.1fs.",
                    response.status_code,
                    url,
                    sleep_secs,
                )
                time.sleep(sleep_secs)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise SimapApiError(f"HTTP error for {url}: {exc}") from exc
            return response

        raise SimapApiError(f"Failed to fetch {url}")

    def get_project_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request("GET", SEARCH_ENDPOINT, params=params)
        return response.json()

    def get_publication_detail(self, project_id: str, publication_id: str) -> Dict[str, Any]:
        path = DETAIL_ENDPOINT.format(project_id=project_id, publication_id=publication_id)
        response = self._request("GET", path)
        return response.json()


def iterate_projects(
    client: SimapClient,
    base_params: Dict[str, Any],
    max_pages: Optional[int] = None,
    delay_between_pages: float = 0.5,
) -> Iterable[Dict[str, Any]]:
    """Stream projects via rolling pagination."""

    last_item: Optional[str] = None
    pages = 0
    seen_last_items: set[str] = set()

    while True:
        params = dict(base_params)
        if last_item:
            params["lastItem"] = last_item
        payload = client.get_project_page(params)
        projects = payload.get("projects") or []
        if not projects:
            logging.info("No further projects returned. Pagination finished.")
            break

        for project in projects:
            if isinstance(project, dict):
                yield project

        pages += 1
        if max_pages and pages >= max_pages:
            logging.info("Reached configured page limit (%s).", max_pages)
            break

        pagination = payload.get("pagination") or {}
        new_last_item = pagination.get("lastItem")
        if not new_last_item or new_last_item in seen_last_items:
            logging.info("Pagination key not advancing. Stopping after %s pages.", pages)
            break
        seen_last_items.add(new_last_item)
        last_item = new_last_item

        items_per_page = pagination.get("itemsPerPage")
        if items_per_page and len(projects) < items_per_page:
            logging.info("Last page returned fewer items than itemsPerPage. Assuming end of feed.")
            break

        if delay_between_pages > 0:
            time.sleep(delay_between_pages)


def enrich_project(
    project: Dict[str, Any],
    detail: Dict[str, Any],
) -> Dict[str, Any]:
    """Combine data from search results and publication detail response."""

    codes = extract_codes(detail)
    country, canton, city = extract_location(project, detail)
    award_criteria = None
    qualification_criteria = None
    criteria_block = detail.get("criteria")
    if isinstance(criteria_block, dict):
        award_criteria = format_criteria(criteria_block.get("awardCriteria"))
        qualification_criteria = format_criteria(criteria_block.get("qualificationCriteria"))

    enriched = {
        "project_id": project.get("id"),
        "publication_id": project.get("publicationId"),
        "publication_date": project.get("publicationDate"),
        "pub_type": project.get("pubType"),
        "title": select_translation(project.get("title")),
        "description": resolve_description(detail),
        "cpv": codes["cpv"],
        "bkp": codes["bkp"],
        "npk": codes["npk"],
        "oag": codes["oag"],
        "ebkp-h": codes["ebkp-h"],
        "ebkp-t": codes["ebkp-t"],
        "country": country,
        "canton": canton,
        "city": city,
        "project_type": project.get("projectType"),
        "process_type": project.get("processType"),
        "order_type": get_order_type(project, detail),
        "award_criteria": award_criteria,
        "qualification_criteria": qualification_criteria,
        "submission_deadline": (detail.get("dates") or {}).get("offerDeadline"),
        "estimated_value": format_price((detail.get("terms") or {}).get("totalPrice")),
        "award_value": flatten_vendor_prices(detail),
        "proc_office_name": select_translation(project.get("procOfficeName")),
    }
    return enriched


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """CLI argument configuration."""

    parser = argparse.ArgumentParser(
        description="Download SIMAP project publications enriched with detail metadata.",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Fetch projects whose newest publication is not older than N days (default: 30).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Limit pagination to at most N pages (default: 5).",
    )
    parser.add_argument(
        "--page-delay",
        type=float,
        default=0.5,
        help="Delay between page fetches in seconds to mitigate rate limits (default: 0.5).",
    )
    parser.add_argument(
        "--detail-delay",
        type=float,
        default=0.25,
        help="Delay between detail requests in seconds (default: 0.25).",
    )
    parser.add_argument(
        "--output",
        default="simap_projects.csv",
        help="Path to the CSV file that will be written (default: simap_projects.csv).",
    )
    parser.add_argument(
        "--max-projects",
        type=int,
        default=None,
        help="Optional hard cap on the number of projects to fetch.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    """Configure root logger according to CLI options."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def ensure_publication_filter(days_back: int) -> Dict[str, Any]:
    """Construct compliant project-search parameters."""

    utc_now = datetime.now(timezone.utc)
    since = utc_now - timedelta(days=max(0, days_back))
    return {
        "newestPublicationFrom": since.date().isoformat(),
    }


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by both CLI and module-level execution."""

    args = parse_arguments(argv)
    configure_logging(args.log_level)

    params = ensure_publication_filter(args.days_back)
    client = SimapClient()
    records: List[Dict[str, Any]] = []

    try:
        iterator = iterate_projects(
            client=client,
            base_params=params,
            max_pages=args.max_pages,
            delay_between_pages=args.page_delay,
        )

        for idx, project in enumerate(iterator, start=1):
            if args.max_projects and idx > args.max_projects:
                logging.info("Reached --max-projects=%s. Stopping.", args.max_projects)
                break
            project_id = project.get("id")
            publication_id = project.get("publicationId")
            if not project_id or not publication_id:
                logging.warning("Skipping project lacking identifiers: %s", project)
                continue

            try:
                detail = client.get_publication_detail(project_id, publication_id)
            except SimapApiError as exc:
                logging.error("Detail request failed for project %s / publication %s: %s", project_id, publication_id, exc)
                continue

            # --- DEBUG: Speichere ein Beispielprojekt als JSON ---
            if idx == 1:
                import json
                out_path = os.path.abspath("sample_project.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump({"project": project, "detail": detail}, f, ensure_ascii=False, indent=2)
                logging.info(f"Beispieldatei gespeichert: {out_path}")
            # -----------------------------------------------------

            record = enrich_project(project, detail)
            records.append(record)

            if args.detail_delay > 0:
                time.sleep(args.detail_delay)

    except SimapApiError as exc:
        logging.error("Aborting due to SIMAP API error: %s", exc)
        return 1
    except requests.RequestException as exc:
        logging.error("Unexpected requests error: %s", exc)
        return 1

    if not records:
        logging.warning("No projects collected. No CSV written.")
        return 0

    df = pd.DataFrame(records)
    df.to_csv(args.output, index=False, quoting=csv.QUOTE_NONNUMERIC)
    logging.info("Wrote %s rows to %s.", len(df), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(run())

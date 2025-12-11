"""
Einfacher API-Client für SIMAP (Swiss Internet Market Place).

Holt öffentliche Ausschreibungsdaten von der SIMAP-API mit automatischer
Paginierung und Fehlerbehandlung.
"""
import logging
import time
from typing import Any, Dict, Iterator, Optional

import requests


class SimapApiError(Exception):
    """Fehler beim Abrufen von der SIMAP API."""
    pass


class SimapClient:
    """
    HTTP-Client für die SIMAP-API mit Retry-Logik.

    Beispiel:
        client = SimapClient()
        params = {"newestPublicationFrom": "2024-01-01"}
        for project in client.get_projects(params):
            print(project['id'])
    """

    BASE_URL = "https://www.simap.ch/api"
    SEARCH_ENDPOINT = "/publications/v2/project/project-search"
    DETAIL_ENDPOINT = "/publications/v1/project/{project_id}/publication-details/{publication_id}"

    def __init__(self, timeout: int = 20, max_retries: int = 3):
        """
        Args:
            timeout: Timeout in Sekunden für HTTP-Requests
            max_retries: Maximum Anzahl von Wiederholungsversuchen
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "SIMAP-CSV-Exporter/1.0"
        })

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Führt HTTP-Request mit Retry-Logik aus.

        Behandelt:
        - Timeouts mit exponential backoff
        - Rate Limiting (429)
        - Server Errors (500+)
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)

                # Rate Limiting
                if response.status_code == 429:
                    wait = float(response.headers.get("Retry-After", 2 ** attempt))
                    logging.warning(f"Rate limited. Warte {wait}s...")
                    time.sleep(wait)
                    continue

                # Server Errors
                if response.status_code >= 500:
                    if attempt == self.max_retries:
                        raise SimapApiError(f"Server Error {response.status_code}: {url}")
                    wait = 2 ** attempt
                    logging.warning(f"Server Error {response.status_code}. Retry in {wait}s...")
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except requests.Timeout:
                if attempt == self.max_retries:
                    raise SimapApiError(f"Timeout nach {attempt} Versuchen: {url}")
                wait = 2 ** attempt
                logging.warning(f"Timeout. Retry in {wait}s...")
                time.sleep(wait)

        raise SimapApiError(f"Request fehlgeschlagen: {url}")

    def get_projects(
        self,
        params: Dict[str, Any],
        max_pages: Optional[int] = None,
        delay: float = 0.5
    ) -> Iterator[Dict[str, Any]]:
        """
        Holt Projekte mit automatischer Paginierung.

        Args:
            params: API Query-Parameter (z.B. newestPublicationFrom)
            max_pages: Maximum Anzahl von Seiten (None = alle)
            delay: Wartezeit zwischen Seiten in Sekunden

        Yields:
            Projekt-Dictionaries von der API
        """
        url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"
        last_item = None
        page = 0

        while True:
            # Paginierung
            current_params = dict(params)
            if last_item:
                current_params["lastItem"] = last_item

            response = self._request("GET", url, params=current_params)
            data = response.json()

            projects = data.get("projects", [])
            if not projects:
                logging.info("Keine weiteren Projekte gefunden.")
                break

            # Yield alle Projekte dieser Seite
            for project in projects:
                if isinstance(project, dict):
                    yield project

            page += 1
            logging.info(f"Seite {page}: {len(projects)} Projekte abgerufen")

            # Prüfe Seitenlimit
            if max_pages and page >= max_pages:
                logging.info(f"Max. Seiten ({max_pages}) erreicht.")
                break

            # Prüfe Paginierung
            pagination = data.get("pagination", {})
            last_item = pagination.get("lastItem")
            if not last_item:
                logging.info("Keine weiteren Seiten verfügbar.")
                break

            # Warte zwischen Seiten
            if delay > 0:
                time.sleep(delay)

    def get_project_details(self, project_id: str, publication_id: str) -> Dict[str, Any]:
        """
        Holt Details zu einem spezifischen Projekt.

        Args:
            project_id: ID des Projekts
            publication_id: ID der Publikation

        Returns:
            Detail-Dictionary von der API
        """
        url = f"{self.BASE_URL}{self.DETAIL_ENDPOINT}".format(
            project_id=project_id,
            publication_id=publication_id
        )
        response = self._request("GET", url)
        return response.json()

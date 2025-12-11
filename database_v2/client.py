"""
SIMAP API Client.

Fokus auf den project-search Endpoint, der bereits alle relevanten Daten enthält.
Unterstützt Rolling Pagination mit lastItem Cursor.
"""
import logging
import time
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://www.simap.ch/api"
SEARCH_ENDPOINT = "/publications/v2/project/project-search"


class SimapClient:
    """
    Client für SIMAP Public API.
    
    Hauptmethode: search_projects() - iteriert über alle Projekte
    mit automatischer Pagination.
    
    Beispiel:
        client = SimapClient()
        for project in client.search_projects(publication_from="2024-01-01"):
            print(project["title"])
    """
    
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = 20,
        max_retries: int = 3,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.session = self._create_session(max_retries)
    
    def _create_session(self, max_retries: int) -> requests.Session:
        """Erstellt Session mit Retry-Logik."""
        session = requests.Session()
        
        retry = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def search_projects(
        self,
        publication_from: Optional[str] = None,
        publication_until: Optional[str] = None,
        cantons: Optional[list[str]] = None,
        process_types: Optional[list[str]] = None,
        project_subtypes: Optional[list[str]] = None,
        search_text: Optional[str] = None,
        max_pages: Optional[int] = None,
        delay: float = 0.1,
    ) -> Iterator[dict]:
        """
        Iteriert über alle Projekte via Rolling Pagination.
        
        Args:
            publication_from: Start-Datum (YYYY-MM-DD)
            publication_until: End-Datum (YYYY-MM-DD)
            cantons: Liste von Kantonskürzeln (ZH, BE, etc.)
            process_types: open, selective, invitation
            project_subtypes: Für pub_type Filter
            search_text: Volltextsuche (min. 3 Zeichen)
            max_pages: Maximum Seiten (für Testing)
            delay: Pause zwischen Requests (Rate Limiting)
            
        Yields:
            dict: Einzelne ProjectsSearchEntry Objekte
            
        Note:
            Die API erfordert mindestens einen Filter (search oder quick-filter).
            Bei fehlendem Filter wird automatisch publication_from gesetzt.
        """
        url = urljoin(self.base_url, SEARCH_ENDPOINT)
        
        # Parameter aufbauen
        params = self._build_params(
            publication_from=publication_from,
            publication_until=publication_until,
            cantons=cantons,
            process_types=process_types,
            project_subtypes=project_subtypes,
            search_text=search_text,
        )
        
        # Sicherstellen dass mindestens ein Filter gesetzt ist
        if not any(params.values()):
            logger.warning("Keine Filter gesetzt - API verlangt mindestens einen")
            return
        
        last_item = None
        page = 0
        total_projects = 0
        
        while True:
            if last_item:
                params["lastItem"] = last_item
            
            try:
                logger.debug(f"Fetching page {page + 1}: {params}")
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                
            except requests.Timeout:
                logger.error(f"Timeout auf Seite {page + 1}")
                break
            except requests.RequestException as e:
                logger.error(f"API Error auf Seite {page + 1}: {e}")
                break
            
            projects = data.get("projects", [])
            
            if not projects:
                logger.debug("Keine weiteren Projekte")
                break
            
            for project in projects:
                yield project
                total_projects += 1
            
            # Pagination cursor
            pagination = data.get("pagination", {})
            last_item = pagination.get("lastItem")
            
            if not last_item:
                logger.debug("Kein lastItem - letzte Seite erreicht")
                break
            
            page += 1
            
            if max_pages and page >= max_pages:
                logger.info(f"Max pages ({max_pages}) erreicht")
                break
            
            # Rate limiting
            time.sleep(delay)
        
        logger.info(f"✓ {total_projects} Projekte von {page + 1} Seiten geladen")
    
    def _build_params(
        self,
        publication_from: Optional[str],
        publication_until: Optional[str],
        cantons: Optional[list[str]],
        process_types: Optional[list[str]],
        project_subtypes: Optional[list[str]],
        search_text: Optional[str],
    ) -> dict:
        """Baut Query-Parameter auf."""
        params = {}
        
        if publication_from:
            params["newestPublicationFrom"] = publication_from
        
        if publication_until:
            params["newestPublicationUntil"] = publication_until
        
        if cantons:
            # API akzeptiert Komma-separiert oder als Array
            params["orderAddressCantons"] = cantons
        
        if process_types:
            params["processTypes"] = process_types
        
        if project_subtypes:
            # Für Filter nach pub_type (tender, award, etc.)
            params["projectSubTypes"] = project_subtypes
        
        if search_text and len(search_text) >= 3:
            params["search"] = search_text
        
        return params
    
    def get_publication_detail(
        self,
        project_id: str,
        publication_id: str,
    ) -> Optional[dict]:
        """
        Holt Details einer spezifischen Publikation.
        
        ACHTUNG: Nur bei Bedarf aufrufen - jeder Call ist ein HTTP Request!
        Die Search-Response enthält bereits die meisten relevanten Felder.
        
        Args:
            project_id: UUID des Projekts
            publication_id: UUID der Publikation
            
        Returns:
            PublicationDetail oder None bei Fehler
        """
        url = urljoin(
            self.base_url,
            f"/publications/v1/project/{project_id}/publication-details/{publication_id}"
        )
        
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Fehler beim Laden von Detail {publication_id}: {e}")
            return None


# Convenience Functions
def create_client(**kwargs) -> SimapClient:
    """Factory-Funktion für Client-Erstellung."""
    return SimapClient(**kwargs)

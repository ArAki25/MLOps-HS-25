import os, time, pathlib, json, requests, csv
from typing import Optional, Iterable, Dict, List
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = os.getenv("SIMAP_BASE_URL", "https://archiv.simap.ch/api")  # ggf. anpassen
DEFAULT_TIMEOUT = float(os.getenv("SIMAP_TIMEOUT", "30"))
OUT_DIR = pathlib.Path("data/raw"); OUT_DIR.mkdir(parents=True, exist_ok=True)

class SimapAPIClient:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        # Set default headers
        self.session.headers.update({
            "User-Agent": "SimapAPIClient/1.0 (+https://example.local)"
        })

        token = os.getenv("SIMAP_API_TOKEN")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

        # Configure retries with backoff for transient errors
        retries = Retry(
            total=int(os.getenv("SIMAP_RETRIES", "5")),
            backoff_factor=float(os.getenv("SIMAP_BACKOFF", "0.5")),
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_json(self, url: str, timeout: Optional[float] = None):
        try:
            resp = self.session.get(url, timeout=timeout or DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"HTTP-Fehler bei GET {url}: {exc}")
        except ValueError:
            print(f"Antwort ist kein gültiges JSON: {url}")
        return None

    def _post_json(self, url: str, payload: dict, params: Optional[dict] = None, timeout: Optional[float] = None):
        try:
            resp = self.session.post(url, json=payload, params=params, timeout=timeout or DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"HTTP-Fehler bei POST {url}: {exc}")
        except ValueError:
            print(f"Antwort ist kein gültiges JSON: {url}")
        return None

    def get_publication(self, publication_id):
        """Einzelne Publikation von SIMAP abrufen"""
        path = f"publication/{publication_id}"
        url = urljoin(self.base_url if self.base_url.endswith('/') else self.base_url + '/', path)
        data = self._get_json(url)
        if data is None:
            print(f"Fehler beim Abrufen der Publikation {publication_id}")
        return data

    def save_publication(self, publication_data, publication_id):
        """Publikation als JSON-Datei speichern"""
        if publication_data:
            filename = OUT_DIR / f"publication_{publication_id}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(publication_data, f, ensure_ascii=False, indent=2)
            print(f"Publikation {publication_id} gespeichert in {filename}")

    def get_openapi_docs(self, docs_path: Optional[str] = None):
        """
        OpenAPI-Dokumentation abrufen (JSON) – z.B. "/v3/api-docs".

        Hinweis: Wenn die Basis-URL bereits "/api" enthält (z.B. ".../api"),
        dann ist der Standardpfad "/v3/api-docs" korrekt. Falls Ihr Server die
        Docs unter "/api/v3/api-docs" bereitstellt, geben Sie diesen Pfad explizit an
        oder setzen Sie die Umgebungsvariable API_DOCS_PATH entsprechend.
        """
        path = docs_path or os.getenv("API_DOCS_PATH", "/v3/api-docs")
        # urljoin behandelt führenden Slash korrekt relativ zur base_url
        base = self.base_url if self.base_url.endswith('/') else self.base_url + '/'
        url = urljoin(base, path.lstrip('/'))
        return self._get_json(url)

    def search_publications(self, filters: Dict, page_no: int = 1, records_per_page: int = 100):
        """
        Suche auf /search. Gibt ResultDto (pages, total, publication[]) zurück.
        """
        base = self.base_url if self.base_url.endswith('/') else self.base_url + '/'
        url = urljoin(base, 'search')
        params = {"pageNo": page_no, "recordsPerPage": records_per_page}
        return self._post_json(url, payload=filters or {}, params=params)

    def iterate_publications(self, filters: Dict, records_per_page: int = 100, max_pages: Optional[int] = None):
        """
        Iteriert über Seiten und liefert Publication-Objekte.
        """
        page = 1
        while True:
            result = self.search_publications(filters, page_no=page, records_per_page=records_per_page)
            if not result:
                break
            pubs = result.get('publication') or []
            for p in pubs:
                yield p
            pages = result.get('pages') or 0
            if max_pages is not None and page >= max_pages:
                break
            if page >= pages or pages == 0:
                break
            page += 1

    def export_publications_csv(self, publications: Iterable[Dict], filename: str = "auftraege.csv") -> pathlib.Path:
        """
        Exportiert relevante Felder der Suchergebnisse in eine CSV.
        Spalten: id, projectid, publicationDate, deadline, type, contType, proc,
        authName, contLoc, cpv, bkp, lang, description, lot_count.
        """
        fields = [
            "id",
            "projectid",
            "publicationDate",
            "deadline",
            "type",
            "contType",
            "proc",
            "authName",
            "contLoc",
            "cpv",
            "bkp",
            "lang",
            "description",
            "lot_count",
        ]
        path = OUT_DIR / filename
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for item in publications:
                lots = item.get('lot') or []
                row = {
                    "id": item.get("id"),
                    "projectid": item.get("projectid"),
                    "publicationDate": item.get("publicationDate"),
                    "deadline": item.get("deadline"),
                    "type": item.get("type"),
                    "contType": item.get("contType"),
                    "proc": item.get("proc"),
                    "authName": item.get("authName"),
                    "contLoc": item.get("contLoc"),
                    "cpv": item.get("cpv"),
                    "bkp": item.get("bkp"),
                    "lang": item.get("lang"),
                    "description": (item.get("description") or "").replace("\n", " ").strip(),
                    "lot_count": len(lots),
                }
                writer.writerow(row)
        print(f"CSV exportiert: {path}")
        return path

    def save_openapi_docs(self, data, filename: str = "openapi.json"):
        """OpenAPI-JSON im Datenverzeichnis speichern."""
        if data is None:
            print("Keine Daten zum Speichern der API Docs vorhanden.")
            return
        file_path = OUT_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"API Docs gespeichert in {file_path}")


def _join(values: Optional[Iterable[str]]) -> Optional[str]:
    if not values:
        return None
    cleaned: List[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            cleaned.append(s)
    return ", ".join(cleaned) if cleaned else None


def build_search_filters(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    types: Optional[Iterable[str]] = None,
    contract_types: Optional[Iterable[str]] = None,
    procedures: Optional[Iterable[str]] = None,
    cpv: Optional[Iterable[str]] = None,
    bkp: Optional[Iterable[str]] = None,
    keywords: Optional[str] = None,
    canton_codes: Optional[Iterable[str]] = None,
    city_codes: Optional[Iterable[str]] = None,
    deadline_passed: Optional[bool] = None,
    project_id: Optional[int] = None,
    notice_nr: Optional[int] = None,
) -> Dict:
    """
    Baut ein Filter-Dict für den /search-Endpoint (SearchDto Felder).

    - Datumsformat: YYYY-MM-DD
    - types: OB00..OB09
    - contract_types: SUPPLIES, SERVICES, WORKS, CONTEST (kommagetrennt)
    - procedures: OPEN, RESTRICTED, OTHER (kommagetrennt)
    - cpv, bkp: Codes als Liste
    - canton_codes: z.B. ["ZH", "BE"] => "ZH, BE"
    - city_codes: Werte wie SIMAP_CITY_01, SIMAP_CITY_02
    """
    f: Dict[str, object] = {}
    if start_date:
        f["stat_tm_1"] = start_date
    if end_date:
        f["stat_tm_2"] = end_date
    j = _join
    if (s := j(types)):
        f["type_cd_ob"] = s
    if (s := j(contract_types)):
        f["type_contract_cd_ob"] = s
    if (s := j(procedures)):
        f["proc_cd_ob"] = s
    if (s := j(cpv)):
        f["cpv_ob"] = s
    if (s := j(bkp)):
        f["bkp_ob"] = s
    if (s := j(canton_codes)):
        f["kanton_cd_ob"] = s
    if (s := j(city_codes)):
        f["city_cd_ob"] = s
    if keywords:
        f["keywords"] = keywords
    if deadline_passed is not None:
        f["deadline_passed_ob"] = bool(deadline_passed)
    if project_id is not None:
        f["project_id_ob"] = int(project_id)
    if notice_nr is not None:
        f["notice_nr"] = int(notice_nr)
    return f

if __name__ == "__main__":
    client = SimapAPIClient()
    mode = os.getenv("SIMAP_MODE", "docs")
    if mode == "docs":
        docs_path = os.getenv("API_DOCS_PATH")  # optional, z.B. "/api/v3/api-docs"
        docs = client.get_openapi_docs(docs_path)
        if docs:
            client.save_openapi_docs(docs)
    elif mode == "csv":
        # Beispiel: Ausschreibungen (OB00, OB01, OB05, OB07)
        filters = {
            "type_cd_ob": "OB00,OB01,OB05,OB07",
            # optional: Zeitraum, Keywords, CPV/BKP, usw.
            # "stat_tm_1": "2023-01-01",
            # "stat_tm_2": "2030-12-31",
            # "keywords": "*Brücke*",
        }
        pubs = client.iterate_publications(filters, records_per_page=200)
        client.export_publications_csv(pubs, filename=os.getenv("SIMAP_CSV_NAME", "auftraege.csv"))

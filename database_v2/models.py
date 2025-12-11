"""
Pydantic Models für SIMAP Daten.

Type-safe Datenstrukturen für API Responses und DB Operationen.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class Translation(BaseModel):
    """Mehrsprachiger Text (SIMAP liefert de/fr/it/en)."""
    de: Optional[str] = None
    fr: Optional[str] = None
    it: Optional[str] = None
    en: Optional[str] = None
    
    def best(self, preferred: str = "de") -> Optional[str]:
        """Gibt beste verfügbare Übersetzung zurück."""
        for lang in [preferred, "de", "fr", "it", "en"]:
            if val := getattr(self, lang, None):
                return val
        return None
    
    def __str__(self) -> str:
        return self.best() or ""


class OrderAddress(BaseModel):
    """Adresse des Ausführungsorts."""
    canton: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = "CH"


class Project(BaseModel):
    """
    Ein SIMAP Projekt/Ausschreibung.
    
    Basiert auf ProjectsSearchEntry aus der API.
    Enthält alle Felder die aus der Search-Response kommen.
    """
    
    # SIMAP IDs
    simap_project_id: str = Field(..., description="UUID des Projekts")
    simap_publication_id: str = Field(..., description="UUID der Publikation")
    project_number: Optional[str] = None
    publication_number: Optional[str] = None
    
    # Titel (mehrsprachig)
    title: Translation = Field(default_factory=Translation)
    
    # Daten
    publication_date: date
    submission_deadline: Optional[datetime] = None
    
    # Typen & Klassifizierung
    pub_type: str = Field(..., description="tender, award, revocation, etc.")
    project_type: Optional[str] = Field(None, description="tender, competition, study_contract")
    project_subtype: Optional[str] = Field(None, description="open, selective, invitation, direct")
    process_type: Optional[str] = Field(None, description="open, selective, invitation")
    order_type: Optional[str] = Field(None, description="construction, service, supply")
    lots_type: Optional[str] = Field(None, description="with, without")
    corrected: bool = False
    
    # Auftraggeber
    proc_office_name: Translation = Field(default_factory=Translation)
    
    # Ort
    order_address: OrderAddress = Field(default_factory=OrderAddress)
    
    # Award-spezifisch (nur bei pub_type='award')
    winner_name: Optional[str] = None
    winner_city: Optional[str] = None
    award_amount: Optional[float] = None
    award_currency: Optional[str] = None
    number_of_submissions: Optional[int] = None
    
    # Codes
    cpv_codes: list[str] = Field(default_factory=list)
    bkp_codes: list[str] = Field(default_factory=list)
    
    # Lots (bei lotsType='with')
    lots: list[dict] = Field(default_factory=list)
    
    # Raw JSON für spätere Detail-Extraktion
    raw_json: dict = Field(default_factory=dict)
    
    @property
    def canton(self) -> Optional[str]:
        """Shortcut für Kanton."""
        return self.order_address.canton
    
    @property
    def title_str(self) -> str:
        """Titel als String (bevorzugt Deutsch)."""
        return str(self.title)


class ProjectFilter(BaseModel):
    """Filter für Projekt-Abfragen."""
    cantons: Optional[list[str]] = None
    pub_types: Optional[list[str]] = None
    process_types: Optional[list[str]] = None
    order_types: Optional[list[str]] = None
    publication_from: Optional[date] = None
    publication_until: Optional[date] = None
    search_text: Optional[str] = None
    only_active: bool = False  # Nur mit Deadline in Zukunft
    limit: int = 100
    offset: int = 0


class SyncStats(BaseModel):
    """Statistiken eines Sync-Laufs."""
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    duration_seconds: float = 0.0

"""
Database v2 - Vereinfachte SIMAP Datenbank-Integration.

Module:
    - models: Pydantic Models für Type-Safety
    - client: SIMAP API Client
    - parser: API Response → Model Transformation  
    - repository: Alle DB-Operationen
    - sync: Synchronisations-Logik

Quick Start:
    from database_v2 import sync, repo, ProjectFilter
    
    # Synchronisieren
    stats = sync(days_back=7)
    
    # Abfragen
    projects = repo.find(ProjectFilter(
        cantons=["ZH", "BE"],
        pub_types=["tender"],
        limit=100
    ))
"""

# Models
from .models import (
    Project,
    ProjectFilter,
    Translation,
    OrderAddress,
    SyncStats,
)

# Repository
from .repository import (
    repo,
    ProjectRepository,
    get_connection,
    init_pool,
    close_pool,
)

# Sync
from .sync import (
    sync,
    sync_awards,
    DEFAULT_CANTONS,
)

# Client & Parser (für fortgeschrittene Nutzung)
from .client import SimapClient
from .parser import parse_search_response, parse_project_entry

__all__ = [
    # Models
    "Project",
    "ProjectFilter", 
    "Translation",
    "OrderAddress",
    "SyncStats",
    # Repository
    "repo",
    "ProjectRepository",
    "get_connection",
    "init_pool",
    "close_pool",
    # Sync
    "sync",
    "sync_awards",
    "DEFAULT_CANTONS",
    # Client
    "SimapClient",
    "parse_search_response",
    "parse_project_entry",
]

__version__ = "2.0.0"

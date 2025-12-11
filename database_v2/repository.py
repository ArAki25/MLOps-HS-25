"""
Repository Pattern für Datenbank-Operationen.

Zentrale Klasse für alle Projekt-bezogenen DB-Operationen.
Verwendet Connection Pooling und Batch-Operations für Performance.
"""
import logging
from datetime import date, datetime
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values, RealDictCursor, Json

from .models import Project, ProjectFilter

logger = logging.getLogger(__name__)

# Connection Pool (Modul-Level Singleton)
_pool: Optional[pool.SimpleConnectionPool] = None


def init_pool(dsn: str, min_conn: int = 1, max_conn: int = 5) -> None:
    """Initialisiert den Connection Pool."""
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(min_conn, max_conn, dsn)
        logger.info(f"Connection Pool initialisiert (max={max_conn})")


def close_pool() -> None:
    """Schliesst den Connection Pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Connection Pool geschlossen")


@contextmanager
def get_connection():
    """
    Context Manager für gepoolte Verbindungen.
    
    Beispiel:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    global _pool
    
    if _pool is None:
        import os
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise ValueError("DATABASE_URL nicht gesetzt und kein Pool initialisiert")
        init_pool(dsn)
    
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


class ProjectRepository:
    """
    Repository für Projekt-DB-Operationen.
    
    Methoden:
        - upsert_batch: Massenupsert von Projekten
        - find: Suche mit Filtern
        - get_by_id: Einzelnes Projekt
        - get_last_publication_date: Für Delta-Sync
        - count: Gesamtanzahl
        - stats: Statistiken
    """
    
    def upsert_batch(
        self,
        projects: list[Project],
        batch_size: int = 500,
    ) -> tuple[int, int]:
        """
        Fügt Projekte ein oder aktualisiert sie (Upsert).
        
        Args:
            projects: Liste von Project-Objekten
            batch_size: Batch-Grösse für execute_values
            
        Returns:
            Tuple (inserted, updated) - approximierte Zahlen
        """
        if not projects:
            return 0, 0
        
        sql = """
        INSERT INTO projects (
            simap_project_id, simap_publication_id, project_number,
            publication_number, title_de, title_fr, title_it,
            publication_date, pub_type, project_type, project_subtype,
            process_type, order_type, lots_type, corrected,
            proc_office_name_de, proc_office_name_fr,
            canton, city, postal_code, country,
            cpv_codes, bkp_codes, lots_count, raw_json
        ) VALUES %s
        ON CONFLICT (simap_project_id, simap_publication_id)
        DO UPDATE SET
            title_de = EXCLUDED.title_de,
            title_fr = EXCLUDED.title_fr,
            title_it = EXCLUDED.title_it,
            publication_date = EXCLUDED.publication_date,
            pub_type = EXCLUDED.pub_type,
            corrected = EXCLUDED.corrected,
            canton = EXCLUDED.canton,
            city = EXCLUDED.city,
            raw_json = EXCLUDED.raw_json,
            updated_at = NOW()
        """
        
        total = 0
        with get_connection() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(projects), batch_size):
                    batch = projects[i:i + batch_size]
                    values = [self._project_to_tuple(p) for p in batch]
                    
                    execute_values(cur, sql, values, page_size=batch_size)
                    total += len(batch)
                
                conn.commit()
        
        logger.info(f"✓ {total} Projekte upserted")
        # Wir können inserted/updated nicht genau zählen ohne RETURNING
        return total, 0
    
    def _project_to_tuple(self, p: Project) -> tuple:
        """Konvertiert Project zu DB-Tuple."""
        return (
            p.simap_project_id,
            p.simap_publication_id,
            p.project_number,
            p.publication_number,
            p.title.de,
            p.title.fr,
            p.title.it,
            p.publication_date,
            p.pub_type,
            p.project_type,
            p.project_subtype,
            p.process_type,
            p.order_type,
            p.lots_type,
            p.corrected,
            p.proc_office_name.de,
            p.proc_office_name.fr,
            p.order_address.canton,
            p.order_address.city,
            p.order_address.postal_code,
            p.order_address.country,
            p.cpv_codes or [],
            p.bkp_codes or [],
            len(p.lots),
            Json(p.raw_json),
        )
    
    def find(self, filters: ProjectFilter) -> list[dict]:
        """
        Sucht Projekte mit Filtern.
        
        Args:
            filters: ProjectFilter mit Suchkriterien
            
        Returns:
            Liste von Projekten als Dictionaries
        """
        conditions = ["1=1"]
        params = []
        
        if filters.cantons:
            conditions.append("canton = ANY(%s)")
            params.append(filters.cantons)
        
        if filters.pub_types:
            conditions.append("pub_type = ANY(%s)")
            params.append(filters.pub_types)
        
        if filters.process_types:
            conditions.append("process_type = ANY(%s)")
            params.append(filters.process_types)
        
        if filters.order_types:
            conditions.append("order_type = ANY(%s)")
            params.append(filters.order_types)
        
        if filters.publication_from:
            conditions.append("publication_date >= %s")
            params.append(filters.publication_from)
        
        if filters.publication_until:
            conditions.append("publication_date <= %s")
            params.append(filters.publication_until)
        
        if filters.search_text:
            conditions.append(
                "to_tsvector('german', COALESCE(title_de, '')) "
                "@@ plainto_tsquery('german', %s)"
            )
            params.append(filters.search_text)
        
        if filters.only_active:
            conditions.append("submission_deadline > NOW()")
        
        where = " AND ".join(conditions)
        params.extend([filters.limit, filters.offset])
        
        sql = f"""
            SELECT 
                id, simap_project_id, simap_publication_id,
                project_number, publication_number,
                title_de, title_fr, title_it,
                publication_date, pub_type, project_type,
                process_type, order_type, canton, city,
                submission_deadline, lots_count,
                created_at, updated_at
            FROM projects
            WHERE {where}
            ORDER BY publication_date DESC
            LIMIT %s OFFSET %s
        """
        
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
    
    def get_by_simap_id(
        self,
        project_id: str,
        publication_id: str,
    ) -> Optional[dict]:
        """Holt ein Projekt anhand der SIMAP IDs."""
        sql = """
            SELECT * FROM projects
            WHERE simap_project_id = %s AND simap_publication_id = %s
        """
        
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (project_id, publication_id))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def get_last_publication_date(self) -> Optional[date]:
        """Gibt das neueste publication_date zurück (für Delta-Sync)."""
        sql = "SELECT MAX(publication_date) FROM projects"
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                result = cur.fetchone()
                return result[0] if result and result[0] else None
    
    def count(self, filters: Optional[ProjectFilter] = None) -> int:
        """Zählt Projekte (optional gefiltert)."""
        if filters:
            conditions = ["1=1"]
            params = []
            
            if filters.cantons:
                conditions.append("canton = ANY(%s)")
                params.append(filters.cantons)
            if filters.pub_types:
                conditions.append("pub_type = ANY(%s)")
                params.append(filters.pub_types)
            
            where = " AND ".join(conditions)
            sql = f"SELECT COUNT(*) FROM projects WHERE {where}"
        else:
            sql = "SELECT COUNT(*) FROM projects"
            params = []
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()[0]
    
    def stats(self) -> dict:
        """Gibt Statistiken zurück."""
        sql = """
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT canton) as cantons,
                COUNT(DISTINCT pub_type) as pub_types,
                COUNT(*) FILTER (WHERE pub_type = 'tender') as tenders,
                COUNT(*) FILTER (WHERE pub_type = 'award') as awards,
                MIN(publication_date) as oldest,
                MAX(publication_date) as newest
            FROM projects
        """
        
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                row = cur.fetchone()
                return dict(row) if row else {}


# Singleton Instance
repo = ProjectRepository()

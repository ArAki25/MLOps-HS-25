-- ============================================================================
-- SIMAP Projects Schema v2
-- ============================================================================
-- Vereinfachtes Schema: Eine Haupttabelle statt komplexer Schichten.
-- Optimiert für Uni-Projekt und potentielles Startup.
--
-- Migration:
--   1. Backup alter Daten: pg_dump -t simap_projects > backup.sql
--   2. Dieses Script ausführen
--   3. Daten migrieren (siehe unten)
-- ============================================================================

-- Alte Tabelle umbenennen (falls vorhanden)
DO $$ 
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'simap_projects') THEN
        ALTER TABLE simap_projects RENAME TO simap_projects_old;
    END IF;
END $$;

-- Haupttabelle
CREATE TABLE IF NOT EXISTS projects (
    -- Interne ID (UUID für Supabase Kompatibilität)
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- SIMAP IDs (für Deduplizierung und API-Referenz)
    simap_project_id UUID NOT NULL,
    simap_publication_id UUID NOT NULL,
    
    -- Identifikatoren
    project_number TEXT,
    publication_number TEXT,
    
    -- Titel (mehrsprachig - nur relevante Felder extrahiert)
    title_de TEXT,
    title_fr TEXT,
    title_it TEXT,
    
    -- Kerndaten
    publication_date DATE NOT NULL,
    submission_deadline TIMESTAMPTZ,
    
    -- Typen & Klassifizierung
    pub_type TEXT NOT NULL,              -- tender, award, revocation, abandonment, etc.
    project_type TEXT,                   -- tender, competition, study_contract
    project_subtype TEXT,                -- Detailtyp
    process_type TEXT,                   -- open, selective, invitation, direct
    order_type TEXT,                     -- construction, service, supply
    lots_type TEXT,                      -- with, without
    corrected BOOLEAN DEFAULT FALSE,
    
    -- Auftraggeber
    proc_office_name_de TEXT,
    proc_office_name_fr TEXT,
    
    -- Ort (aus orderAddress extrahiert)
    canton TEXT,                         -- ZH, BE, etc.
    city TEXT,
    postal_code TEXT,
    country TEXT DEFAULT 'CH',
    
    -- Award-Felder (nur bei pub_type='award' gefüllt)
    winner_name TEXT,
    winner_city TEXT,
    winner_canton TEXT,
    award_amount NUMERIC(15,2),
    award_currency TEXT,                 -- CHF, EUR
    award_vat_type TEXT,
    number_of_submissions INT,
    award_decision_date DATE,
    
    -- Codes (als Arrays für einfache Queries)
    cpv_codes TEXT[],                    -- z.B. {'45233120', '45233121'}
    bkp_codes TEXT[],
    
    -- Zusätzliche Infos
    lots_count INT DEFAULT 0,
    
    -- Vollständiger API Response (für Details/ML später)
    raw_json JSONB,
    
    -- Metadaten
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT projects_simap_ids_unique 
        UNIQUE (simap_project_id, simap_publication_id)
);

-- ============================================================================
-- Indizes
-- ============================================================================

-- Primäre Abfrage-Patterns
CREATE INDEX IF NOT EXISTS idx_projects_pub_date 
    ON projects(publication_date DESC);

CREATE INDEX IF NOT EXISTS idx_projects_pub_type 
    ON projects(pub_type);

CREATE INDEX IF NOT EXISTS idx_projects_canton 
    ON projects(canton);

CREATE INDEX IF NOT EXISTS idx_projects_process_type 
    ON projects(process_type);

-- Für offene Ausschreibungen (häufiger Use Case)
CREATE INDEX IF NOT EXISTS idx_projects_deadline_active 
    ON projects(submission_deadline) 
    WHERE submission_deadline > NOW();

-- Volltext-Suche (Deutsch)
CREATE INDEX IF NOT EXISTS idx_projects_title_fts 
    ON projects 
    USING GIN(to_tsvector('german', COALESCE(title_de, '')));

-- JSONB für flexible Queries
CREATE INDEX IF NOT EXISTS idx_projects_raw_json 
    ON projects USING GIN(raw_json);

-- CPV-Code Suche (Array-Operatoren)
CREATE INDEX IF NOT EXISTS idx_projects_cpv 
    ON projects USING GIN(cpv_codes);

-- ============================================================================
-- Trigger für updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS projects_updated_at ON projects;
CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- Views für häufige Abfragen
-- ============================================================================

-- Aktive Ausschreibungen (Deadline in Zukunft)
CREATE OR REPLACE VIEW active_tenders AS
SELECT 
    id, simap_project_id, project_number,
    title_de, title_fr,
    publication_date, submission_deadline,
    process_type, order_type,
    canton, city,
    proc_office_name_de
FROM projects
WHERE pub_type = 'tender'
  AND submission_deadline > NOW()
ORDER BY submission_deadline;

-- Awards für ML-Analyse
CREATE OR REPLACE VIEW awards_for_ml AS
SELECT 
    id, simap_project_id, project_number,
    title_de,
    publication_date, award_decision_date,
    winner_name, winner_city, winner_canton,
    award_amount, award_currency,
    number_of_submissions,
    process_type, order_type, canton,
    cpv_codes, bkp_codes
FROM projects
WHERE pub_type = 'award'
  AND award_amount IS NOT NULL
ORDER BY award_decision_date DESC;

-- Statistiken pro Kanton
CREATE OR REPLACE VIEW stats_by_canton AS
SELECT 
    canton,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pub_type = 'tender') as tenders,
    COUNT(*) FILTER (WHERE pub_type = 'award') as awards,
    AVG(award_amount) FILTER (WHERE award_amount IS NOT NULL) as avg_award,
    MAX(publication_date) as latest
FROM projects
WHERE canton IS NOT NULL
GROUP BY canton
ORDER BY total DESC;

-- ============================================================================
-- Migration von alter Tabelle (falls vorhanden)
-- ============================================================================

-- INSERT INTO projects (
--     simap_project_id, simap_publication_id,
--     project_number, publication_number,
--     title_de, publication_date, pub_type,
--     project_type, process_type, order_type,
--     canton, city, postal_code,
--     submission_deadline,
--     winner_name, award_amount, award_currency,
--     number_of_submissions, award_decision_date,
--     created_at, updated_at
-- )
-- SELECT 
--     project_id::uuid, publication_id::uuid,
--     project_number, publication_number,
--     title, publication_date, publication_type,
--     project_type, process_type, order_type,
--     canton, city, postal_code,
--     submission_deadline,
--     winner_name, award_amount, award_currency,
--     number_of_submissions, award_decision_date,
--     created_at, updated_at
-- FROM simap_projects_old
-- ON CONFLICT DO NOTHING;

-- Nach erfolgreicher Migration:
-- DROP TABLE simap_projects_old;

-- ============================================================================
-- Kommentare
-- ============================================================================

COMMENT ON TABLE projects IS 'SIMAP Ausschreibungen und Zuschläge';
COMMENT ON COLUMN projects.simap_project_id IS 'UUID des Projekts auf SIMAP';
COMMENT ON COLUMN projects.simap_publication_id IS 'UUID der spezifischen Publikation';
COMMENT ON COLUMN projects.pub_type IS 'tender, award, revocation, abandonment, correction, etc.';
COMMENT ON COLUMN projects.process_type IS 'open (öffentlich), selective, invitation, direct';
COMMENT ON COLUMN projects.order_type IS 'construction (Bau), service (Dienstleistung), supply (Lieferung)';
COMMENT ON COLUMN projects.raw_json IS 'Vollständige API Response für spätere Extraktion';

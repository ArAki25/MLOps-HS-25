-- SIMAP Projects Datenbank-Schema für Supabase
--
-- Dieses Schema wird automatisch von db_importer.py erstellt,
-- kann aber auch manuell im Supabase SQL Editor ausgeführt werden.

-- ============================================================================
-- Haupttabelle: simap_projects
-- ============================================================================

CREATE TABLE IF NOT EXISTS simap_projects (
    -- Primary Keys
    project_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,

    -- IDs & Nummern
    project_number TEXT,
    publication_number TEXT,

    -- Basis-Informationen
    title TEXT,
    description TEXT,
    publication_date TIMESTAMP,
    publication_type TEXT,  -- tender, award, cancellation, change
    project_type TEXT,
    project_subtype TEXT,

    -- Auftraggeber
    contracting_authority TEXT,

    -- Ort
    canton TEXT,  -- ZH, BE, GE, etc.
    city TEXT,
    postal_code TEXT,
    country TEXT,

    -- Fristen & Prozess
    submission_deadline TIMESTAMP,
    process_type TEXT,  -- open, selective, invitation
    lots_type TEXT,

    -- Geschätzte Preise
    estimated_amount NUMERIC,
    estimated_currency TEXT,

    -- Award-Informationen (Zuschläge)
    award_decision_date TIMESTAMP,
    number_of_submissions INTEGER,
    winner_name TEXT,
    winner_city TEXT,
    winner_canton TEXT,
    winner_postal_code TEXT,
    winner_country TEXT,
    award_amount NUMERIC,
    award_currency TEXT,
    award_vat_type TEXT,

    -- Klassifizierungen (CPV, BKP, etc.)
    cpv_code TEXT,
    additional_cpv_codes TEXT,
    bkp_codes TEXT,
    ebkph_codes TEXT,
    ebkpt_codes TEXT,
    npk_codes TEXT,

    -- Weitere Details
    order_type TEXT,
    construction_type TEXT,
    construction_category TEXT,
    creation_language TEXT,  -- de, fr, it, en

    -- Metadaten
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Primary Key Constraint
    PRIMARY KEY (project_id, publication_id)
);

-- ============================================================================
-- Indizes für Performance
-- ============================================================================

-- Zeitbasierte Abfragen (wichtig für tägliche Updates)
CREATE INDEX IF NOT EXISTS idx_simap_publication_date
    ON simap_projects(publication_date DESC);

-- Filter nach Typ
CREATE INDEX IF NOT EXISTS idx_simap_publication_type
    ON simap_projects(publication_type);

CREATE INDEX IF NOT EXISTS idx_simap_process_type
    ON simap_projects(process_type);

-- Geografische Filter
CREATE INDEX IF NOT EXISTS idx_simap_canton
    ON simap_projects(canton);

-- Sprache
CREATE INDEX IF NOT EXISTS idx_simap_creation_language
    ON simap_projects(creation_language);

-- Volltext-Suche für ML-Feature-Extraction
CREATE INDEX IF NOT EXISTS idx_simap_title_search
    ON simap_projects USING GIN(to_tsvector('german', COALESCE(title, '')));

CREATE INDEX IF NOT EXISTS idx_simap_description_search
    ON simap_projects USING GIN(to_tsvector('german', COALESCE(description, '')));

-- ============================================================================
-- Nützliche Views für ML-Training
-- ============================================================================

-- View: Nur Ausschreibungen (tenders) mit allen wichtigen Features
CREATE OR REPLACE VIEW simap_tenders AS
SELECT
    project_id,
    publication_id,
    title,
    description,
    publication_date,
    canton,
    city,
    process_type,
    submission_deadline,
    estimated_amount,
    estimated_currency,
    cpv_code,
    construction_type,
    creation_language
FROM simap_projects
WHERE publication_type = 'tender'
AND title IS NOT NULL
AND description IS NOT NULL;

-- View: Nur Zuschläge (awards) für Training
CREATE OR REPLACE VIEW simap_awards AS
SELECT
    project_id,
    publication_id,
    title,
    description,
    canton,
    award_decision_date,
    winner_name,
    winner_canton,
    award_amount,
    award_currency,
    number_of_submissions,
    cpv_code
FROM simap_projects
WHERE publication_type = 'award'
AND award_amount IS NOT NULL;

-- View: Ausschreibungen mit zugehörigen Zuschlägen (für Matching-Analyse)
CREATE OR REPLACE VIEW simap_tender_award_pairs AS
SELECT
    t.project_id,
    t.title as tender_title,
    t.description as tender_description,
    t.publication_date as tender_date,
    t.estimated_amount as tender_estimated,
    a.award_amount as award_actual,
    a.winner_name,
    a.number_of_submissions,
    t.canton,
    t.cpv_code
FROM simap_projects t
LEFT JOIN simap_projects a
    ON t.project_id = a.project_id
    AND a.publication_type = 'award'
WHERE t.publication_type = 'tender';

-- ============================================================================
-- Nützliche Queries für ML-Pipeline
-- ============================================================================

-- Kommentar: Neue Projekte der letzten 24h holen
-- SELECT * FROM simap_projects
-- WHERE publication_date >= NOW() - INTERVAL '24 hours'
-- ORDER BY publication_date DESC;

-- Kommentar: Projekte für spezifischen Kanton und Typ
-- SELECT * FROM simap_projects
-- WHERE canton = 'ZH'
-- AND publication_type = 'tender'
-- AND submission_deadline > NOW();

-- Kommentar: Volltext-Suche für Keywords (z.B. "Software", "IT")
-- SELECT project_id, title, description
-- FROM simap_projects
-- WHERE to_tsvector('german', COALESCE(title, '') || ' ' || COALESCE(description, ''))
--       @@ to_tsquery('german', 'Software | IT');

-- ============================================================================
-- Row Level Security (RLS) - Optional für Multi-User Setup
-- ============================================================================

-- Aktiviere RLS wenn du verschiedene User-Rollen hast
-- ALTER TABLE simap_projects ENABLE ROW LEVEL SECURITY;

-- Beispiel Policy: Alle können lesen, nur Service-Account kann schreiben
-- CREATE POLICY "Public read access" ON simap_projects
--     FOR SELECT USING (true);

-- CREATE POLICY "Service account write access" ON simap_projects
--     FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

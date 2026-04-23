-- Exportiert aus Remote schema_migrations (version=20260414150037, name=create_archive_table)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

CREATE TABLE IF NOT EXISTS archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- SIMAP IDs
  simap_project_id TEXT NOT NULL,
  simap_publication_id TEXT NOT NULL UNIQUE,
  project_number TEXT,
  publication_number TEXT,

  -- Titel & Beschreibung
  title_de TEXT,
  title_fr TEXT,
  description_de TEXT,
  description_fr TEXT,

  -- Daten
  publication_date DATE NOT NULL,
  submission_deadline TIMESTAMPTZ,
  offer_opening_date TIMESTAMPTZ,
  award_decision_date DATE,

  -- Beschaffungsstelle
  proc_office_name_de TEXT,
  proc_office_name_fr TEXT,
  proc_office_id TEXT,
  proc_office_street TEXT,
  proc_office_city TEXT,
  proc_office_postal_code VARCHAR,
  proc_office_canton VARCHAR,
  proc_office_country VARCHAR DEFAULT 'CH',
  proc_office_email TEXT,
  proc_office_phone VARCHAR,
  proc_office_contact TEXT,

  -- Ort
  canton VARCHAR,
  city TEXT,
  postal_code VARCHAR,
  country VARCHAR DEFAULT 'CH',

  -- Klassifikation
  pub_type VARCHAR NOT NULL,
  project_type VARCHAR,
  project_subtype VARCHAR,
  process_type VARCHAR,
  order_type VARCHAR,
  lots_type VARCHAR,
  corrected BOOLEAN DEFAULT FALSE,

  -- CPV / BKP
  cpv_code_main VARCHAR,
  cpv_codes TEXT[] DEFAULT '{}',
  bkp_codes TEXT[] DEFAULT '{}',
  oag_codes TEXT[] DEFAULT '{}',

  -- Zuschlag
  winner_name TEXT,
  winner_id TEXT,
  winner_street TEXT,
  winner_city TEXT,
  winner_canton VARCHAR,
  winner_postal_code VARCHAR,
  award_amount NUMERIC,
  award_currency VARCHAR DEFAULT 'CHF',
  award_vat_type VARCHAR,
  number_of_submissions INTEGER,
  all_winners JSONB,
  award_justification_de TEXT,

  -- Lose
  lots_count INTEGER DEFAULT 0,

  -- Empfänger
  recipient_name TEXT,
  recipient_city TEXT,
  recipient_canton VARCHAR,

  -- Flags
  publication_ted BOOLEAN DEFAULT FALSE,
  state_contract_area BOOLEAN DEFAULT FALSE,
  creation_language VARCHAR,

  -- Referenz-Publikation
  referencing_pub_id TEXT,
  referencing_pub_type VARCHAR,
  referencing_pub_date DATE,
  referencing_pub_number VARCHAR,

  -- Bau
  construction_type VARCHAR,
  construction_category VARCHAR,

  -- Rechtsmittel & Diverses
  remedies_notice_de TEXT,
  total_price_selection VARCHAR,
  has_project_documents BOOLEAN DEFAULT FALSE,

  -- Raw-Daten (alle Informationen)
  raw_json_search JSONB,
  raw_json_detail JSONB,

  -- Meta
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  detail_fetched_at TIMESTAMPTZ,
  detail_fetch_error TEXT,
  content_hash TEXT,
  last_checked_at TIMESTAMPTZ
);

-- Performance-Indexes
CREATE INDEX IF NOT EXISTS idx_archive_simap_project_id ON archive (simap_project_id);
CREATE INDEX IF NOT EXISTS idx_archive_publication_date ON archive (publication_date);
CREATE INDEX IF NOT EXISTS idx_archive_pub_type ON archive (pub_type);
CREATE INDEX IF NOT EXISTS idx_archive_canton ON archive (canton);
CREATE INDEX IF NOT EXISTS idx_archive_cpv_main ON archive (cpv_code_main);
CREATE INDEX IF NOT EXISTS idx_archive_order_type ON archive (order_type);
CREATE INDEX IF NOT EXISTS idx_archive_process_type ON archive (process_type);
CREATE INDEX IF NOT EXISTS idx_archive_detail_pending ON archive (detail_fetched_at) WHERE detail_fetched_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_archive_award_amount ON archive (award_amount) WHERE award_amount IS NOT NULL;

-- RLS deaktiviert fuer Service-Role-Zugriff (Einmal-Skript)
ALTER TABLE archive ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_access" ON archive FOR ALL USING (true) WITH CHECK (true);

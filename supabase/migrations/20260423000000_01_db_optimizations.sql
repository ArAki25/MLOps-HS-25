-- Exportiert aus Remote schema_migrations (version=20260423, name=01_db_optimizations)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ===========================================================================
-- DB Performance & Security Optimierungen (2026-04-23)
-- ===========================================================================
-- Auditbefund (via Supabase MCP, pg_indexes, pg_policies, Supabase advisors):
--
-- POSITIV (keine Aenderung noetig):
--   * public.embeddings hat HNSW-Index archive_emb_vec_hnsw (m=16, ef=64) auf
--     embedding vector_cosine_ops. Guter Default fuer 1024-d pgvector.
--   * public.embeddings hat unique-partial-Indizes archive_emb_proj_uniq /
--     archive_emb_archive_uniq (source-abhaengig). Deckt die JOIN-Muster in
--     ui.refresh_user_taste und ui.recommend_projects_for_user_v2 sauber ab.
--   * ui.projects_ui hat 22 Indizes inkl. btree auf canton/order_type/
--     process_type/pub_type/project_subtype/cpv_code_main und gin-tsvector
--     auf title_de+description_de. Der Suchpfad in get_projects_paginated
--     (search + filter + order by publication_date) ist indexgedeckt.
--   * Migration 20260421091130_20260421_01_likes_only.sql ist LIVE (version 20260421091130).
--     Likes-only ist auf DB-Ebene sauber durchgezogen (CHECK rating IS NULL
--     OR rating = 1, n_dislikes entfernt, refresh_user_taste neu geschrieben).
--   * ui.user_tender_ratings hat unique (user_id, tender_id, source) - deckt
--     user_id-Prefix-Queries bereits als Index-Scan ab.
--
-- VERBESSERUNGEN (dieser Migration):
--   1. ui.user_profiles und ui.user_tender_ratings haben JEWEILS ZWEI
--      identische RLS-Policies ("*_own" und "users manage own *"). Jede
--      Row-Pruefung evaluiert beide Policies (OR-Verknuepfung) - unnoetig.
--      Wir konsolidieren auf EINE Policy pro Tabelle.
--   2. Alle RLS-Policies in ui.* rufen auth.uid() pro Zeile erneut auf
--      (Supabase-Advisor lint 0003 auth_rls_initplan). Wir ersetzen durch
--      (SELECT auth.uid()), damit der Planner den Wert einmal cached.
--   3. ui.favorites hat RLS enabled, aber KEINE Policy (= alles blockiert
--      ausser service_role). Wir ergaenzen eine own-row Policy + Indizes
--      auf user_id und created_at (die App filtert/sortiert so).
--   4. ui.user_simap_ids hat Foreign-Key auf user_id ohne Covering-Index
--      (Supabase-Advisor lint 0001 unindexed_foreign_keys). Behoben.
--   5. Eigene Funktionen (refresh_user_taste, recommend_projects_for_user_v2,
--      sample_projects_for_rating, tg_user_tender_ratings_refresh_taste)
--      haben mutable search_path (lint 0011). Wir fixieren search_path auf
--      ui, public, extensions, pg_temp.
--
-- NICHT angefasst:
--   * Unused-Index-Hinweise fuer projects_ui/public.projects - die Tabelle
--     ist erst wenig abgefragt worden, Indizes werden bei realer Last
--     gebraucht. Kein Drop ohne Produktions-Beobachtung.
--   * ui.projects_ui hat RLS deaktiviert (lint 0013). Das ist bewusste,
--     read-only Referenz-Daten fuer die UI. Falls gewuenscht, spaeter
--     separat RLS + "SELECT true" Policy aktivieren.
--   * public.archive service_role_full_access (lint 0024): beabsichtigter
--     Service-Role Escape. Nicht aendern ohne Team-Entscheid.
-- ===========================================================================
-- Hinweis: Kein CREATE INDEX CONCURRENTLY hier — Supabase fuehrt Migrations-SQL
-- typischerweise in einer Transaktion aus; CONCURRENTLY waere dann ungueltig.
-- Auf ui.favorites / user_simap_ids ist ein kurzer Lock beim Indexaufbau ok.

-- ---------------------------------------------------------------------------
-- 1+2. Konsolidiere RLS-Policies und wrappe auth.uid() in (SELECT auth.uid())
-- ---------------------------------------------------------------------------

-- ui.user_profiles
DROP POLICY IF EXISTS "users manage own profile" ON ui.user_profiles

DROP POLICY IF EXISTS user_profiles_own ON ui.user_profiles

CREATE POLICY user_profiles_own ON ui.user_profiles
  FOR ALL
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id)

-- ui.user_tender_ratings
DROP POLICY IF EXISTS "users manage own ratings" ON ui.user_tender_ratings

DROP POLICY IF EXISTS ratings_own ON ui.user_tender_ratings

CREATE POLICY ratings_own ON ui.user_tender_ratings
  FOR ALL
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id)

-- ui.user_simap_ids
DROP POLICY IF EXISTS simap_ids_own ON ui.user_simap_ids

CREATE POLICY simap_ids_own ON ui.user_simap_ids
  FOR ALL
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id)

-- ui.user_taste_vectors (nur SELECT - wird ueber RPC/Trigger beschrieben)
DROP POLICY IF EXISTS user_taste_vectors_self_read ON ui.user_taste_vectors

CREATE POLICY user_taste_vectors_self_read ON ui.user_taste_vectors
  FOR SELECT
  USING ((SELECT auth.uid()) = user_id)

-- ---------------------------------------------------------------------------
-- 3. ui.favorites - fehlende RLS-Policy + passende Indizes
-- ---------------------------------------------------------------------------
-- Einige Remotes hatten ui.favorites nur mit (id, created_at) angelegt.
-- Die App (simap_ui) benoetigt user_id + project_id wie bei PostgREST-Upserts.
ALTER TABLE ui.favorites
  ADD COLUMN IF NOT EXISTS user_id uuid

ALTER TABLE ui.favorites
  ADD COLUMN IF NOT EXISTS project_id uuid

DROP POLICY IF EXISTS favorites_own ON ui.favorites

CREATE POLICY favorites_own ON ui.favorites
  FOR ALL
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id)

-- ---------------------------------------------------------------------------
-- 3b + 4. Indizes (ohne CONCURRENTLY, siehe Kopfkommentar)
-- ---------------------------------------------------------------------------

-- ui.favorites.user_id + created_at (Query: WHERE user_id=$1 ORDER BY created_at DESC)
CREATE INDEX IF NOT EXISTS favorites_user_id_created_at_idx
  ON ui.favorites (user_id, created_at DESC)

-- ui.favorites (user_id, project_id) - fuer remove_favorite-DELETE
CREATE INDEX IF NOT EXISTS favorites_user_project_idx
  ON ui.favorites (user_id, project_id)

-- ui.user_simap_ids.user_id - fuer Foreign-Key + DELETE-by-user
CREATE INDEX IF NOT EXISTS user_simap_ids_user_id_idx
  ON ui.user_simap_ids (user_id)

-- ---------------------------------------------------------------------------
-- 5. search_path auf unseren eigenen Funktionen fixieren
-- ---------------------------------------------------------------------------

ALTER FUNCTION ui.refresh_user_taste(uuid)
  SET search_path = ui, public, extensions, pg_temp

ALTER FUNCTION ui.tg_user_tender_ratings_refresh_taste()
  SET search_path = ui, public, extensions, pg_temp

ALTER FUNCTION ui.recommend_projects_for_user_v2(uuid, integer)
  SET search_path = ui, public, extensions, pg_temp

ALTER FUNCTION ui.sample_projects_for_rating(uuid, integer)
  SET search_path = ui, public, extensions, pg_temp

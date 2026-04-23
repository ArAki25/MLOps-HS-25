-- ============================================================================
-- ui.user_profiles: Multi-Canton Support
--
-- Adds a text[] column `preferred_cantons` so users can select multiple
-- cantons in their profile. Keeps the legacy `canton` column populated with
-- the first element for backward compatibility with existing recommendation
-- RPCs (e.g. ui.recommend_projects_for_user_v2) that still rely on it.
--
-- Hinweis: Dateiname muss eindeutigen Zeitstempel haben (nicht 20260423_02),
-- sonst kollidiert die Supabase-Migrationsversion mit 20260423_01.
-- ============================================================================

alter table ui.user_profiles
    add column if not exists preferred_cantons text[] default '{}'::text[];

-- Backfill: wenn bisher nur `canton` gesetzt war, uebernehme den Wert
-- als einziges Element in das neue Array.
update ui.user_profiles
   set preferred_cantons = array[canton]
 where canton is not null
   and canton <> ''
   and (preferred_cantons is null or cardinality(preferred_cantons) = 0);

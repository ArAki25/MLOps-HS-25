-- Exportiert aus Remote schema_migrations (version=20260418122707, name=drop_broken_sync_to_projects_ui_trigger)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- Entfernt den kaputten Trigger + Function, die versucht in die nicht mehr existierende
-- public.projects_ui zu schreiben. Der Sync nach ui.projects_ui erfolgt weiterhin
-- durch trg_sync_to_ui -> public.sync_project_to_ui() (schreibt explizit in ui.projects_ui).
DROP TRIGGER IF EXISTS sync_projects_trigger ON public.projects;
DROP FUNCTION IF EXISTS public.sync_to_projects_ui();

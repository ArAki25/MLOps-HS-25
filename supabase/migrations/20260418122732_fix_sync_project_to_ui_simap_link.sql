-- Exportiert aus Remote schema_migrations (version=20260418122732, name=fix_sync_project_to_ui_simap_link)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- Fix: sync_project_to_ui() versuchte NEW.simap_link zu lesen, aber diese Spalte
-- existiert nur in ui.projects_ui, nicht in public.projects. Wir berechnen den Link
-- direkt aus simap_project_id.
CREATE OR REPLACE FUNCTION public.sync_project_to_ui()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, ui
AS $function$
BEGIN
    INSERT INTO ui.projects_ui (
        id,
        simap_project_id,
        project_number,
        publication_number,
        title_de,
        title_fr,
        description_de,
        description_fr,
        canton,
        city,
        country,
        process_type,
        order_type,
        pub_type,
        publication_date,
        submission_deadline,
        cpv_code_main,
        proc_office_name_de,
        proc_office_name_fr,
        proc_office_email,
        proc_office_phone,
        award_amount,
        award_currency,
        winner_name,
        winner_city,
        simap_link
    )
    VALUES (
        NEW.id,
        NEW.simap_project_id,
        NEW.project_number,
        NEW.publication_number,
        NEW.title_de,
        NEW.title_fr,
        NEW.description_de,
        NEW.description_fr,
        NEW.canton,
        NEW.city,
        NEW.country,
        NEW.process_type,
        NEW.order_type,
        NEW.pub_type,
        NEW.publication_date,
        NEW.submission_deadline,
        NEW.cpv_code_main,
        NEW.proc_office_name_de,
        NEW.proc_office_name_fr,
        NEW.proc_office_email,
        NEW.proc_office_phone,
        NEW.award_amount,
        NEW.award_currency,
        NEW.winner_name,
        NEW.winner_city,
        CASE WHEN NEW.simap_project_id IS NOT NULL
             THEN 'https://www.simap.ch/de/project-detail/' || NEW.simap_project_id::text
             ELSE NULL
        END
    )
    ON CONFLICT (id) DO UPDATE SET
        title_de = EXCLUDED.title_de,
        title_fr = EXCLUDED.title_fr,
        description_de = EXCLUDED.description_de,
        description_fr = EXCLUDED.description_fr,
        canton = EXCLUDED.canton,
        city = EXCLUDED.city,
        country = EXCLUDED.country,
        process_type = EXCLUDED.process_type,
        order_type = EXCLUDED.order_type,
        pub_type = EXCLUDED.pub_type,
        publication_date = EXCLUDED.publication_date,
        submission_deadline = EXCLUDED.submission_deadline,
        cpv_code_main = EXCLUDED.cpv_code_main,
        proc_office_name_de = EXCLUDED.proc_office_name_de,
        proc_office_name_fr = EXCLUDED.proc_office_name_fr,
        proc_office_email = EXCLUDED.proc_office_email,
        proc_office_phone = EXCLUDED.proc_office_phone,
        award_amount = EXCLUDED.award_amount,
        award_currency = EXCLUDED.award_currency,
        winner_name = EXCLUDED.winner_name,
        winner_city = EXCLUDED.winner_city,
        simap_link = EXCLUDED.simap_link;

    RETURN NEW;
END;
$function$;

-- Row Level Security.
-- The backend connects as the database owner (bypasses RLS) and is the only writer.
-- The web panel reads through Supabase Realtime only, as role `authenticated`.
-- Everything else exposed by PostgREST is closed: RLS enabled, no policies.

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'parcels', 'signals', 'photos', 'applications', 'status_transitions', 'events',
    'telegram_users', 'subscriptions', 'knowledge_questions', 'ndvi_scans',
    'tg_processed_updates', 'geocode_cache', 'alembic_version'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
      EXECUTE format('REVOKE ALL ON public.%I FROM anon', t);
    END IF;
  END LOOP;
END $$;

-- Realtime needs SELECT for the subscribed role.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['events', 'signals', 'parcels'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'inspector_read_' || t, t);
    EXECUTE format(
      'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (true)', 'inspector_read_' || t, t
    );
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
  END LOOP;
END $$;

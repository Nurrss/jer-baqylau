-- Private bucket for photos. No storage policies: only the backend (service role)
-- reads/writes objects; browsers get short-lived signed URLs.
-- Skipped automatically on a plain PostGIS database (no `storage` schema).
DO $$
BEGIN
  IF to_regclass('storage.buckets') IS NOT NULL THEN
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    VALUES ('photos', 'photos', false, 15728640, ARRAY['image/jpeg', 'image/png', 'image/webp'])
    ON CONFLICT (id) DO UPDATE SET public = false;
  END IF;
END $$;

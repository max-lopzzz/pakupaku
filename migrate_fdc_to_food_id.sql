-- Run once against the Neon production database, after deploying the code
-- that expects food_id. Existing integer fdc_ids stringify.
--
-- Idempotent: each block is a no-op if fdc_id has already been renamed, so
-- re-running the script (or running it against a fresh DB that never had
-- fdc_id) is safe.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'food_logs' AND column_name = 'fdc_id') THEN
    ALTER TABLE food_logs ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
    ALTER TABLE food_logs RENAME COLUMN fdc_id TO food_id;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'recipe_ingredients' AND column_name = 'fdc_id') THEN
    ALTER TABLE recipe_ingredients ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
    ALTER TABLE recipe_ingredients RENAME COLUMN fdc_id TO food_id;
  END IF;
END $$;

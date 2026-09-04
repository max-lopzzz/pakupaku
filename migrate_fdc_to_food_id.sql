-- Run once against the Neon production database, after deploying the code
-- that expects food_id. Existing integer fdc_ids stringify.
ALTER TABLE food_logs           ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
ALTER TABLE food_logs           RENAME COLUMN fdc_id TO food_id;
ALTER TABLE recipe_ingredients  ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
ALTER TABLE recipe_ingredients  RENAME COLUMN fdc_id TO food_id;

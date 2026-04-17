-- Migration: rename fdc_id → spoonacular_id in food_logs and recipe_ingredients
-- Run once against your production database.

ALTER TABLE food_logs
  RENAME COLUMN fdc_id TO spoonacular_id;

ALTER TABLE recipe_ingredients
  RENAME COLUMN fdc_id TO spoonacular_id;

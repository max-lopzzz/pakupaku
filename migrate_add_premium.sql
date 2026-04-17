-- Migration: add is_premium column to users table
-- Run once against your production database.

ALTER TABLE users ADD COLUMN is_premium BOOLEAN NOT NULL DEFAULT FALSE;

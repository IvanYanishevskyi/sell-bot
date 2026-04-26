-- Migration: Add price levels for volume-based discounts
-- This adds multiple price columns to support discount levels at 200k, 150k, 100k volumes

-- First, create a new table structure with price levels
CREATE TABLE IF NOT EXISTS price_items_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price_version_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    base_price NUMERIC NOT NULL,                    -- Base price without VAT
    price_200k NUMERIC NOT NULL,                    -- Price at 200k volume
    discount_200k_percent NUMERIC DEFAULT 0,        -- Discount % at 200k
    price_150k NUMERIC NOT NULL,                    -- Price at 150k volume
    discount_150k_percent NUMERIC DEFAULT 0,        -- Discount % at 150k
    price_100k NUMERIC NOT NULL,                    -- Price at 100k volume
    discount_100k_percent NUMERIC DEFAULT 0,        -- Discount % at 100k
    currency TEXT NOT NULL DEFAULT 'UAH',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (price_version_id) REFERENCES price_versions(id) ON DELETE CASCADE,
    UNIQUE(price_version_id, sku)
);

-- Migrate existing data (if any)
INSERT INTO price_items_new (
    id, price_version_id, sku, name, base_price,
    price_200k, discount_200k_percent,
    price_150k, discount_150k_percent,
    price_100k, discount_100k_percent,
    currency, is_active, created_at, updated_at
)
SELECT
    id, price_version_id, sku, name, price as base_price,
    price as price_200k, 0 as discount_200k_percent,
    price as price_150k, 0 as discount_150k_percent,
    price as price_100k, 0 as discount_100k_percent,
    currency, is_active, created_at, updated_at
FROM price_items;

-- Drop old table
DROP TABLE IF EXISTS price_items;

-- Rename new table to original name
ALTER TABLE price_items_new RENAME TO price_items;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_price_items_sku ON price_items(sku);
CREATE INDEX IF NOT EXISTS idx_price_items_is_active ON price_items(is_active);
CREATE INDEX IF NOT EXISTS idx_price_items_updated_at ON price_items(updated_at);
CREATE INDEX IF NOT EXISTS idx_price_items_version_id ON price_items(price_version_id);

-- Add price_level to clients table
ALTER TABLE clients ADD COLUMN price_level TEXT DEFAULT 'base' CHECK (price_level IN ('base', '200k', '150k', '100k'));

-- Update schema version (if tracking)
INSERT INTO schema_migrations (version, applied_at) VALUES ('2026-04-24-price-levels', CURRENT_TIMESTAMP);

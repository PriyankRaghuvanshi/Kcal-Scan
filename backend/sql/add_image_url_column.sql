-- Add optional image_url column to chain_menu_items.
-- Run once in Supabase SQL editor. After this, sync passes through any
-- image_url field on per-chain seed files.
--
-- image_url should be a publicly-fetchable HTTPS URL pointing at a
-- thumbnail-quality (≥240px wide) JPG/PNG/WebP of the dish. NULL when
-- no curated image is available — the mobile UI renders no thumbnail.

ALTER TABLE public.chain_menu_items
    ADD COLUMN IF NOT EXISTS image_url TEXT;

-- Optional integrity check: ensure URLs look like https when present
ALTER TABLE public.chain_menu_items
    DROP CONSTRAINT IF EXISTS chain_menu_items_image_url_https;
ALTER TABLE public.chain_menu_items
    ADD CONSTRAINT chain_menu_items_image_url_https
    CHECK (image_url IS NULL OR image_url ~* '^https://');

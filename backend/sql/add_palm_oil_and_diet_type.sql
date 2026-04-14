-- Add palm-oil + diet-type columns to chain_menu_items.
-- Run once in Supabase SQL editor. Idempotent.
--
-- Without these columns the mobile palm-oil badge and veg/vegan/non-veg
-- classifications have no source of truth in Supabase, even though every
-- seed file on disk already carries the data.

ALTER TABLE public.chain_menu_items
    ADD COLUMN IF NOT EXISTS contains_palm_oil BOOLEAN;

ALTER TABLE public.chain_menu_items
    ADD COLUMN IF NOT EXISTS diet_type TEXT;

-- Constrain diet_type to the three values the mobile app understands,
-- NULL allowed for legacy rows.
ALTER TABLE public.chain_menu_items
    DROP CONSTRAINT IF EXISTS chain_menu_items_diet_type_valid;
ALTER TABLE public.chain_menu_items
    ADD CONSTRAINT chain_menu_items_diet_type_valid
    CHECK (diet_type IS NULL OR diet_type IN ('non_veg', 'vegetarian', 'vegan'));

-- Fix: chain_menu_items has FK to chain_registry. Insert parent rows for taco_bell and panera.
-- Run in Supabase SQL Editor. chain_registry has required display_name (NOT NULL).

insert into public.chain_registry (chain_key, display_name)
values
  ('taco_bell', 'Taco Bell'),
  ('panera', 'Panera Bread')
on conflict (chain_key) do update set display_name = excluded.display_name;

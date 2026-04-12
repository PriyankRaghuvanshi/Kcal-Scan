# Chain menu seed files (Supabase sync)

Seed files are named `{chain_key}_{market_tag}.json` (lowercase), e.g.:

- `chipotle_us.json` — Chipotle (US)
- `faasos_in.json` — Faasos (IN)

Each file must be a JSON object with:

- **`items`** (required): array of menu item dicts with at least `item_name`, `estimated_calories`, `estimated_protein_g`, and optionally `estimated_carbs_g`, `estimated_fat_g`, `confidence`.
- **`brand_name`** (optional): display name.
- **`source_type`** (optional): e.g. `seed_ingestion`.
- **`source_url`** (optional): URL.
- **`store_name_variants`** (optional): list of name variants for matching.

Sync loads from `backend/data/chains/` via `chain_menu_supabase_sync.sync_chain_menu_to_supabase(chain_key, market_tag)`.

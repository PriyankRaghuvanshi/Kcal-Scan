# Rollout: Taco Bell (US) + Panera (US)

Same pattern as Chipotle + Faasos. Use this checklist after seed files are in place.

## 1. Seed finalization

- **Paths:** `backend/data/chains/taco_bell_us.json`, `backend/data/chains/panera_us.json`
- Ensure each has: `brand_name`, `source_type`, `source_url`, `store_name_variants`, and **`items`** array.
- Each item: `item_name`, `estimated_calories`, `estimated_protein_g`, and optionally `estimated_carbs_g`, `estimated_fat_g`, `confidence`.
- For default fitness ordering, include at least one strong “protein rescue” item (e.g. Power Menu Bowl for Taco Bell, Green Goddess Cobb for Panera) and one heavier item so sort puts the better one first.
- Sync will derive `item_key` from `item_name` and add `protein_density_score` / `fat_loss_fit_score` if missing.

## 2. Rollout order

1. Sync **Taco Bell** first: `sync_chain_menu_to_supabase("taco_bell", "US")`.
2. Sync **Panera** second: `sync_chain_menu_to_supabase("panera", "US")`.
3. Then run enrichment and Supabase checks.

## 3. Sync verification (Supabase)

After sync, run in SQL Editor:

```sql
select chain_key, market_tag, item_key, item_name, estimated_protein_g, estimated_calories
from public.chain_menu_items
where chain_key in ('taco_bell', 'panera') and market_tag = 'US'
order by chain_key, item_key;
```

- Expect rows for both chains; `item_key` and `item_name` populated; counts match seed (e.g. 5 Taco Bell, 5 Panera if using provided seeds).

## 4. Enrichment verification

Use place names that match chain registry:

- **Taco Bell:** e.g. `"Taco Bell – Times Square"` (or any name containing “taco bell”), `market_tag="US"`.
- **Panera:** e.g. `"Panera Bread Bakery Cafe"`, `market_tag="US"`.

Check:

- `enriched` is not `None`.
- `matched_chain_key` is `"taco_bell"` or `"panera"`.
- `chain_menu_store == "supabase"`.
- `chain_menu_item_count_for_match > 0`.
- `supabase_chain_candidates` non-empty; each candidate has `menu_item_source == "ingested_chain_item"`, `profile_source == "chain_menu_supabase"`, `specificity_tier == "exact_menu_match"`.
- `top_menu_item` / `top_menu_items` / `best_menu_items` reflect fitness ordering (see section 5).

## 5. Expected top items (default fitness sort)

- **Taco Bell:** Default top should favor **Power Menu Bowl with Chicken** (or Power Menu Bowl with Steak) over heavier burrito and over lighter-but-lower-protein tacos (sort uses fat_loss_fit_score, protein_density_score, protein_g, confidence).
- **Panera:** Default top should favor **Green Goddess Cobb Salad with Chicken** (or Caesar Salad with Chicken) over heavier sandwich/melt (e.g. Bacon Turkey Bravo).

## 6. Tests to run

- **Existing:**  
  `python3 -m unittest test_chain_menu_supabase_sync test_chain_menu_serving_path test_chain_menu_ranking -v`
- **Optional:** Add serving-path tests for Taco Bell and Panera (mock `get_chain_menu_items`, assert `matched_chain_key`, `top_menu_item` name or protein/calorie band) in `test_chain_menu_serving_path.py` if you want the same coverage as Chipotle/Faasos.

## 7. Likely issues

- **Match:** Place name must match registry (e.g. “taco bell”, “panera bread”). If enrichment returns `None`, check `match_chain_key(place_name)`.
- **Market:** Both are US; pass `market_tag="US"` (or ensure `country_code`/vicinity infers US).
- **Seed path:** Filenames must be `taco_bell_us.json` and `panera_us.json` (lowercase market).
- **Sync failure:** If `item_count` is 0, check sync return for `error` (e.g. `no_chain_menu_items_written`, `missing_item_key`) and fix seed or Supabase.

## 8. Success criteria (before Wow! Momo / Haldiram’s / Barbeque Nation)

- [ ] Sync Taco Bell US returns `ok: True`, `item_count` = number of seed items.
- [ ] Sync Panera US returns `ok: True`, `item_count` = number of seed items.
- [ ] Supabase has rows for `chain_key` in (`taco_bell`, `panera`), `market_tag = 'US'`, with non-null `item_key`.
- [ ] Enrichment for a Taco Bell place returns non-None; `matched_chain_key == "taco_bell"`; `top_menu_item` is a strong bowl/protein option (e.g. Power Menu Bowl).
- [ ] Enrichment for a Panera place returns non-None; `matched_chain_key == "panera"`; `top_menu_item` is a salad/bowl (e.g. Green Goddess Cobb).
- [ ] Existing sync and serving-path tests still pass.

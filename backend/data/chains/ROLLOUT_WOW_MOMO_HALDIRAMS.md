# Rollout: Wow! Momo (IN) + Haldiram's (IN)

Same Supabase-backed sync + enrichment pipeline as Chipotle/Faasos/Taco Bell/Panera. India market (IN).

## 1. Seed finalization

- **Paths:** `backend/data/chains/wow_momo_in.json`, `backend/data/chains/haldirams_in.json` (created).
- **Format:** Same as other chains: `brand_name`, `source_type`, `source_url`, `store_name_variants`, **`items`** array. Each item: `item_name`, `estimated_calories`, `estimated_protein_g`, optionally `estimated_carbs_g`, `estimated_fat_g`, `confidence`. No `item_key` needed (sync derives from `item_name`).
- **Wow! Momo:** Seed includes Steamed Chicken Momos, Grilled Chicken Momos (fitness-friendly), and Fried Chicken Momos (heavier) so default sort puts steamed/grilled first.
- **Haldiram's:** Seed includes Tandoori Chicken with Salad, Dal with Roti, Paneer Tikka, and heavier options so default sort favors higher-protein / lighter items.
- Tweak item names or macros in the JSON if you want different menu items; then re-sync.

## 2. Rollout order

1. **Add parent rows in Supabase** (required if `chain_menu_items` has FK to `chain_registry`):
   ```sql
   insert into public.chain_registry (chain_key, display_name)
   values ('wow_momo', 'Wow! Momo'), ('haldirams', 'Haldiram''s')
   on conflict (chain_key) do update set display_name = excluded.display_name;
   ```
2. **Sync Wow! Momo first:** `sync_chain_menu_to_supabase("wow_momo", "IN")` → expect `ok: True`, `item_count` = 5 (or your item count).
3. **Sync Haldiram's second:** `sync_chain_menu_to_supabase("haldirams", "IN")` → same check.
4. Then run Supabase + enrichment checks below.

## 3. Sync verification (Supabase)

After both syncs, in SQL Editor:

```sql
select chain_key, market_tag, item_key, item_name, estimated_protein_g, estimated_calories
from public.chain_menu_items
where chain_key in ('wow_momo', 'haldirams') and market_tag = 'IN'
order by chain_key, market_tag, item_key;
```

- Expect rows for **wow_momo** and **haldirams**, all with non-null `item_key` and `item_name`. Counts match seed (e.g. 5 each).

## 4. Enrichment verification

Use place names that match chain registry (e.g. from `test_mock_chain_places`):

- **Wow! Momo:** `"Wow! Momo – Salt Lake"` (or any name containing “wow momo” / “wow! momo”), `market_tag="IN"`.
- **Haldiram's:** `"Haldiram's Restaurant"` (or “haldiram's” / “haldirams”), `market_tag="IN"`.

Call `enrich_place_with_local_profile(place, market_tag="IN")` for each. Confirm:

- Result is not `None`.
- `matched_chain_key` is `"wow_momo"` or `"haldirams"`.
- `chain_menu_store == "supabase"`, `chain_menu_item_count_for_match > 0`.
- `supabase_chain_candidates` non-empty; each has `menu_item_source == "ingested_chain_item"`, `profile_source == "chain_menu_supabase"`, `specificity_tier == "exact_menu_match"`.
- `top_menu_item` / `top_menu_items` / `best_menu_items` reflect fitness ordering (section 5).

## 5. Expected top items (default fitness sort)

- **Wow! Momo:** Default top should favor **Grilled Chicken Momos** or **Steamed Chicken Momos** (higher protein, better fat_loss_fit_score) over Fried Chicken Momos or pan-fried veg.
- **Haldiram's:** Default top should favor **Tandoori Chicken with Salad** or **Paneer Tikka with Salad** (higher protein / lighter) over heavy Chhole Bhature or Veg Thali.

## 6. Tests to run

- **Existing:**  
  `python3 -m unittest test_chain_menu_supabase_sync test_chain_menu_serving_path test_chain_menu_ranking -v`  
  All should still pass.
- **Optional:** Add in `test_chain_menu_serving_path.py` one test per chain: mock `get_chain_menu_items` for a Wow! Momo and a Haldiram's place, assert `matched_chain_key` and that `top_menu_item` is the intended fitness-friendly item (by name or protein/calorie).

## 7. Likely issues

- **chain_registry FK:** If you get 409 "chain_key not present in chain_registry", run the `INSERT INTO chain_registry (chain_key, display_name)` for `wow_momo` and `haldirams` (step 2).
- **Match:** Place name must match registry aliases (“wow momo”, “wow! momo”, “haldiram's”, “haldirams”). If enrichment is `None`, check `match_chain_key(place_name)`.
- **Market:** Both are IN; pass `market_tag="IN"` or ensure place infers India (e.g. `country_code="IN"`, vicinity in India).
- **Seed path:** Filenames must be `wow_momo_in.json` and `haldirams_in.json` (lowercase `_in`).

## 8. Success criteria (before Barbeque Nation)

- [ ] Sync **wow_momo / IN** returns `ok: True`, `item_count` = seed item count.
- [ ] Sync **haldirams / IN** returns `ok: True`, `item_count` = seed item count.
- [ ] Supabase has rows for `chain_key` in (`wow_momo`, `haldirams`), `market_tag = 'IN'`, non-null `item_key`.
- [ ] Enrichment for a Wow! Momo place is non-None; `matched_chain_key == "wow_momo"`; **top_menu_item** is a steamed/grilled chicken option (e.g. Grilled or Steamed Chicken Momos).
- [ ] Enrichment for a Haldiram's place is non-None; `matched_chain_key == "haldirams"`; **top_menu_item** is a higher-protein/lighter option (e.g. Tandoori Chicken with Salad or Paneer Tikka).
- [ ] Existing sync and serving-path tests still pass.

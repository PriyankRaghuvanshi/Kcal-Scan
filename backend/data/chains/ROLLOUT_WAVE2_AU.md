# Wave 2 AU rollout plan

Same Supabase sync + enrichment pipeline as Wave 1. AU market. Chains: Nando's, KFC, Red Rooster, Hungry Jack's, McDonald's.

## 1. Rollout order

Do them in this order (easiest / lowest-risk first, higher-variance last):

1. **Nando's** — Grilled chicken, clear “best” options; lowest risk of misleading top.
2. **KFC** — Tenders + salad and fillet no mayo in seed; avoid bucket/heavy items.
3. **Red Rooster** — Roast chicken + veggies; leaner option leads.
4. **Hungry Jack's** — Salad + grilled chicken and grilled burger; still burger-heavy so after Nando’s/KFC/Red Rooster.
5. **McDonald's** — Last: most combo/heavy-burger risk; seed favors McChicken no mayo, Hamburger, Filet no tartar.

## 2. Seed finalization

- **Paths:** `nandos_au.json`, `kfc_au.json`, `red_rooster_au.json`, `hungry_jacks_au.json`, `mcdonalds_au.json` under `backend/data/chains/` (all created).
- **Format:** Same as Wave 1: `brand_name`, `source_type`, `source_url`, `store_name_variants`, **`items`** array. Each item: `item_name`, `estimated_calories`, `estimated_protein_g`, optionally `estimated_carbs_g`, `estimated_fat_g`, `confidence`. No `item_key` (sync derives it).
- **Content:** Put the intended default top item first in the seed (or give it the best protein/calorie combo) so the deterministic sort picks it. Avoid combo meals, “bucket”, “feast”, “large fries” as the lead item; prefer single-item or salad/sandwich no mayo style.

## 3. Expected top items by chain

- **Nando's:** Quarter Chicken with Salad or Half Chicken with Broccolini (grilled/protein-forward).
- **KFC:** Original Tenders (3) with Side Salad or Original Fillet Burger, no mayo (not Zinger or bucket).
- **Red Rooster:** Roast Chicken Quarter with Veggies or Chicken Salad Roll (not heavy combo).
- **Hungry Jack's:** Garden Salad with Grilled Chicken Patty or Grilled Chicken Burger, no mayo (not Whopper with Cheese).
- **McDonald's:** McChicken, no mayo or Hamburger (not Big Mac or heavy combo).

## 4. Sync verification

1. **chain_registry:** Insert parent rows for AU chains (if FK exists):
   ```sql
   insert into public.chain_registry (chain_key, display_name)
   values
     ('nandos', 'Nando''s'),
     ('kfc', 'KFC'),
     ('red_rooster', 'Red Rooster'),
     ('hungry_jacks', 'Hungry Jack''s'),
     ('mcdonalds', 'McDonald''s')
   on conflict (chain_key) do update set display_name = excluded.display_name;
   ```
2. **Sync in rollout order:**  
   `sync_chain_menu_to_supabase("nandos", "AU")`, then kfc, red_rooster, hungry_jacks, mcdonalds. Expect `ok: True` and `item_count` = seed count each time.
3. **Supabase check:**
   ```sql
   select chain_key, market_tag, item_key, item_name, estimated_protein_g, estimated_calories
   from public.chain_menu_items
   where market_tag = 'AU' and chain_key in ('nandos','kfc','red_rooster','hungry_jacks','mcdonalds')
   order by chain_key, item_key;
   ```
   All five chains with non-null `item_key` and expected counts.

## 5. Enrichment verification

For each chain, use a place name that matches registry (e.g. “Nando's”, “KFC”, “Red Rooster”, “Hungry Jack's”, “McDonald's” or “Maccas”) and `market_tag="AU"`. Call `enrich_place_with_local_profile(place, market_tag="AU")`. Confirm: non-None; `matched_chain_key` correct; `chain_menu_store == "supabase"`; `chain_menu_item_count_for_match > 0`; `top_menu_item` matches expected (section 3). Optional: add a small script like `verify_enrichment_wave2_au.py` that runs one mock place per chain and prints matched_chain_key, chain_menu_store, top_menu_item.

## 6. Tests to run

- **Existing:** `python3 -m unittest test_chain_menu_supabase_sync test_chain_menu_serving_path test_chain_menu_ranking -v` — must stay green.
- **Status script:** After adding Wave 2 to `chain_menu_status.py` (or a separate Wave 2 list), run it and confirm all five AU chains show [ok].
- **Regression:** Extend `wave1_top_item_regression.py` (or add a Wave 2 regression script) with AU place names and expected top substrings; run after sync and fix any failure.

## 7. Likely issues

- **FK:** If 409 on items insert, add the chain to `chain_registry` with `display_name`.
- **Match:** Place name must match aliases (e.g. “maccas” for McDonald's). Use `market_tag="AU"`.
- **Wrong top:** If a heavy/combo item wins, adjust seed (remove or demote that item, or give the desired item better protein/calorie so sort puts it first).
- **Seed path:** Filenames must be `nandos_au.json`, `kfc_au.json`, `red_rooster_au.json`, `hungry_jacks_au.json`, `mcdonalds_au.json` (lowercase `_au`).

## 8. Wave 2 AU success criteria

- [ ] All five chains synced: `ok: True`, `item_count` = seed count.
- [ ] Supabase has rows for each (chain_key, AU) with non-null `item_key`.
- [ ] Enrichment for a mock place per chain returns non-None; `matched_chain_key` and `chain_menu_store == "supabase"`; **top_menu_item** is the intended default (section 3), not a heavy combo/bucket/Whopper/Big Mac.
- [ ] Existing test suites pass; status/regression scripts updated and passing for Wave 2 AU.

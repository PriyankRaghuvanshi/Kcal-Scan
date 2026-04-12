# Rollout: Barbeque Nation (IN) — cautious

Same Supabase sync + enrichment pipeline. Conservative treatment: grilled/skewer/protein-forward items only; no buffet/unlimited/platter language in seed.

## Part A — Rollout plan

### 1. Seed finalization

- **Path:** `backend/data/chains/barbeque_nation_in.json`.
- **Include:** Grilled / tandoori / skewer items with **portion-style** names (e.g. "Grilled Chicken Tikka (portion)", "Tandoori Chicken (half portion)", "Chicken Seekh Kebab (2 pcs)").
- **Avoid:** "Unlimited", "buffet", "refill", "platter", "full spread", dessert-first items, or anything that implies variable/unlimited portions. Keep items that can be reasonably estimated per portion.
- **Macros:** Use conservative estimates per portion so fitness sort favors high-protein, moderate-calorie options.

### 2. Sync and verify in Supabase

1. **Parent row** (if FK to `chain_registry`):
   ```sql
   insert into public.chain_registry (chain_key, display_name)
   values ('barbeque_nation', 'Barbeque Nation')
   on conflict (chain_key) do update set display_name = excluded.display_name;
   ```
2. **Sync:** `sync_chain_menu_to_supabase("barbeque_nation", "IN")` → expect `ok: True`, `item_count` = seed count.
3. **Verify rows:**
   ```sql
   select chain_key, market_tag, item_key, item_name, estimated_protein_g, estimated_calories
   from public.chain_menu_items
   where chain_key = 'barbeque_nation' and market_tag = 'IN'
   order by item_key;
   ```

### 3. Likely issues

- **409 FK:** Add `barbeque_nation` to `chain_registry` with `display_name` if missing.
- **Match:** Place name must match "barbeque nation" / "bbq nation". Use `market_tag="IN"`.
- **Top item too heavy:** If seed has buffet-style or heavy items, remove or rephrase them; keep only portion-based grilled/protein options.

### 4. Success criteria (rollout-ready)

- Sync returns `ok: True`, `item_count` > 0.
- Supabase has rows for `(barbeque_nation, IN)` with non-null `item_key`.
- Enrichment for a Barbeque Nation place returns non-None; `matched_chain_key == "barbeque_nation"`; `chain_menu_store == "supabase"`.
- **top_menu_item** is a grilled/skewer/protein-forward option (e.g. Grilled Chicken Tikka, Tandoori Chicken, Grilled Fish Tikka), **not** a heavy platter, dessert, or indulgent buffet-style item.

## Part B — Enrichment verification

Run from backend: `python3 scripts/verify_enrichment_barbeque_nation.py`

Inspect: **matched_chain_key**, **chain_menu_store**, **top_menu_item**. Expect conservative, protein-forward top item; interpret failures as in the main doc.

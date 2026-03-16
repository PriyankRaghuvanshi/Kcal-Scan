# Wow! Momo & Haldiram's vegetarian seed fix and retest

Data-fix-and-retest plan so vegetarian spot checks return veg items for Wow! Momo and Haldiram's (IN).

---

## 1. Wow! Momo seed/data fix

**File:** `backend/data/chains/wow_momo_in.json`

**Items to mark vegetarian:** Any **veg momo** item (no chicken/meat).

- **Pan-Fried Veg Momos (6 pcs)** → set `vegetarian_possible: true`, `vegan_possible: true` (veg momos are typically vegan).

**Items to mark non-vegetarian:** All **chicken** items.

- **Steamed Chicken Momos (6 pcs)** → `vegetarian_possible: false`, `vegan_possible: false`
- **Grilled Chicken Momos (6 pcs)** → `vegetarian_possible: false`, `vegan_possible: false`
- **Chicken Momo Bowl with Salad** → `vegetarian_possible: false`, `vegan_possible: false`
- **Fried Chicken Momos (6 pcs)** → `vegetarian_possible: false`, `vegan_possible: false`

**Summary:** One veg item (Pan-Fried Veg Momos) = veg + vegan; all four chicken items = non-veg, non-vegan.

---

## 2. Haldiram's seed/data fix

**File:** `backend/data/chains/haldirams_in.json`

**Items to mark vegetarian:** All **vegetarian** dishes (no chicken/meat).

- **Dal with Roti (2 pcs)** → `vegetarian_possible: true`, `vegan_possible: true` (dal + roti typically no dairy/egg).
- **Chhole with Bhature (1 pc)** → `vegetarian_possible: true`, `vegan_possible: false` (bhature often has dairy).
- **Veg Thali (Light)** → `vegetarian_possible: true`, `vegan_possible: false` (thali may include curd/dairy).
- **Paneer Tikka with Salad** → `vegetarian_possible: true`, `vegan_possible: false` (paneer = cheese).

**Items to mark non-vegetarian:** Chicken item.

- **Tandoori Chicken with Salad** → `vegetarian_possible: false`, `vegan_possible: false`

**Summary:** Four vegetarian items (one vegan: Dal with Roti); one chicken item = non-veg, non-vegan.

---

## 3. Re-sync steps

From the **backend** directory, with Supabase env set:

**Wow! Momo (IN):**
```bash
cd backend && python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
r = sync_chain_menu_to_supabase('wow_momo', 'IN')
print(r)
"
```

**Haldiram's (IN):**
```bash
cd backend && python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
r = sync_chain_menu_to_supabase('haldirams', 'IN')
print(r)
"
```

**Success:** Each prints `{"ok": True, "chain_key": "...", "market_tag": "IN", "item_count": N}` with N = 5 for both seeds.

**One-liner (both chains):**
```bash
cd backend && python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
for key, market in [('wow_momo', 'IN'), ('haldirams', 'IN')]:
    print(key, market, sync_chain_menu_to_supabase(key, market))
"
```

---

## 4. Spot-check rerun

From **backend**:

```bash
cd backend && python3 scripts/spot_check_diet_enrichment.py
```

---

## 5. Expected output after the fix

**Wow! Momo (IN) – vegetarian:**
- `matched_chain_key`: wow_momo
- `chain_menu_store`: supabase
- `diet_filter_applied`: True
- `no_diet_safe_candidates`: **False**
- `top_menu_item`: a **vegetarian** item (e.g. **Pan-Fried Veg Momos (6 pcs)** or the single veg item in the seed).

**Haldiram's (IN) – vegetarian:**
- `matched_chain_key`: haldirams (or haldiram's per registry)
- `chain_menu_store`: supabase
- `diet_filter_applied`: True
- `no_diet_safe_candidates`: **False**
- `top_menu_item`: a **vegetarian** item (e.g. **Dal with Roti (2 pcs)**, **Veg Thali (Light)**, **Paneer Tikka with Salad**, or **Chhole with Bhature (1 pc)** — whichever ranks first by fitness among the veg subset).

---

## 6. Failure interpretation

| What you see | Meaning |
|--------------|--------|
| Wow! Momo or Haldiram's vegetarian still has `no_diet_safe_candidates: True` and `top_menu_item: None` | Supabase still has old rows without the new flags. Re-run the re-sync for that chain; confirm `item_count` > 0; in Supabase `chain_menu_items` check that veg items have `vegetarian_possible = true` for the relevant chain/market. |
| Re-sync prints `ok: False` or `no_seed` / `no_items` | Seed file missing or path wrong. Confirm `backend/data/chains/wow_momo_in.json` and `haldirams_in.json` exist and contain the new `vegetarian_possible` / `vegan_possible` fields. |
| `matched_chain_key` wrong or `Enriched: None` | Chain match or data load issue (e.g. place name, market, or Supabase not returning rows). Not caused by the veg flags; check chain registry and Supabase for that chain/market. |
| Vegetarian top is a chicken item | Non-veg item still has `vegetarian_possible: true` or flags not synced. Re-check seed and re-sync so chicken items have `vegetarian_possible: false`. |

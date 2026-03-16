# KFC vegan fix and diet spot-check retest

Patch-and-retest plan: fix KFC vegan safety via seed flags, re-sync, then re-run diet spot checks.

---

## 1. KFC seed/data fix

**File:** `backend/data/chains/kfc_au.json`

**Change:** Add explicit diet flags to every item so chicken items are excluded for vegetarian/vegan.

**Fields to set per item:**

- `vegetarian_possible`: **false**
- `vegan_possible`: **false**

**Items (all are chicken):**

- Original Tenders (3) with Side Salad  
- Original Fillet Burger, no mayo  
- Zinger Burger, no mayo  
- Twister Wrap (Grilled)  

Each of these must include:

```json
"vegetarian_possible": false,
"vegan_possible": false
```

**Code change:** None. Enrichment already uses `vegetarian_possible` / `vegan_possible` in `_item_safe_for_diet`; the fix is data-only in the seed.

---

## 2. Re-sync step

From the **backend** directory, with Supabase env (e.g. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) set:

```bash
cd backend && python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
r = sync_chain_menu_to_supabase('kfc', 'AU')
print(r)
"
```

**Success:** `{"ok": True, "chain_key": "kfc", "market_tag": "AU", "item_count": 4}` (or your item count).

**If sync fails:** Fix the error (e.g. env, network, Supabase table/RLS), then run the same command again.

---

## 3. Spot-check rerun

From **backend**, run all five diet spot checks (including KFC vegan):

```bash
cd backend && python3 scripts/spot_check_diet_enrichment.py
```

---

## 4. Expected output after the fix

**KFC (AU) – vegan** block should look like:

- `matched_chain_key`: kfc  
- `chain_menu_store`: supabase  
- `diet_filter_applied`: True  
- `no_diet_safe_candidates`: **True**  
- `top_menu_item`: **None**  

**McDonald's (AU) – vegetarian** should be unchanged:

- `top_menu_item`: Hamburger  
- `no_diet_safe_candidates`: False  

Other checks (Wow! Momo, Haldiram's, Nando's) depend on data being available in your environment; if they return `Enriched: None`, run the same spot-check script where chain data is loaded (e.g. with Supabase or fallback data for IN/AU).

---

## 5. Failure interpretation

| What you see | Meaning |
|--------------|--------|
| KFC vegan still has `top_menu_item` = a chicken item (e.g. Tenders) and `no_diet_safe_candidates` = False | Supabase is still serving old rows. Re-run the re-sync command; confirm `item_count` > 0; check that `chain_menu_items` rows for kfc/AU have `vegetarian_possible` and `vegan_possible` set (e.g. in Supabase dashboard). |
| Re-sync prints `ok: False` or `item_count: 0` | Seed not loaded, or Supabase write failed. Check `backend/data/chains/kfc_au.json` exists and has the new flags; check env and Supabase logs. |
| KFC vegan has `top_menu_item`: None but `no_diet_safe_candidates`: False | Logic bug: when there are no diet-safe candidates, both should be set (None and True). Unlikely if only the seed was changed; if it happens, check `local_venue_enrichment` fallback when the filtered list is empty. |
| McDonald's vegetarian changes (e.g. top is no longer Hamburger) | Unrelated regression. Re-run only the McDonald’s check and fix any recent changes to McDonald’s seed or enrichment. |

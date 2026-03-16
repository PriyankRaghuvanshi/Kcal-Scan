# Diet-aware enrichment: real-world spot-check plan

Manual spot checks across five live chain examples to confirm vegetarian/vegan filtering and graceful fallback.

---

## 1. Spot checks

| # | Chain            | Market | Diet preference | What to run |
|---|------------------|--------|-----------------|-------------|
| 1 | **McDonald's**   | AU     | vegetarian      | Enrich one mock McDonald's AU place with `diet_preference="vegetarian"`. Inspect `top_menu_item`, `no_diet_safe_candidates`. |
| 2 | **Wow! Momo**    | IN     | vegetarian      | Enrich one mock Wow! Momo IN place with `diet_preference="vegetarian"`. Inspect `top_menu_item`. |
| 3 | **Haldiram's**   | IN     | vegetarian      | Enrich one mock Haldiram's IN place with `diet_preference="vegetarian"`. Inspect `top_menu_item`. |
| 4 | **Nando's**      | AU     | vegan           | Enrich one mock Nando's AU place with `diet_preference="vegan"`. Inspect `top_menu_item`, `no_diet_safe_candidates`. |
| 5 | **KFC**          | AU     | vegan           | Enrich one mock KFC AU place with `diet_preference="vegan"`. Inspect `top_menu_item`, `no_diet_safe_candidates`. |

**How to run each check**

- Use your existing pattern: build a mock place (correct `name`/`place_name` for the chain, `country_code` / vicinity for market), then call:
  - `enrich_place_with_local_profile(place, market_tag="AU"|"IN", diet_preference="vegetarian"|"vegan")`.
- Inspect in the returned payload: `matched_chain_key`, `chain_menu_store`, `top_menu_item` (or `None`), `diet_filter_applied`, `no_diet_safe_candidates`.

---

## 2. Expected behavior

| # | Chain      | Diet        | Expected result |
|---|------------|-------------|------------------|
| 1 | McDonald's | vegetarian | `top_menu_item` is a **vegetarian** option (e.g. **Hamburger**). Must **not** be McChicken, Filet-O-Fish, or Big Mac. `no_diet_safe_candidates` is False. |
| 2 | Wow! Momo | vegetarian | `top_menu_item` is a **veg momo** option (e.g. Pan-Fried Veg Momos or similar veg item from seed). Must not be a chicken momo. `no_diet_safe_candidates` is False. |
| 3 | Haldiram's | vegetarian | `top_menu_item` is a **vegetarian** option (e.g. Dal with Roti, Veg Thali, Paneer Tikka, or Chhole). Must not be Tandoori Chicken. `no_diet_safe_candidates` is False. |
| 4 | Nando's   | vegan      | Nando's menu is chicken-focused; typically **no vegan-safe items**. Expect `top_menu_item` is **None**, `no_diet_safe_candidates` is **True**, `diet_filter_applied` is True. Payload still has `matched_chain_key` / `chain_menu_store` so the venue is recognized. |
| 5 | KFC       | vegan      | KFC AU is chicken-focused; typically **no vegan-safe items**. Expect **same as #4**: `top_menu_item` is **None**, `no_diet_safe_candidates` is **True**, graceful fallback. |

---

## 3. Failure interpretation

| What you see | Likely cause |
|--------------|---------------|
| **McDonald's vegetarian:** top is McChicken (or other non-veg) | Diet filter not applied for this chain/market, or `vegetarian_possible` not set correctly on Hamburger (or veg item) in seed/Supabase. Re-check seed or DB flags and re-sync if needed. |
| **Wow! Momo vegetarian:** top is chicken momo | Veg momo items not marked `vegetarian_possible=True` in seed/Supabase, or filter not applied. Fix seed/Supabase and re-sync. |
| **Haldiram's vegetarian:** top is Tandoori Chicken | Vegetarian items (Dal, Veg Thali, Paneer, Chhole) not marked `vegetarian_possible=True`, or chicken item not marked False. Fix seed/Supabase and re-sync. |
| **Nando's or KFC vegan:** top is a chicken/non-vegan item | Non-vegan items should be excluded; if one appears as top, diet filter is not applied or vegan logic is wrong. If you intentionally added a vegan option to the seed, then expect that item; otherwise expect None. |
| **Nando's or KFC vegan:** top_menu_item is not None and no_diet_safe_candidates is False | Seed may have a vegan item (e.g. sides/salad only). If that’s intended, behavior is correct. If you expect no vegan options, add or fix `vegan_possible` in seed so all items are non-vegan and re-sync. |
| **No diet_safe_candidates but payload is None or missing matched_chain_key** | Enrichment should still return a payload with chain metadata; only `top_menu_item` / `top_menu_items` / `candidates` are empty. If the whole payload is None or chain keys are missing, the bug is in the fallback path (return shape when no diet-safe candidates). |
| **diet_filter_applied is False for vegetarian/vegan** | `diet_preference` not reaching enrichment (e.g. not passed or not read from `place`). Check caller passes `diet_preference` (or sets `place["diet_preference"]`). |

---

## Optional: one-off script

You can add a small script (e.g. `scripts/spot_check_diet_enrichment.py`) that builds the five mock places, calls `enrich_place_with_local_profile(place, market_tag=..., diet_preference=...)` for each, and prints for each: `matched_chain_key`, `chain_menu_store`, `top_menu_item` (or "None"), `no_diet_safe_candidates`, `diet_filter_applied`. Then run from `backend` with Supabase env and compare output to the table in section 2.

# Recommendation quality & API options

## Changes made (ranking & heuristics)

### 1. “Best” pick for fat loss: pizza/fast-food demotion

- **Issue:** Pizza Hut (or similar) was shown as “BEST RIGHT NOW” for users with a fat-loss goal.
- **Change:** In `lunch_decision._pick_best`, when goal is fat_loss/cut we:
  - Sort by **health_score** right after `fit_for_today`, so fitter venues (e.g. South Indian, tandoori) outrank pizza when they fit.
  - Apply a **-15 health_score** penalty when the place name contains: `pizza`, `hut`, `domino`, `mcdonald`, `kfc`, `burger king`.
- **Files:** `backend/lunch_decision.py` (`_pick_best(..., goal=goal)`).

### 2. List order vs score

- Healthy map list is sorted by `_sort_key` in `healthy_food_map.enrich_places_for_healthy_map`, which already includes `restaurant_health_score` / `health_score`. So higher score should appear higher in the list. If your UI still shows a different order, ensure the client uses the **same** list order as the API (e.g. by `health_score_100` or `map_rank`).

### 3. Generic “egg plate” → South Indian (e.g. Chennai Filter Coffee)

- **Issue:** Venues like “Chennai Filter Coffee (CFC)” were getting generic “Egg + chicken plate” (cafe rule) instead of “Idli or plain dosa-style option”.
- **Change:** South Indian / filter-coffee matching was extended so these venues get idli/dosa suggestions:
  - **healthy_order_recommender.py** – `CUISINE_ORDER_RULES` for `south_indian_temple`: added tokens `"filter coffee"`, `"chennai"`, `"cfc"`. Rule priority (10) is already above cafe (8), so “Chennai Filter Coffee” now matches South Indian and gets “Idli or plain dosa-style option”.
  - **menu_item_scoring.py** – `PLACE_MENU_RULES` for `south_indian_temple_canteen`: same tokens added so heuristic menu items are idli/dosa, not cafe egg plate.
- **Files:** `backend/healthy_order_recommender.py`, `backend/menu_item_scoring.py`.

---

## LLM slowness & API options (Yelp, etc.)

You mentioned LLM-based reasoning takes too long (e.g. timeouts, 504). Below are practical options.

### Current fast path (already in place)

- For **healthy nearby** and **lunch-decision** (and daily-decision), we use `use_llm_place_context=False` and skip real menu ingestion for bulk calls. That keeps responses in the few-seconds range instead of minutes.

### Option A: Enrich only top N with LLM/API

- Return the list quickly using **heuristics only** (current fast path).
- In the background or on-demand, call LLM or an external API only for the **top 3–5** places (or the one the user taps). That way latency is low and quality improves where it matters.

### Option B: Use real menu/rating APIs

- **Yelp Fusion API** – Business search, details, reviews. No official “menu items” endpoint; you can use reviews/text for hints or pair with another source.
- **Google Places (New)** – You already use it for discovery. Details can include some metadata; full menus usually require Place Details + optional scraping or partner data.
- **Foursquare / TripAdvisor / other** – Some have menus or rich descriptions; terms and rate limits apply.
- **Dedicated menu APIs** – e.g. Grubhub/Doordash-style partners (if available), or services that aggregate menu data. Often paid and region-specific.

Integration approach:

1. **Discovery:** Keep Google Places (New) for “nearby places”.
2. **Scores & “best order”:**  
   - **Tier 1 (fast):** Keep heuristic rules (e.g. `healthy_order_recommender` + `menu_item_scoring` PLACE_MENU_RULES) as default.  
   - **Tier 2 (optional):** For selected place(s), call Yelp (or similar) for ratings/reviews and optionally a small LLM pass to infer “best order” from text.  
3. **Caching:** Cache per `place_id` (and optionally goal) to avoid repeated LLM/API calls.

### Option C: Hybrid scoring

- Use **Yelp rating** (or similar) as an extra signal in `_sort_key` / `_pick_best` (e.g. boost places with rating ≥ 4.0). That can improve “better option” ordering without waiting on LLM.

### Summary

- **Short term:** Current changes (fat-loss ranking, South Indian/filter-coffee heuristics) improve “best” choice and reduce generic egg plate. Keep `use_llm_place_context=False` for bulk to avoid timeouts.
- **Medium term:** Add Yelp (or similar) for details/ratings; use it for top-N or on tap. Optionally run a small LLM only for the selected place.
- **Long term:** If you get access to a real menu API, use it to replace or augment heuristic “best order” for higher accuracy.

If you want to proceed with Yelp, next steps are: add a small `yelp_client` module, call it from a single endpoint (e.g. “place details”) or from the lunch-decision flow for the chosen place only, and cache by `place_id`.

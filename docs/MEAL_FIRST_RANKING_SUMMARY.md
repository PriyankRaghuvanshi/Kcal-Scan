# Meal-first ranking – summary

## Goal

Fix Healthy Nearby so it is **meal-first, not venue-first**. A Pizza Hut "less bad" item must not beat a clearly better Indian/Subway/cafe option for a CUT / get-fit user. Also fix the UI/backend mismatch where list order did not match the visible score. After cleanup: one canonical ranking builder, visible order = visible score, no hidden current_place bump in flat mode, general food-quality/processed-meal logic (no pizza-specific caps), and clear section/label/confidence in the payload.

## Canonical ranking builder

All ranking-related fields come from **one source of truth**: **`backend/ranked_place_builder.py`** → `build_ranked_place_profile(place, user_context, *, for_map=False, for_list=False) -> dict`. Callers (main.py `/places/healthy`, lunch_decision.py, map flows) call this builder and merge the result; they do not recompute ranking fields. The builder returns: `display_rank_score_100`, `meal_fitness_score_100`, `meal_fitness_score`, `venue_prior_score_100`, `eligibility_band`, `section`, `recommendation_label`, `confidence_label`, `why_this_ranked_here`, `rank_reason_short`, `score_breakdown`, fit/protein/calorie/overshoot scores, `best_item_*`, `best_item_is_generic_fallback`, `best_item_needs_menu_check`, `food_quality_score_100`, `protein_density_score_100`.

## Flat vs sectioned sort mode

- **`sort_mode: "flat_score"`** — Order = **display_rank_score_100 descending**, then **distance ascending**. No current_place bump. Use when the API returns a flat list without section headers.
- **`sort_mode: "sectioned"`** — Order = **section rank** (fixed order below), then **display_rank_score_100 descending**, then distance. Use when the API returns grouped `sections` and the client renders section headers.

Section order (fixed): 1. Best fit for your goal  2. Decent nearby options  3. Needs menu check. Do not silently mix current_place into visible order in flat mode; use a badge (e.g. `is_current_place: true`) instead.

## Visible score rules

Healthy Nearby uses **`display_rank_score_100`** as the main visible score. **health_score** / **health_score_100** are kept for backward compatibility but are **venue-prior only**; do not use them as the primary sort or displayed score on Healthy Nearby.

## Venue prior vs display rank score

- **venue_prior_score_100** = venue-level prior (from health_score); input to ranking, not the primary visible score.
- **display_rank_score_100** = meal-first rank score; primary visible score and sort key; order must match this score.

## Candidate meal generation (cuisine-specific)

Candidate meals for ranking come from **cuisine-specific archetypes** when no real menu is available:

- **backend/cuisine_candidate_rules.py** — Central rule table: North Indian, South Indian, general cafe, juice/smoothie, pizza, sandwich/Subway. Each cuisine has up to 3–5 candidate archetypes (name, calories, protein, cut_friendly, avoid_as_primary). Bad generic fallbacks (e.g. "egg + chicken plate", "lighter menu option") are suppressed from being chosen as primary.
- **backend/menu_item_scoring.py** — Uses `get_candidates_for_place()` for heuristic items; returns up to 3 candidates per venue; existing scoring/sorting picks the best. Confidence and labels reflect cuisine match strength (e.g. juice centers get lower confidence).
- **backend/healthy_order_recommender.py** — When suggesting a single best order without a real menu, uses `get_best_order_for_place_heuristic()` so Indian gets tandoori/dal-style, South Indian gets idli/dosa/egg dosa, cafe gets eggs/wrap, etc.

Heuristic labels: **Likely healthy option** when cuisine match is strong and confidence ≥ 0.58; **Needs menu check** when weak or low confidence. Heuristic generic fallbacks are never labeled "Best pick".

## Reducing heuristic dependence (real menu + chain registry + swaps)

- **Chain coverage**: `backend/chain_menu_registry.py` provides deterministic seeded menu items for known chains. These items are tagged as **`menu_item_source="chain_registry"`** (separate from `real_menu`) and are preferred over broad heuristics when available.
- **Normalization**: `backend/menu_normalization.py` normalizes candidates across sources to a consistent shape (name, macros, category, negative_flags, supports_swaps), making selection stable and debuggable.
- **Source preference** (approx): `user_scan` / `real_menu` > `chain_registry` > `llm_inferred` (if enabled) > `heuristic`.
- **Swap intelligence**: `backend/swap_rules.py` generates 1–3 deterministic structured swaps for the chosen item (portion control, light sauce, skip sides/drinks, etc.). These appear as `best_item_swaps` in the chosen item payload and are visible in audit mode.

## Personal learning signals (v1)

CalorieClick captures lightweight per-user habit/response signals to enable “worked before” style nudges without heavy ML.

- **Event capture**:
  - `POST /meal-feedback` – partial allowed; supports follow-up updates via `feedback_id`.
  - `POST /meal-decision-event` – append-only events (viewed/opened/swap accepted/chosen/ignored).
- **Storage**:
  - `backend/meal_feedback_store.py` – JSON event store at `backend/data/meal_feedback_store.json` (override `MEAL_FEEDBACK_STORE_PATH`).
  - `backend/meal_decision_event_store.py` – JSON event store at `backend/data/meal_decision_event_store.json` (override `MEAL_DECISION_EVENT_STORE_PATH`).
- **Summary + labels**:
  - `backend/personal_response_summary.py` – computes deterministic aggregates and labels:
    - “Worked well before”, “Usually keeps you fuller”, “Often followed by cravings”, “You often repeat this”, “Not enough data yet”.
- **Payload enrichment & bounded ranking modifier**:
  - `/places/healthy?user_id=...` and `/places/healthy/audit?user_id=...` include: `personal_memory_label`, `worked_before`, `avg_fullness`, `avg_craving_score`, `times_chosen`, `repeat_success_rate`, `swap_accept_rate`.
  - A **small bounded modifier** is applied in `backend/ranked_place_builder.build_ranked_place_profile` via `compute_personal_memory_modifier(...)` **only when**:
    - `times_chosen >= 3` **and**
    - core quality is reasonable (`meal_fitness_score_100` ≥ ~55, food_quality ≥ 50, protein_density ≥ 45).
  - Modifier bounds:
    - `personal_history_net_100` ∈ \[-6, +6], typically \[-4, +4] in practice.
    - Positive signals: high fullness, low cravings, good repeat rate, high swap acceptance, “Worked well before” style label.
    - Negative signals: high cravings, low fullness, poor repeat, “Often followed by cravings”.
  - Core scores remain:
    - `meal_fitness_score_100` = **core** meal-first score (no personal memory)
    - `display_rank_score_100` = core + bounded personal modifier (used for sorting/visible score).

## Context-aware ranking (time-of-day and situational)

A bounded **context-adjustment layer** sits on top of the meal-first engine. Recommendations adapt to:

- **Post-workout recovery** – favours high-protein, recovery-friendly meals
- **Late-night / damage-control** – favours lighter, satiating options; penalises combo/fried/dessert-heavy
- **Low calories remaining** (≤250 kcal) – favours meals within remaining; penalises overshoot
- **High protein recovery needed** (≥35g left) – favours high-protein meals
- **Breakfast / lunch / dinner** – inferred from `local_hour`; favours context-appropriate meals
- **Optional**: `poor_sleep_flag`, `high_craving_risk_flag` – slight satiety preference, penalty for hyper-palatable combos

**Inference** (`backend/context_modes.py`): `infer_context_mode(context)` returns `context_mode`, `context_flags`, `context_reason`. Explicit `context_mode_override` wins. Otherwise: post_workout_recovery > late_night_damage_control > breakfast/lunch/dinner by hour > default.

**Scoring** (`backend/context_scoring.py`): `compute_context_modifier(place_profile, context_info, user_context)` returns `context_bonus_100`, `context_penalty_100`, `context_net_100` (clamped **[-8, +8]**), `context_mode`, `context_reason`, `context_applied`, `context_components`.

**Safeguards:**
- If `meal_fitness_score_100` < 50: max positive context bonus = +2
- Low `food_quality_score_100`: dampen positives
- Low `protein_density_score_100`: dampen post-workout / high-protein positives

**Score breakdown:**
- `meal_fitness_score_100` = **core** (meal-first, no personal, no context)
- `personal_history_net_100` = personal memory modifier
- `context_net_100` = context modifier
- `display_rank_score_100` = core + personal + context (clamped [0, 100])

**Query params** (optional): `context_mode`, `post_workout`, `late_night`, `local_hour`, `remaining_calories`, `remaining_protein_g`, `poor_sleep_flag`, `high_craving_risk_flag`.

## Smart Food Alerts

Context-aware nearby notifications that fire **only when** there is a genuinely useful nearby option for the user's goal and state. No generic promo spam; no notifications just because food exists.

**Philosophy:** need × timing × nearby quality × personal relevance − fatigue. Alerts require:
1. User need exists (e.g. protein gap, post-workout, late-night, habit rescue)
2. Timing/context is right (dinner window, post-workout, late-night)
3. Nearby option quality is high (display_rank_score_100, confidence)
4. Fatigue/spam checks allow (recent alerts, ignored streak)

**Alert types:**
- **protein_rescue** — remaining_protein_g ≥ 25, dinner window (16:00–20:30), high-protein nearby
- **post_workout_recovery** — post_workout true, remaining_protein_g ≥ 20, recovery meal nearby
- **late_night_damage_control** — local_hour ≥ 21, lower-regret option nearby
- **worked_before_repeat** — strong personal_memory_label (Worked well before, Usually keeps you fuller, You often repeat this)
- **habit_rescue** — poor_sleep_flag or high_craving_risk_flag, lower-regret option nearby

**Scoring:** alert_score = need + timing + nearby_quality + personal_relevance − fatigue. Threshold: ≥ 55 to be eligible. Only Verified/Estimated confidence; Needs menu check → suppressed.

**Anti-spam rules:**
- Max 1 high-intent alert in 6 hours
- Max 2 per day
- Max 5 per week
- If 3 ignored in a row, reduce eligibility
- Same venue not repeated in short window
- No alert if confidence weak or no strong nearby option
- Optional: no alert if user recently opened app and saw nearby options

**Endpoint:** `GET /smart-food-alerts/candidates` — same inputs as /places/healthy plus fatigue params. Returns `candidates` with `alert_type`, `alert_score`, `title`, `body`, `why_triggered`, `suppression_reasons`, `eligible_to_send`, `audit_one_liner`.

**Push delivery:** `POST /push/send-smart-alerts` sends eligible alerts as Expo push; top 1 per user per run. Supports dry-run. See `backend/docs/EXPO_PUSH_DELIVERY.md`.

**Audit:** `GET /places/healthy/audit?include_alert_candidates=true` adds `alert_candidates` to the response. Example one-liner: `protein_rescue | Score 91 | Subway | 30g protein | 4 min away | eligible`.

## Confidence and recommendation labels

- **confidence_label**: **Verified** (real menu/user_scan, conf ≥ 0.72), **Estimated** (decent conf), **Needs menu check** (low conf/heuristic).
- **recommendation_label**: Best pick | Strong option | Likely healthy option | Suggested healthier pick | Needs menu check. Generic fallbacks (`best_item_is_generic_fallback = true`) must never be "Best pick"; they get Suggested healthier pick or Needs menu check and eligibility_band ≤ 2.

## Files changed

| File | Changes |
|------|--------|
| **backend/context_modes.py** | **Context inference.** `infer_context_mode(context)` – time-of-day and situational flags. |
| **backend/context_scoring.py** | **Context scoring.** `compute_context_modifier()` – bounded ±8 modifier, safeguards. |
| **backend/smart_food_alerts.py** | **Smart alerts.** `build_smart_food_alert_candidates()` – need × timing × quality − fatigue; anti-spam. |
| **backend/ranked_place_builder.py** | **Canonical builder.** `build_ranked_place_profile()`; context modifier; confidence_label; rank_reason_short; all ranking fields in one place. |
| **backend/meal_ranking.py** | General penalties (ultra_processed, combo_meal, deep_fried, sugary_drink, hyper_palatable, low_protein_density). No pizza-specific band cap. |
| **backend/place_today_decision.py** | Numeric fields: `fit_today_score_100`, `calorie_fit_score_100`, `protein_fit_score_100`, `overshoot_penalty_100`. |
| **backend/lunch_decision.py** | Calls `build_ranked_place_profile`; merges result. Hero uses `best_item_is_generic_fallback`. |
| **backend/healthy_food_map.py** | `_flat_sort_key`, `_sectioned_sort_key`, `build_sections(places)`. Enrich `sort_mode`; flat = score desc then distance; sectioned = section then score then distance. |
| **backend/main.py** | `/places/healthy`: calls `build_ranked_place_profile`, merges; response has `sort_mode` and `sections` when sectioned. |
| **backend/test_meal_ranking.py** | CUT ranking, generic fallback, visible score/sort, needs menu check, low-cal poor-protein. |
| **backend/test_ranked_place_builder.py** | Canonical builder consistency, flat/sectioned sort trust, current_place no hidden bump, processed-meal penalty, generic fallback label. |

## Rationale for ranking changes

1. **Venue health_score** reflected venue type/metadata, not the specific meal. Ranking is driven by **meal_fitness_score_100** / **display_rank_score_100**. Healthy Nearby shows and sorts by **display_rank_score_100**.

2. **Eligibility bands** prevent generic/heuristic fallbacks from being hero. Only band 3 (verified, non-generic) can be "Best pick". Processed/combo meals are demoted by **general** food-quality penalties (no single pizza brand token).

3. **Visible score = sort key**: list order matches `display_rank_score_100` (and section when sectioned). Flat mode has no hidden current_place bump.

4. **Sections** are returned explicitly when using sectioned mode so mobile can render headers and avoid score/order confusion.

## Before/after API payload (3 places)

**Before (venue-first, health_score as main):**
- Place A (Pizza Hut): `health_score` 6.2, `health_score_100` 62, list position 1.
- Place B (Indian): `health_score` 5.8, `health_score_100` 58, list position 2.
- Place C (Subway): `health_score` 5.5, `health_score_100` 55, list position 3.

**After (meal-first, display_rank_score_100 as main):**
- Place A (Subway): `health_score` 5.5 (kept), `display_rank_score_100` 78, `meal_fitness_score_100` 78, `eligibility_band` 3, `section` "Best fit for your goal", `recommendation_label` "Best pick", list position 1.
- Place B (Indian): `health_score` 5.8, `display_rank_score_100` 76, `meal_fitness_score_100` 76, `eligibility_band` 2, `section` "Best fit for your goal", `recommendation_label` "Strong option", list position 2.
- Place C (Pizza Hut): `health_score` 6.2, `display_rank_score_100` 58, `meal_fitness_score_100` 58, `eligibility_band` 2, `section` "Decent nearby options", `recommendation_label` "Strong option", list position 3.

## Query param: sort_mode

`GET /places/healthy` accepts an optional query param **`sort_mode`**:

- **`flat_score`** — Response has **`items`**: a flat list sorted by `display_rank_score_100` desc, then distance asc. No `sections` key.
- **`sectioned`** — Response has **`places`** and **`sections`**: grouped sections with headers; items within each section sorted by score then distance.

**Default:** `sort_mode=sectioned` (for backward compatibility with clients that expect `places` and `sections`). Invalid values return **422** with `invalid_sort_mode` and the list of allowed values.

## Response payload shape

**Flat mode** (`sort_mode=flat_score`): `items` = flat array; each item has `section`, `display_rank_score_100`, etc.; `sort_mode: "flat_score"`. No `places` or `sections` key.

**Sectioned mode** (`sort_mode=sectioned`): `places` = flat array (same order as sectioned sort); `sections: [{ "name": "Best fit for your goal", "items": [...] }, ...]`; `sort_mode: "sectioned"`.

Common per-place fields: `display_rank_score_100`, `meal_fitness_score_100`, `venue_prior_score_100`, `eligibility_band`, `section`, `recommendation_label`, `confidence_label`, `why_this_ranked_here`, `rank_reason_short`, `best_item_name`, `best_item_calories`, `best_item_protein`, `best_item_is_generic_fallback`, `best_item_needs_menu_check`, `health_score`, `health_score_100` (venue-prior only).

## Sample response (3 places, sectioned)

```json
{
  "sort_mode": "sectioned",
  "places": [ ... ],
  "sections": [
    { "name": "Best fit for your goal", "items": [
      { "name": "Subway", "display_rank_score_100": 78, "recommendation_label": "Best pick", "confidence_label": "Verified", "rank_reason_short": "42g protein, fits today", "section": "Best fit for your goal", ... }
    ]},
    { "name": "Decent nearby options", "items": [
      { "name": "Indian Kitchen", "display_rank_score_100": 72, "recommendation_label": "Strong option", "confidence_label": "Estimated", "rank_reason_short": "Higher protein, better whole-food option", ... }
    ]},
    { "name": "Needs menu check", "items": [
      { "name": "Cafe", "display_rank_score_100": 55, "recommendation_label": "Needs menu check", "confidence_label": "Needs menu check", "rank_reason_short": "Needs menu confirmation", ... }
    ]}
  ]
}
```

## Mobile UI TODO

- Always show **`display_rank_score_100`** on each card (not `health_score_100`).
- If `sort_mode === "sectioned"`, show **section headers** ("Best fit for your goal", "Decent nearby options", "Needs menu check") and group items under them.
- Show **`recommendation_label`**, **`confidence_label`**, and **`rank_reason_short`** so users see why a place is ranked and how confident we are.

## Performance (making data faster)

- **LLM out of hot path:** Ranking uses no LLM; meal_fitness_score and eligibility_band are deterministic (existing `use_llm_place_context=False` and no menu ingestion in bulk are unchanged).
- **Google Places:** Keep using Nearby Search (New) and Place Details with **minimal field masks** (only fields you need) to reduce latency and cost.
- **Concurrent load:** To handle many simultaneous users:
  - **Caching:** Cache `/places/healthy` (or its upstream Google calls) by `(lat, lng, radius, goal, cut_mode)` with a short TTL (e.g. 2–5 min). Cache per-place details by `place_id`.
  - **Connection pooling:** Use a single `requests.Session` or async client for Google APIs.
  - **Rate limiting:** Optional per-user or per-IP rate limit on `/places/healthy` to avoid thundering herd.
  - **Read replicas / async:** If DB is used for menu or user prefs, use read replicas for healthy endpoint; keep ranking logic async-friendly so it doesn't block.

No Yelp/Foursquare added; discovery and ranking stay on Google Places + internal meal-first logic.

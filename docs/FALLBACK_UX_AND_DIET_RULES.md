# Fallback UX and Diet Rules

## Goal

Healthy Nearby must remain useful and trustworthy when suburbs or restaurants are not yet in the DB. Vegetarian and vegan users must never receive incompatible recommendations.

- **Unknown suburb/restaurant**: Still return useful recommendations with honest confidence labels.
- **Vegetarian/vegan**: Never recommend meat, chicken, fish (vegetarian) or + egg, dairy, whey (vegan).

No LLM. No live menu fetch in the hot path.

## Diet Preference Values

| Value | Alias | Meaning |
|-------|-------|---------|
| `omnivore` | default | All items allowed |
| `vegetarian` | `veg` | Exclude meat, chicken, fish |
| `vegan` | - | Exclude meat, chicken, fish, egg, dairy, whey |

Pass via query param `diet_preference` on:
- `GET /places/healthy`
- `GET /places/healthy/audit`
- `GET /smart-food-alerts/candidates`

## Diet Filtering Rules

- **Conservative when uncertain**: If an item might contain animal product and we're unsure, exclude it.
- **Name inference**: Items with "veggie", "vegan", "vegetarian" in the name are not flagged as meat.
- **Explicit flags override**: Candidates can have `contains_chicken`, `contains_meat`, etc. when known.

### Item Flags

| Flag | Excludes for |
|------|--------------|
| `contains_meat` | vegetarian, vegan |
| `contains_chicken` | vegetarian, vegan |
| `contains_fish` | vegetarian, vegan |
| `contains_egg` | vegan |
| `contains_dairy` | vegan |
| `contains_whey` | vegan |

## Fallback Ladder

When resolving a recommendation for a place, the live path tries sources in order:

1. **Exact menu / venue intelligence cache**
2. **Chain-backed** (ingested chain items, chain registry)
3. **Enriched local venue profile**
4. **Strong cuisine heuristic**
5. **Generic fallback** → enqueues for enrichment

Unknown suburb: Places are still fetched from Google; we rank and filter by diet. No app failure.
Unknown restaurant: No local profile or cache → heuristic or generic fallback. Label honestly.

## Confidence / Label UX Rules

| Source | Labels | Confidence |
|--------|--------|------------|
| exact/cache/chain-backed | Best pick, Strong option | Verified / Chain-backed |
| enriched local / strong heuristic | Likely healthy option | Estimated |
| generic fallback | Suggested option | Needs menu check |

- Vegan + weak heuristic: prefer "Needs menu check" over "Estimated".
- Generic fallback items never get "Best pick".
- Honest downgrade when diet filters many candidates.

## Unknown Suburb Behavior

- Fetch places from Google (unchanged).
- Rank using meal-first logic.
- Filter by diet.
- If no local profiles in area, heuristic/generic fallback is used. Label as "Suggested option" or "Needs menu check".
- Enqueue visible generic results for enrichment.

## Unknown Restaurant Behavior

- No cache hit, no local profile, no chain match.
- Use cuisine heuristic; if no match, generic fallback.
- Diet filter applies at each stage.
- When all candidates filtered out for veg/vegan, use diet-safe fallback: "Dal + roti (needs menu check)" or "Vegetarian option (needs menu check)".

## Enrichment Queue Triggers

Places are enqueued for enrichment when:

- `candidate_low_specificity` – heuristic path used, generic result
- `high_visibility_generic` – visible with generic fallback
- `diet_safe_but_low_specificity` – diet-safe but weak inference
- `missing_veg_profile` – vegetarian user, no local profile
- `missing_vegan_profile` – vegan user, no local profile
- `unknown_suburb_visible_result` – visible in unknown suburb with generic

Duplicate queue spam is avoided (recent enqueue dedup).

## Debug / Audit Fields

Trace and audit include:

- `diet_preference`
- `diet_excluded_candidate_count`
- `fallback_used`
- `fallback_reason`
- `confidence_label`
- `chosen_candidate_specificity_tier`
- `enqueued_for_enrichment`
- `enrichment_enqueue_reason`

## Example Outputs

| Scenario | User | Output |
|----------|------|--------|
| Known chain + veg | vegetarian | "Subway — Veggie sub, extra salad, no mayo" |
| Unknown Indian + vegan | vegan | "Suggested option — Dal + roti (needs menu check)" |
| Unknown cafe + vegetarian | vegetarian | "Likely healthy option — Eggs on toast" |
| Generic fallback | omnivore | "Suggested option — Lighter menu option" |

## Key Files

- `backend/diet_filters.py` – `is_item_allowed_for_diet`, `filter_candidates_for_diet`, `normalize_diet_preference`
- `backend/cuisine_candidate_rules.py` – diet flags on candidates, diet filtering in `get_candidates_for_place`
- `backend/menu_item_scoring.py` – diet filtering on cache, chain, local profile, heuristic
- `backend/healthy_order_recommender.py` – diet-safe local profile and rule override
- `backend/ranked_place_builder.py` – vegan + weak heuristic → "Needs menu check"
- `backend/background_enrichment_queue.py` – new enqueue reasons
- `backend/place_trace_debug.py` – diet and fallback trace fields
- `backend/healthy_places_audit.py` – diet and fallback audit fields

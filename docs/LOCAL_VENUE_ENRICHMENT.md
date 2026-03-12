# Local Venue Enrichment

## Goal

Make Healthy Nearby much more trustworthy in launch geography by improving specificity for the local venues users actually see most often. Independents should feel nearly as strong as chains.

This is **not** about solving every independent restaurant globally. It is about dominating the top launch suburbs with:

- Better venue-specific candidate intelligence
- Better specificity than generic cuisine fallback
- Cached local venue profiles
- Faster repeat performance

No LLM on the hot path. No live menu scraping.

## Launch Area Strategy

We focus on launch suburbs first:

- **Wentworthville**, **Parramatta**, **Harris Park**, **Westmead**
- **Merrylands**, **Granville**, **Homebush**, **Strathfield**
- **Sydney Olympic Park**
- Nearby Sydney-west areas as configured

Launch areas are defined in `backend/launch_area_config.py` (or via `LAUNCH_AREA_CONFIG_PATH`).

## Local Venue Profile Schema

Each profile supports:

| Field | Type | Description |
|-------|------|-------------|
| `place_id` | string | Google Place ID (optional; add when available) |
| `place_name` | string | Display name |
| `normalized_name` | string | Lowercase, no punctuation |
| `name_variants` | string[] | "Darbar Indian", "Darbar Restaurant", etc. |
| `area_key` | string | wentworthville, parramatta, harris_park, etc. |
| `market_tag` | string | AU |
| `cuisine_tags` | string[] | indian, south_indian, cafe |
| `category_tags` | string[] | restaurant, cafe |
| `coverage_status` | enum | planned, seeded, partial, strong |
| `confidence_tier` | float | 0–1 |
| `profile_source` | enum | curated_manual, cached_user_feedback, inferred_local_profile, chain_registry, hybrid, auto_promoted, community_confirmed, launch_enrichment_pack |
| `seeded_by_launch_pack` | bool | True when profile was seeded from the launch enrichment pack |
| `specificity_tier` | enum | exact_local_profile, enriched_local_profile, heuristic_local_profile, generic_fallback |
| `candidate_templates` | object[] | See below |
| `swap_templates` | object[] | See below |
| `active` | bool | true |

### Candidate Template

| Field | Type |
|-------|------|
| `template_key` | string |
| `template_name` | string |
| `estimated_calories` | int |
| `estimated_protein_g` | int |
| `confidence` | float |
| `food_quality_tags` | string[] |
| `negative_flags` | string[] |
| `cut_friendly` | bool |
| `recommended_swap_keys` | string[] |

### Swap Template

| Field | Type |
|-------|------|
| `swap_key` | string |
| `swap_label` | string |
| `swap_type` | string |
| `calories_delta` | int |
| `protein_delta` | int |
| `reason` | string |
| `plausibility_score` | float |

## Specificity Tiers for Local Venues

| Tier | Bonus | Meaning |
|------|-------|---------|
| `exact_local_profile` | +5 | Matched by place_id |
| `enriched_local_profile` | +4 | Matched by name + area, has curated candidates |
| `heuristic_local_profile` | +1 | Cuisine heuristic |
| `generic_fallback` | -4 | Generic "lighter menu option" |

Enriched local profile beats generic fallback when core scores are close.

## Priority Order (Live Recommendation Path)

The live path uses database-backed intelligence before falling back to heuristics:

1. **Venue intelligence cache** (`venue_intelligence_cache` via Supabase or JSON) – exact_menu_cache, chain_ingested
2. **Local venue profiles** – Supabase canonical store first; fallback to JSON if unavailable. See [SUPABASE_LOCAL_PROFILE_CANONICAL_STORE.md](SUPABASE_LOCAL_PROFILE_CANONICAL_STORE.md)
3. **Ingested chain items** – chain_menu_ingested data
4. **Chain registry** – chain_registry templates
5. **Strong cuisine heuristic**
6. **Generic fallback**

Cache and local profiles are read in:

- **`backend/menu_item_scoring.py`** – `recommend_menu_items_for_place()` checks `get_cached_venue_intelligence(place_id)` first, then `enrich_place_with_local_profile(place)`
- **`backend/healthy_order_recommender.py`** – `suggest_best_order_for_place()` checks `get_local_venue_profile(place_id, normalized_name, area_key)` before heuristic rules
- **`backend/supabase_intelligence_store.py`** – `get_cached_venue_intelligence`, `get_local_venue_profile`, `enqueue_place_for_enrichment`

When a place ends up with a generic heuristic recommendation and no cache/local profile, it is **enqueued for enrichment** (if `should_enqueue_for_low_specificity(place)` is true) with a reason chosen by `_pick_enrichment_reason()` in `menu_item_scoring.py`. Recent-enqueue suppression (24h) avoids spam:

| Condition | Reason |
|-----------|--------|
| Place outside launch area (unknown suburb) | `unknown_suburb_visible_result` |
| Vegan user + heuristic path | `missing_vegan_profile` |
| Vegetarian user + heuristic path | `missing_veg_profile` |
| Omnivore in launch area | `candidate_low_specificity` |

The enrichment queue is in `backend/background_enrichment_queue.py`. Diet-aware reasons (`missing_veg_profile`, `missing_vegan_profile`) help prioritize enrichment for venues that vegetarian/vegan users need. See [FALLBACK_UX_AND_DIET_RULES.md](FALLBACK_UX_AND_DIET_RULES.md) for diet filtering and fallback behavior.

## Coverage Reporting

- **`GET /launch-areas/coverage`** – All areas
- **`GET /launch-areas/coverage?area_key=wentworthville`** – One area

Returns:

- `total_seeded_profiles`, `strong_profiles`, `partial_profiles`
- `pack_seeded_profiles` – profiles seeded from launch enrichment pack
- `auto_promoted_profiles` – profiles with ≥1 template from contribution auto-promotion
- `top_cuisines_covered`, `top_categories_covered`
- `total_local_enriched_places`

## How Local Venues Move from Generic to Enriched

1. **Planned** – Venue identified for enrichment
2. **Seeded** – Basic profile added
3. **Partial** – Some candidates + swaps
4. **Strong** – 3+ candidates, chain-like specificity

Adding more local venues is structured data/config work: edit `backend/data/local_venue_profiles.json`.

## Matching Logic

- **place_id** – Exact match when available
- **normalized_name + area_key** – Fallback; avoids cross-area false matches
- **name_variants** – Profile can list alternate names
- First token match – "Darbar" matches "Darbar Indian Restaurant"

## Launch readiness report

Use the launch readiness report to measure whether a suburb is producing concrete value:
- **`GET /launch-readiness/report?area_key=parramatta`**
- See [LAUNCH_READINESS_REPORT.md](LAUNCH_READINESS_REPORT.md)

## Post-sync remediation and next-enrichment targets

After canonical sync, run a post-sync pass to measure quality and get prioritized enrichment targets:
- **`GET /launch-readiness/post-sync-report?area_key=parramatta`** — Report with canonical metrics
- **`GET /launch-readiness/next-enrichment-targets?limit=20`** — Next 20 venues to enrich
- **`POST /launch-readiness/apply-next-enrichment-targets`** — Bulk apply those targets into the canonical Supabase store (add profiles, expand templates, add swaps, diet variants). See [APPLY_ENRICHMENT_TARGETS.md](APPLY_ENRICHMENT_TARGETS.md).

See [POST_SYNC_REMEDIATION_REPORT.md](POST_SYNC_REMEDIATION_REPORT.md) for how targets are chosen and how to use the report for enrichment sprints.

## Trace and Audit Visibility

Trace (`place_trace_debug.py`) and audit (`healthy_places_audit.py`) expose:

- `matched_local_profile`, `local_profile_source`, `chosen_candidate_profile_source`, `local_profile_confidence`, `local_profile_id`, `profile_store` (supabase_canonical | fallback_local_store)
- `used_venue_intelligence_cache`, `cache_source_type`, `cache_last_enriched_at`
- `chosen_candidate_specificity_tier`
- `fallback_used`, `fallback_reason`
- `enqueued_for_enrichment`, `enrichment_enqueue_reason`
- `diet_preference`, `diet_excluded_candidate_count`

These fields answer: *Why did this place show a generic result? Was cache/profile used? Why was it queued?*

Example visible sources: `exact_menu_cache`, `local_venue_profile`, `ingested_chain_item`, `chain_registry`, `heuristic_cuisine_match_strong`, `generic_fallback`. Diet-aware filtering is documented in [FALLBACK_UX_AND_DIET_RULES.md](FALLBACK_UX_AND_DIET_RULES.md).

## Enqueue suppression

To avoid queue spam, `enqueue_place_for_enrichment` skips enqueueing if the place was already enqueued within the last 24 hours. Use `skip_recent_check=True` to force enqueue (e.g. for manual runs).

## Contribution Review and Profile Updates

**Manual review:** Approved user venue contributions can add or update local venue profiles via a human-in-the-loop review flow:

- **Review flow**: [CONTRIBUTION_REVIEW_FLOW.md](CONTRIBUTION_REVIEW_FLOW.md)
- **Contributions**: [USER_VENUE_CONTRIBUTIONS.md](USER_VENUE_CONTRIBUTIONS.md)
- `backend/contribution_review_flow.py` – approve/reject, apply to profiles

**Auto-promotion:** Evidence-based auto-promotion promotes safe, repeated contributions without manual review:

- **Auto-promotion**: [CONTRIBUTION_AUTO_PROMOTION.md](CONTRIBUTION_AUTO_PROMOTION.md)
- `backend/contribution_auto_promotion.py` – aggregation, scoring, promotion
- Promoted templates use `profile_source = auto_promoted` or `community_confirmed`

Both paths use `backend/local_venue_profiles.py` – `add_candidate_template`, `add_swap_template`, `update_template_in_profile`.

## Launch Enrichment Pack

The **launch enrichment pack** (`backend/local_launch_enrichment_pack.py`) seeds structured local venue profiles for top launch suburbs. This reduces generic fallback for independents in launch areas.

**Priority areas:** Wentworthville, Parramatta, Harris Park, Westmead, Merrylands (from `launch_area_config`).

**Venue selection:** Pack defines specific venues per area with plausible candidate templates (e.g. Indian: tandoori + dal, paneer tikka, dal + roti; Cafe: eggs on toast, grilled chicken wrap). Diet-aware: vegetarian_possible, vegan_possible on templates where appropriate.

**Seeding:**
- `POST /launch-enrichment/seed` – Body: `{ area_key?, limit_areas?, limit_per_area? }`
- `GET /launch-enrichment/status` – Pack vs store status
- Or call `seed_launch_area_enrichment(area_key)` / `seed_all_priority_launch_areas()` in code

**Coverage:** `summarize_launch_area_coverage` includes `pack_seeded_profiles`. Trace/audit expose `seeded_by_launch_pack`.

**How seeded profiles affect live ranking:** Same as any local profile – `enrich_place_with_local_profile` matches by place_id or normalized_name + area_key. When a place matches a pack-seeded profile, it gets `enriched_local_profile` specificity (vs generic_fallback).

## Key Files

- `backend/launch_area_config.py` – Area definitions, `is_place_in_launch_area`, `sample_points_for_area`
- `backend/local_venue_profiles.py` – Profile schema, match, load, add/update templates
- `backend/local_venue_enrichment.py` – Enrich place, coverage summary, priority list
- `backend/supabase_intelligence_store.py` – DB access: `get_cached_venue_intelligence`, `get_local_venue_profile`, `enqueue_place_for_enrichment`
- `backend/venue_intelligence_cache.py` – JSON cache, `cache_to_menu_payload`
- `backend/background_enrichment_queue.py` – Enrichment queue, enqueue reasons
- `backend/local_launch_enrichment_pack.py` – Launch enrichment pack, seed helpers
- `backend/apply_enrichment_targets.py` – Bulk apply next-enrichment targets to canonical store
- `backend/data/local_venue_profiles.json` – Seed data

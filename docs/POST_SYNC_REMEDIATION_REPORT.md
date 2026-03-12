# Post-Sync Remediation Report

## Purpose

After canonical Supabase sync (launch-pack and auto-promoted profiles), we need to measure launch-area quality and prioritize the **next 20 venues to enrich**. This report answers:

1. Did generic fallback drop after canonical sync?
2. Which top suburbs still have the biggest quality gaps?
3. Which next 20 venues should we enrich immediately?
4. Which cuisines and venue types are still weakest?

This is **measurement + prioritization only**. No ranking changes, no LLM, no live menu fetch on the hot path.

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /launch-readiness/post-sync-report?area_key=parramatta` | Post-sync report for one area (includes canonical metrics) |
| `GET /launch-readiness/post-sync-report/all?limit_areas=5` | Post-sync reports for priority areas |
| `GET /launch-readiness/next-enrichment-targets?limit=20` | Prioritized next-enrichment targets (default 20) |

## What It Measures (Post-Sync)

For each priority suburb:

| Metric | Description |
|--------|-------------|
| `percent_top_5_generic_fallback` | % of top-5 results using generic fallback |
| `visible_results_using_local_profiles_percent` | % using local profiles |
| `known_chain_hidden_rate` | Known chains fetched but not in top 5 |
| `duplicate_score_cluster_rate_top_5` | Score collapse / tie clusters |
| `pack_seeded_profiles` | Profiles seeded from launch pack |
| `auto_promoted_profiles` | Profiles with auto-promoted templates |
| `canonical_profile_count` | Profiles in Supabase canonical store |
| `top_cuisines_needing_enrichment` | Cuisines with most generic venues |

The report also includes a **`remediation_examples`** block with: `top_remaining_generic_fallback_venues`, `top_weak_local_venues`, `top_missing_chain_opportunities`, `top_duplicate_score_cluster_examples`.

## Next-20 Target Selection Logic

Targets are scored and ranked. Higher score = more urgent. Scoring favors:

- **High visibility** — Venue appears in top-5 across multiple sample points
- **Generic fallback** — Currently showing generic items (tandoori+dal, protein bowl, etc.)
- **High-priority suburbs** — Wentworthville, Parramatta, Harris Park, Westmead, Merrylands first
- **Weak cuisine clusters** — Cuisine appears in `top_cuisines_needing_enrichment`
- **Missing local specificity** — No canonical local profile

Scoring penalizes:

- **Already strong** — `exact_local_profile`, `chain_registry`, `enriched_local_profile`
- **Low-priority areas** — Suburbs further down the list

## Target Output Structure

Each target includes:

| Field | Description |
|-------|-------------|
| `area_key` | Suburb (e.g. parramatta) |
| `place_id` | Google Place ID if known |
| `place_name` | Display name |
| `priority_score` | Higher = more urgent |
| `reason_summary` | Human-readable reason |
| `current_source` | e.g. generic_fallback, chain_fetched_not_visible |
| `chosen_candidate_specificity_tier` | Current tier |
| `cuisine_guess` | Inferred cuisine (indian, cafe, juice_smoothie, etc.) |
| `recommended_enrichment_action` | Action bucket |
| `profile_store` | supabase_canonical / fallback_local_store |
| `local_profile_source` | Profile source if any |
| `seeded_by_launch_pack` | True if from launch pack |

## Recommended Enrichment Actions

| Action | Meaning |
|--------|---------|
| `add_profile_now` | No local profile; add one |
| `expand_existing_profile` | Profile exists but weak; add templates |
| `add_veg_vegan_variants` | Add vegetarian/vegan options |
| `add_swaps` | Add swap templates |
| `fix_generic_template` | Pack-seeded but still generic; improve template |
| `review_chain_gap` | Known chain fetched but hidden; investigate |

## Priority Suburbs (Default Order)

1. Wentworthville  
2. Parramatta  
3. Harris Park  
4. Westmead  
5. Merrylands  

## Using the Report for Enrichment Sprints

1. **Run post-sync report** — `GET /launch-readiness/post-sync-report/all?limit_areas=5`
2. **Inspect canonical metrics** — `canonical_sync`, `local_enrichment`
3. **Get next targets** — `GET /launch-readiness/next-enrichment-targets?limit=20`
4. **Group by action** — Use `by_action` in the response to batch work
5. **Prioritize by score** — `targets` is sorted by `priority_score` descending
6. **Bulk apply targets** — `POST /launch-readiness/apply-next-enrichment-targets` with body `{ "limit": 20, "area_keys": [...] }` to apply targets into the canonical Supabase store. See [APPLY_ENRICHMENT_TARGETS.md](APPLY_ENRICHMENT_TARGETS.md).

## Key Files

- `backend/post_sync_remediation_report.py` — Report logic, scoring, target building
- `backend/launch_readiness_report.py` — Base report (extended with canonical metrics)
- `backend/local_profile_supabase_sync.py` — `get_sync_status`
- `backend/apply_enrichment_targets.py` — Bulk apply targets to canonical store
- `backend/main.py` — Endpoints

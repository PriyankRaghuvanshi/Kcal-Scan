# Launch Readiness Report

## Why this report exists

Healthy Nearby must produce **concrete value**, not just "Google Places with healthy guesses". If we only show nearby places plus generic cuisine heuristics, users will see no difference from Google Maps and uninstall.

This report measures, by suburb/area, whether Healthy Nearby is actually adding value beyond Google Places.

## What it measures

1. **Speed** — How fast Healthy Nearby responds (p50, p90, avg ms)
2. **Specificity** — How specific top recommendations are (chain/local vs generic)
3. **Concrete value** — Whether top results have concrete orders, specific swaps, high confidence
4. **Genericity** — Whether results collapse into duplicate/generic templates
5. **Missing winners** — Whether obvious chains (Subway, McDonald's, etc.) are fetched but hidden
6. **Local enrichment** — How much chain + local profile coverage vs generic fallback

## Endpoints

- **`GET /launch-readiness/report?area_key=parramatta`** — Full report for one area
- **`GET /launch-readiness/report?area_key=parramatta&include_examples=false`** — Report without example sections
- **`GET /launch-readiness/report/all`** — Summaries for all configured launch areas
- **`GET /launch-readiness/remediation?top_n_suburbs=2&samples_per_area=2`** — Prioritized remediation for top N worst suburbs (missing chains, generic venues, cuisines, duplicate clusters)
- **`GET /launch-readiness/post-sync-report?area_key=parramatta`** — Post-sync report with canonical metrics (see [POST_SYNC_REMEDIATION_REPORT.md](POST_SYNC_REMEDIATION_REPORT.md))
- **`GET /launch-readiness/post-sync-report/all?limit_areas=5`** — Post-sync reports for priority areas
- **`GET /launch-readiness/next-enrichment-targets?limit=20`** — Next 20 prioritized enrichment targets

## Specificity score (0–5)

| Tier | Score | Meaning |
|------|-------|---------|
| exact_menu_match | 5 | Real menu / user scan |
| exact_local_profile | 5 | Matched by place_id to local profile |
| chain_registry | 4 | Chain-backed (Subway, McDonald's, etc.) |
| enriched_local_profile | 4 | Local venue profile (Darbar, Madras Cafe, etc.) |
| menu_inferred | 3 | LLM-inferred (if enabled) |
| heuristic_cuisine_match_strong | 2 | Strong cuisine heuristic |
| heuristic_cuisine_match_weak | 1 | Weak heuristic |
| generic_fallback | 0 | "Lighter menu option", "tandoori + dal + roti", etc. |

Higher = more trustworthy. We want top results to have score ≥ 4.

## Concrete-value metric rules

### A. Concrete order

A recommendation counts as **concrete** if:
- `best_item_name` exists
- And is **not** generic filler like:
  - "egg + chicken plate"
  - "protein bowl"
  - "tandoori + dal + roti" (generic pattern)
  - "lighter menu option", "healthy option"

### B. Specific swap

- `best_item_swaps` exists
- Swap labels are realistic (e.g. "No mayo", "Thin crust", "Extra salad")

### C. High confidence

- `confidence_label` in **Verified** or **Estimated** (not "Needs menu check")

### D. Clear difference reason

- `rank_reason_short` exists and is meaningful (not just "Check menu" or "Good fallback")

## Readiness statuses

| Status | Meaning |
|--------|---------|
| **launch_ready** | Speed, specificity, concrete-value pass thresholds |
| **too_slow** | p90 response time > 5s |
| **too_generic** | Top-5 generic fallback % too high, or top-3 concrete % too low |
| **needs_local_enrichment** | Local profile usage low while generic % high |
| **chain_coverage_gap** | Known chains often fetched but hidden from top 5 |
| **mixed** | Multiple issues |
| **no_data** | No sample points or fetch failed |

## Thresholds (tunable)

- `THRESHOLD_P90_MS` = 5000
- `THRESHOLD_TOP5_GENERIC_PERCENT` = 60
- `THRESHOLD_TOP3_CONCRETE_PERCENT` = 50
- `THRESHOLD_LOCAL_PROFILE_USAGE_PERCENT` = 10
- `THRESHOLD_CHAIN_HIDDEN_RATE` = 0.5

## Sample points

If `sample_points` are not provided, the report generates a default set around the area center:
- center
- north, south, east, west offsets within area radius

For reproducible reports, pass explicit `sample_points` with `lat`, `lng`, and optional `label`.

## Report fields

### Speed
- `avg_total_response_ms`, `p50_total_response_ms`, `p90_total_response_ms`
- `avg_fetched_places`, `avg_shortlisted_places`, `avg_deep_ranked_places`

### Specificity
- `percent_top_1_exact_or_chain_backed`
- `percent_top_3_exact_chain_or_enriched_local`
- `percent_top_5_generic_fallback`
- `avg_specificity_score_top_3`, `avg_specificity_score_top_5`

### Concrete value
- `percent_top_3_with_concrete_order`
- `percent_top_3_with_specific_swap`
- `percent_top_3_with_high_confidence`
- `percent_top_3_with_non_generic_item_name`
- `percent_top_3_with_clear_difference_reason`

### Genericity
- `duplicate_score_cluster_rate_top_5`
- `duplicate_candidate_name_rate_top_5`
- `percent_top_5_same_cuisine_generic_guess`
- `generic_indian_cluster_count`, `generic_cafe_cluster_count`, `generic_juice_cluster_count`

### Missing chains
- `known_chain_fetched_count`, `known_chain_visible_top_5_count`, `known_chain_hidden_count`
- `top_missing_chain_examples`

### Local enrichment
- `local_enrichment` (from `summarize_launch_area_coverage`) — includes `pack_seeded_profiles` when launch enrichment pack has been run
- `visible_results_using_local_profiles_percent`
- `visible_results_using_chain_registry_percent`
- `visible_results_using_generic_fallback_percent`

### Launch enrichment pack

To accelerate local enrichment and reduce generic fallback:
- **`POST /launch-enrichment/seed`** — Seed local venue profiles from the pack. Body: `{ area_key?, limit_areas?, limit_per_area? }`
- **`GET /launch-enrichment/status`** — Status of pack definitions vs profiles in store

See [LOCAL_VENUE_ENRICHMENT.md](LOCAL_VENUE_ENRICHMENT.md) for diet-aware templates and how seeded profiles affect live ranking.

## Using the report

1. **Pre-launch** — Run reports for each suburb. Fix `too_generic` and `needs_local_enrichment` by adding local profiles (see [LOCAL_VENUE_ENRICHMENT.md](LOCAL_VENUE_ENRICHMENT.md)).
2. **Chain coverage** — If `chain_coverage_gap`, investigate why Subway/McDonald's etc. are hidden (trace, score gap).
3. **Speed** — If `too_slow`, tune shortlist size, cache, or API usage.
4. **Prioritization** — Use `launch_ready` vs `mixed` to decide which suburbs go first.

## Remediation workflow

`/launch-readiness/remediation` turns report output into concrete product fixes:

1. Fetches reports for all launch areas with `remediation_extended=True`
2. Ranks suburbs by composite score (generic %, hidden chain rate, duplicate rate)
3. Surfaces top N worst suburbs with full remediation lists:
   - **top_10_missing_chain_opportunities** — Known chains fetched but not in top 5
   - **top_10_generic_fallback_venues** — Venues showing generic items (protein bowl, tandoori+dal, etc.)
   - **top_cuisines_needing_enrichment** — Cuisines inferred from generic venues (indian, cafe, etc.)
   - **top_duplicate_score_clusters** — Score values shared by 2+ places (rank collapse)

Use this to prioritize local enrichment and chain-registry fixes by suburb.

## Post-sync remediation

After canonical Supabase sync, run a post-sync pass to measure quality and get the next enrichment targets:

- **`GET /launch-readiness/post-sync-report`** — Report with `canonical_profile_count`, `pack_seeded_profiles`, etc.
- **`GET /launch-readiness/next-enrichment-targets`** — Prioritized list of venues to enrich (default 20)

See [POST_SYNC_REMEDIATION_REPORT.md](POST_SYNC_REMEDIATION_REPORT.md) for full documentation.

## Key files

- `backend/launch_readiness_report.py` — Report generator, metrics, grading, remediation_extended
- `backend/suburb_remediation.py` — Remediation ranking, build_remediation_list, generate_prioritized_remediation
- `backend/post_sync_remediation_report.py` — Post-sync report, next-enrichment targets, scoring
- `backend/launch_area_config.py` — `sample_points_for_area`
- `backend/local_launch_enrichment_pack.py` — Launch enrichment pack, seed helpers (syncs to Supabase after seed)
- `backend/local_profile_supabase_sync.py` — Canonical Supabase sync for pack + auto-promoted profiles
- `backend/main.py` — `/launch-readiness/*`, `/launch-enrichment/*`, `/local-profiles/sync/*`

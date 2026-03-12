# Apply Enrichment Targets

## Purpose

Take the prioritized output from **`GET /launch-readiness/next-enrichment-targets`** and convert it into actual trusted local profile improvements in the **canonical Supabase store**:

- Add missing local profiles
- Expand existing profiles with more templates/swaps
- Add diet-safe (vegetarian/vegan) variants
- Add swap templates
- Fix generic templates with more specific ones
- Skip chain-gap targets (do not treat as local venue fixes)

No LLM. No live menu fetch in `/places/healthy`. No ranking changes. Structured enrichment only.

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/launch-readiness/apply-next-enrichment-targets` | Fetch next-enrichment targets then bulk apply to canonical store. Body: `{ "limit": 20, "area_keys": ["wentworthville", "parramatta"] }` (optional). |
| POST | `/launch-readiness/apply-enrichment-targets` | Apply an explicit list of targets. Body: `{ "targets": [ ... ], "limit": 20 }`. Use when you already have the output of next-enrichment-targets. |

## How Next-Enrichment Targets Become Profile Updates

1. Each target has a **`recommended_enrichment_action`** (e.g. `add_profile_now`, `expand_existing_profile`, `add_veg_vegan_variants`, `add_swaps`, `fix_generic_template`, `review_chain_gap`).
2. **`build_profile_update_from_target(target)`** builds a deterministic update payload (templates/swaps) from the target’s `cuisine_guess`, `area_key`, and action. No LLM; uses fixed patterns per cuisine.
3. **`apply_enrichment_target(target)`** loads the existing profile from Supabase (by `place_id` or `normalized_name` + `area_key`), merges the update via **`merge_trusted_profile_sources`** (no duplicate `template_key`/`swap_key`), then **`upsert_trusted_profile_to_supabase`**.
4. **`review_chain_gap`** targets are **skipped** and marked as `skipped_reason: chain_gap`; they are not written as local venue profiles.

## Action-to-Update Mapping

| Action | Behavior |
|--------|----------|
| **add_profile_now** | Create canonical profile if missing. Seed 1–3 strong candidate templates by cuisine (e.g. Indian: tandoori+dal, chicken tikka, dal+roti; Cafe: eggs on toast, grilled chicken wrap, omelette+toast). Add 1–2 plausible swaps. |
| **expand_existing_profile** | Append 1–2 additional candidate templates and swaps. No overwrite of existing templates. |
| **add_veg_vegan_variants** | Add only vegetarian/vegan-safe templates (e.g. dal+roti, paneer+dal, green smoothie). Diet flags set correctly; no meat/dairy in vegan variants. |
| **add_swaps** | Add realistic swap templates only (e.g. light raita, skip naan for Indian; skip hash browns for cafe). No vague placeholders. |
| **fix_generic_template** | Add more specific templates (same patterns as add_profile_now/expand). Does not destructively delete; merge only adds new template_key. |
| **review_chain_gap** | Skip. Return `skipped_reason: chain_gap`. Do not create or update local profile for chain-only gaps. |

## Template Generation Rules (Deterministic)

Templates are generated from **cuisine/category** and **target context** only. Examples:

- **Indian**: Chicken tikka + salad, Tandoori chicken half + dal, Paneer tikka + dal, Dal + roti (vegan-safe).
- **Cafe**: Eggs on toast, Grilled chicken wrap, Omelette + toast, Avocado toast + poached egg.
- **Juice/smoothie**: Green smoothie (spinach, apple, ginger), Protein smoothie (banana, milk, protein). Vegan-safe variants where plausible.

Vague placeholders like “protein bowl”, “lighter menu option”, “healthy meal” are **not** created.

## Idempotency Rules

- **Reruns are safe.** `merge_trusted_profile_sources` appends only templates with new `template_key` and swaps with new `swap_key`. Duplicate keys are not re-added.
- Stronger existing source metadata is preserved (e.g. `curated_manual` > `bulk_enrichment_target`). New profiles get `profile_source = bulk_enrichment_target`.

## Source Metadata

- **profile_source** = `bulk_enrichment_target` for new profiles created by bulk apply. Existing profiles keep their higher-priority source when only appending templates/swaps.
- **Template-level** `profile_source` on added templates is set to `bulk_enrichment_target`.
- **seeded_by_launch_pack** remains `false` for bulk-applied profiles (distinct from launch pack).
- Trace/audit already expose: `profile_store`, `local_profile_source`, `chosen_candidate_profile_source`, `seeded_by_launch_pack`. Profiles from bulk apply will show `profile_source` / `chosen_candidate_profile_source` as `bulk_enrichment_target` where applicable.

## Result / Summary Shape

Bulk apply response:

- **targets_considered** — Number of targets processed.
- **targets_applied** — Count applied successfully.
- **targets_skipped** — Count skipped (e.g. chain_gap, upsert_failed).
- **applied_by_action** — Map of action → count (e.g. `{"add_profile_now": 5, "add_swaps": 2}`).
- **skipped_by_reason** — Map of reason → count (e.g. `{"chain_gap": 3}`).
- **sample_results** — Up to 20 result objects. Each has: `place_name`, `area_key`, `recommended_enrichment_action`, `applied`, `profile_created`, `templates_added`, `swaps_added`, `skipped_reason`.

Example sample result:

```json
{
  "place_name": "Cafe A",
  "area_key": "parramatta",
  "recommended_enrichment_action": "add_profile_now",
  "applied": true,
  "profile_created": true,
  "templates_added": 2,
  "swaps_added": 1
}
```

## How to Run the Bulk Apply Endpoint

1. **Option A – Apply next N targets (recommended)**  
   `POST /launch-readiness/apply-next-enrichment-targets`  
   Body: `{ "limit": 20, "area_keys": ["wentworthville", "parramatta"] }`  
   The server fetches next-enrichment targets (same logic as GET next-enrichment-targets) then applies them.

2. **Option B – Apply explicit target list**  
   First: `GET /launch-readiness/next-enrichment-targets?limit=20`  
   Then: `POST /launch-readiness/apply-enrichment-targets`  
   Body: `{ "targets": <paste targets array>, "limit": 20 }`

## Rerun Post-Sync Report After Application

After bulk apply, re-measure launch-area quality:

1. `GET /launch-readiness/post-sync-report/all?limit_areas=5`
2. `GET /launch-readiness/next-enrichment-targets?limit=20`

You should see lower generic fallback % and more `visible_results_using_local_profiles_percent` where profiles were added or expanded.

## Key Files

- **backend/apply_enrichment_targets.py** — `build_profile_update_from_target`, `apply_enrichment_target`, `apply_enrichment_targets`, `apply_next_enrichment_targets`
- **backend/local_profile_supabase_sync.py** — `merge_trusted_profile_sources`, `SOURCE_PRECEDENCE` (includes `bulk_enrichment_target`)
- **backend/supabase_intelligence_store.py** — `get_local_venue_profile`, `upsert_trusted_profile_to_supabase`
- **backend/post_sync_remediation_report.py** — Action constants, target shape
- **backend/main.py** — POST endpoints

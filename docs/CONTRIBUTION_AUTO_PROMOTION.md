# Contribution Auto-Promotion

## Goal

Replace manual-review bottlenecks with an evidence-based auto-promotion pipeline. Most safe, repeated user contributions auto-promote into trusted local venue profiles. Only conflicts, risky changes, and diet-sensitive edge cases remain for manual review.

No LLM. No blind auto-accept. Deterministic evidence thresholds.

## Trust Layers

| Layer | Description | Used for live ranking |
|-------|-------------|------------------------|
| **A. Raw contributions** | All user submissions stored immediately. No blocking. | No |
| **B. Aggregated evidence** | Per place + normalized suggestion + diet context + contribution type. Counts, conflict signals. | No |
| **C. Trusted local venue profiles** | Only auto-promoted or explicitly approved. | Yes |

## Grouping / Signature Logic

Contributions are grouped by a stable signature:

- `place_id` (preferred) or `normalized place_name + area_key`
- `contribution_type`
- `normalized suggested item name`
- `diet_context` (vegetarian, vegan, or empty)

Example: **Darbar** + `better_order_suggestion` + `"paneer tikka + dal"` + vegetarian → one aggregate group.

## Evidence Scoring

Promotion score formula (bounded -50 to 100):

```
score =
  (unique_user_count * 4)
  + (same_suggestion_repeat_count * 3)
  + (supporting_feedback_count * 3)
  + (chosen_count * 3)
  + (helpful_count * 2)
  - (conflict_count * 4)
  - (contradictory_feedback_count * 4)
  - (item_not_on_menu_count * 5)
  - (veg_conflict_count * 5)
  - (vegan_conflict_count * 6)
```

Returns: `promotion_score`, `positive_reasons`, `blocking_reasons`, `safety_flags`.

## Promotion Thresholds / Rules

**Auto-promote** when ALL are true:

- `unique_user_count >= 2` OR `total_submission_count >= 3`
- `promotion_score >= threshold` (default 8, configurable via `CONTRIBUTION_PROMOTION_THRESHOLD`)
- No hard conflict
- Not blocked by diet-safety issue
- Contribution type is promotable
- Suggestion is not too vague / generic / empty

**Promotable types:** `better_order_suggestion`, `vegetarian_option_missing`, `vegan_option_missing`, `recommendation_accurate`, `menu_item_correction`.

## Blocked / Review-Needed Rules

**Hard blockers:**

- Strong vegan/vegetarian contradiction (e.g. "cheese" in vegan suggestion)
- High `item_not_on_menu` evidence
- Suggestion too generic: "healthy option", "protein bowl", "lighter menu", etc.
- Very low information content
- Explicit conflicts between repeated submissions

**Diet-safe rules:**

- Vegan suggestion must NOT auto-promote if item likely contains dairy/egg/whey/meat unless explicitly safe
- Vegetarian suggestion must NOT auto-promote if item likely contains meat/chicken/fish
- Uncertainty → mark `review_needed`, do not auto-promote

If blocked: keep in raw layer, mark `review_needed` or `conflict_pending`, optionally enqueue for manual review.

## How Promoted Contributions Update Local Profiles

Promotion does NOT destructively overwrite:

1. **New local candidate template** – when no matching template exists
2. **Confidence boost** – for existing matching template (e.g. repeated `recommendation_accurate`)
3. **New diet-safe variant** – tagged with diet_context
4. **Profile note / evidence metadata** – stored on template when supported

**Rules:**

- Do not delete existing trusted templates
- If conflict with existing trusted template → mark for review, do not hard overwrite
- Source metadata on promoted templates: `profile_source = auto_promoted` or `community_confirmed`, `promoted_from_contribution_ids`, `promoted_at`, `evidence_score`, `support_count`

## Audit Trail

Each promotion decision is logged to `contribution_auto_promotion_audit.json`:

| Field | Description |
|-------|-------------|
| `promotion_id` | UUID |
| `place_id` | Place identifier |
| `aggregate_signature` | Group signature |
| `contribution_ids` | Contributing contribution IDs |
| `action_type` | See below |
| `applied_changes` | JSON of changes |
| `evidence_score` | Promotion score |
| `created_at` | ISO timestamp |

**Action types:**

- `auto_promoted_new_template`
- `auto_promoted_confidence_boost`
- `auto_promoted_new_swap`
- `promotion_blocked_conflict`
- `promotion_blocked_diet_risk`
- `promotion_blocked_low_evidence`

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/venue-contributions/auto-promote/run` | POST | Run auto-promotion. Body: `{ place_id?, area_key?, place_name?, limit? }` |
| `/venue-contributions/auto-promote/status` | GET | Status for a place. Params: `place_id?`, `area_key?` |

Admin/debug utilities. Safe to call repeatedly.

## Enrichment Queue Integration

When a contribution group is **blocked** but **near promotion threshold** (e.g. `insufficient_evidence`, `promotion_score_below_threshold`), the place is enqueued for background enrichment with higher priority. This surfaces venues that may soon qualify for auto-promotion.

**Near-threshold:** `total_submission_count >= 2` OR `unique_user_count >= 2` OR `promotion_score >= threshold - 4`.

**Enqueue reasons (by contribution type):**

| Contribution type | Reason |
|-------------------|--------|
| `vegan_option_missing` | `vegan_option_repeated` |
| `vegetarian_option_missing` | `vegetarian_option_repeated` |
| `better_order_suggestion` | `better_order_repeated` |
| conflict in blocked_reason | `conflict_needs_review` |
| other | `user_correction_high_signal` |

**Requires:** `place_id` must be present (enqueue skips when only `place_name` + `area_key`). 24h suppression prevents repeat enqueues.

## Live Integration

Promoted templates become available via:

- **Supabase canonical store** – Auto-promoted profiles are upserted to Supabase after promotion. See [SUPABASE_LOCAL_PROFILE_CANONICAL_STORE.md](SUPABASE_LOCAL_PROFILE_CANONICAL_STORE.md).
- `local_venue_enrichment` – `enrich_place_with_local_profile` reads Supabase first, then JSON fallback.
- Trace/audit: `profile_source`, `profile_store` (supabase_canonical | fallback_local_store), `promoted_from_contribution_ids`, `evidence_score`

Ranking benefits via local profile specificity as before.

## Key Files

- `backend/contribution_auto_promotion.py` – aggregation, scoring, promotion logic
- `backend/user_venue_contributions.py` – raw store, `list_all_contributions`
- `backend/local_venue_profiles.py` – `add_candidate_template`, `profile_source` values
- `backend/background_enrichment_queue.py` – new reasons for near-threshold groups
- `backend/data/contribution_auto_promotion_audit.json` – audit trail

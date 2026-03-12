# Supabase as Canonical Trusted Local Venue Store

## Goal

Supabase is the **canonical trusted local venue store**. All launch-pack seeded and auto-promoted profiles are synced into Supabase so there is one durable source of truth for trusted local venue intelligence.

## Why Supabase is Canonical

- **Durable** – Profiles persist across deploys, file resets, and local JSON changes
- **Single source of truth** – Reduces drift between pack, auto-promotion, and manual curation
- **Live path consistency** – Healthy Nearby and Smart Alerts read from one store first

## Trusted Sources Synced

| Source | Precedence | Description |
|--------|------------|-------------|
| curated_manual | 1 (highest) | Human-curated, never overwritten by lower sources |
| community_confirmed | 2 | User contributions confirmed by community evidence |
| auto_promoted | 3 | Contribution auto-promotion |
| launch_enrichment_pack | 4 (lowest) | Structured pack for launch suburbs |

## Source Precedence Rules

When the same venue exists in multiple sources:

1. **Profile-level fields** – Higher-priority source wins (`profile_source`, `seeded_by_launch_pack`)
2. **Templates** – New non-conflicting templates from any source are appended
3. **Swaps** – Same rule: append by `swap_key`, no overwrite of existing
4. **Conflicts** – Existing trusted data is preserved; no destructive overwrites

## Merge Rules

- `merge_trusted_profile_sources(existing, incoming)` produces a safe merged profile
- Templates deduped by `template_key`
- Swaps deduped by `swap_key`
- Name variants, cuisine tags merged as sets

## Sync Flow

1. **Launch pack seed** – After `seed_launch_area_enrichment`, a best-effort sync runs
2. **Auto-promotion** – After `auto_promote_contribution_group` adds a template, that profile is upserted to Supabase
3. **Manual sync** – `POST /local-profiles/sync/supabase` runs full sync

All sync is **idempotent**: reruns do not create duplicates; merge logic handles repeats safely.

## Fail-Open Behavior

- **Read path** – `get_local_venue_profile` tries Supabase first, then falls back to JSON
- **Sync** – If Supabase is unavailable, sync returns `{synced: 0, failed: N}`; no exception
- **Live ranking** – Always continues; JSON fallback ensures recommendations still work

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/local-profiles/sync/supabase` | POST | Sync to Supabase. Body: `{ sync_launch_pack?, sync_auto_promoted?, area_key?, limit? }` |
| `/local-profiles/sync/status` | GET | Status: canonical count, pack/auto counts. Params: `area_key?` |

## Audit / Trace Fields

| Field | Description |
|-------|-------------|
| `profile_store` | `supabase_canonical` or `fallback_local_store` |
| `local_profile_source` | curated_manual, auto_promoted, community_confirmed, launch_enrichment_pack |
| `chosen_candidate_profile_source` | Source of the chosen template |
| `seeded_by_launch_pack` | Profile was seeded from launch pack |

## Schema Requirements

The Supabase `local_venue_profiles` table should have:

- `place_id` (text, nullable) – unique when not null
- `area_key` (text)
- `normalized_name` (text)
- `place_name` (text)
- `name_variants` (jsonb)
- `candidate_templates` (jsonb)
- `swap_templates` (jsonb)
- `profile_source` (text)
- `seeded_by_launch_pack` (boolean)
- `coverage_status`, `confidence_tier`, `specificity_tier`, `active`, etc.

For upsert: `UNIQUE(place_id)` where `place_id IS NOT NULL`. For name-only profiles, sync uses PATCH by `id` when an existing row matches `area_key` + `normalized_name`, or INSERT when no match.

## Key Files

- `backend/local_profile_supabase_sync.py` – Sync logic, merge rules
- `backend/supabase_intelligence_store.py` – `upsert_trusted_profile_to_supabase`, `get_local_venue_profile`
- `backend/local_venue_enrichment.py` – Read path with `profile_store` in enrich payload

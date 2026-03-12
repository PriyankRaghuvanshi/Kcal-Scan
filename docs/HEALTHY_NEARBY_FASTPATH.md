# Healthy Nearby fast path architecture

## Goal

Make Healthy Nearby fast and scalable by:
- Avoiding LLM and live menu fetching on the hot path
- Shortlisting before deep ranking to reduce work
- Using cached chain/local venue intelligence first
- Enabling systematic expansion of chain coverage
- Scaffolding background enrichment for low-specificity venues

## Fast path vs background path

### Fast path (live request)

The live `/places/healthy` request follows a strict fast path:

1. **Retrieve nearby places** — Google Places Nearby Search (New) only. No Place Details, no menu URLs.
2. **Normalize & classify** — Place types, names, coordinates. Cheap chain token check (name substrings).
3. **Shortlist** — Pre-rank by distance, type relevance, chain hint, cache hit, rating. Deep-rank only top N (default 10, max 20).
4. **Load cached intelligence** — `venue_intelligence_cache` lookup by `place_id`. Chain registry lookup by place name.
5. **Generate candidates** — From cache, chain registry, or heuristic. No LLM. No website fetch. No live parsing.
6. **Rank & return** — Canonical `build_ranked_place_profile`; specificity-aware tie-breaks; return top results.

**LLM is excluded from the hot path.** No `use_llm_place_context`, no menu ingestion, no website scrape during the user request.

### Background path

- **Enrichment queue** — Places with low specificity (generic fallback, heuristic-only) that reached top results are enqueued for later enrichment.
- **Future workers** — Will fetch menus, parse with LLM, resolve chain menus, and populate `venue_intelligence_cache`.
- **Over time** — Local venues that are frequently visible gain cached intelligence; generic fallback becomes less dominant.

## Shortlist strategy

Before deep ranking (menu scoring, health scoring, personalization), we pre-rank places with a cheap score:

| Factor            | Effect                          |
|-------------------|---------------------------------|
| Distance          | Closer = higher (e.g. ≤500 m +25) |
| Place type        | Restaurant-like types +12       |
| Chain token match | Name contains Subway, McDonald's, etc. +15 |
| Cache hit         | Place has cached intelligence +12 |
| Rating count      | High ratings +2–5               |

- **Shortlist size**: Default 10, max 20. Configurable via `HEALTHY_SHORTLIST_SIZE`.
- **Example**: Fetch 20 places → pre-rank → deep-rank only top 8–10. Skipped places are logged in `shortlist_debug`.

## Chain coverage architecture

`backend/chain_menu_registry.py` supports scalable expansion.

### Coverage types

- **global_chain** — Worldwide (e.g. McDonald's, Subway)
- **regional_chain** — Per country/market (e.g. Hungry Jack's in AU)
- **local_chain** — City or region

### Structure

- **Aliases & name matching** — Place name substrings map to chain keys.
- **Category-specific templates** — Sandwich chains get different item templates than pizza chains.
- **Swap rules** — Chain-specific portion/sauce/side swaps.
- **Market tags** — Optional `country_code` / `markets` (AU, US, IN, UK) for regional variants.

Adding a new chain is **data/config work**, not custom code. Extend the chain config with new entries; the registry resolves at runtime.

## Venue intelligence cache

`backend/venue_intelligence_cache.py` stores pre-computed menu/candidate data.

### Priority order

1. **Exact cache** — Place-specific stored candidates (from prior enrichment).
2. **Chain registry** — Resolved chain items for this place.
3. **Enriched local venue** — Manually or background-enriched profile.
4. **Heuristic cuisine fallback** — Generic cuisine-based guesses.

### Stored per place/chain

- `candidates` — List of items (name, calories, protein)
- `specificity_tier` — exact_menu_match, chain_registry, heuristic_*, generic_fallback
- `confidence` — 0–1
- `source_type` — chain_registry, enriched_local, heuristic
- `last_enriched_at` — TTL check
- `chain_key` / `chain_match` — Chain metadata
- Optional `swap_templates`

### Path

`backend/data/venue_intelligence_cache.json` (override: `VENUE_INTELLIGENCE_CACHE_PATH`).

## How local venues gain specificity

1. **Initial** — Venue appears with heuristic or generic fallback (e.g. "Lighter menu option").
2. **Enqueued** — If it reaches top results with low specificity, it is enqueued for enrichment.
3. **Background** — (Future) Worker fetches menu, runs LLM parse or chain match, writes to cache.
4. **Next request** — Cache hit; place gets chain-backed or menu-inferred candidates instead of generic.

## Debug and timing

### Query param `debug=true`

`GET /places/healthy?lat=...&lng=...&debug=true` returns `_debug`:

```json
{
  "_debug": {
    "timings_ms": {
      "nearby_fetch_ms": 180,
      "shortlist_ms": 2,
      "ranking_ms": 420,
      "total_ms": 602
    },
    "fetched_count": 18,
    "shortlisted_count": 10,
    "deeply_ranked_count": 10,
    "shortlist_debug": {
      "fetched_count": 18,
      "shortlisted_count": 10,
      "skipped_count": 8,
      "shortlist_size": 10,
      "skipped_reasons": { "low_pre_rank": 8 }
    }
  }
}
```

### Trace endpoint

`GET /places/healthy/trace?query_place_name=Subway` includes:

- `shortlist_debug` — Shortlist counts and skipped reasons
- `timings_ms` — Latency breakdown
- `fetched_count`, `shortlisted_count`, `deeply_ranked_count`

## Files

| File | Role |
|------|------|
| `backend/healthy_nearby_fastpath.py` | Shortlist, pre-rank, `run_fast_path()` |
| `backend/venue_intelligence_cache.py` | Cache get/put, `cache_to_menu_payload` |
| `backend/background_enrichment_queue.py` | Enqueue, list pending, `should_enqueue_for_low_specificity` |
| `backend/chain_menu_registry.py` | Chain resolution, coverage types |
| `backend/main.py` | Integrates shortlist, cache, enqueue; timing instrumentation |

## Env vars

- `USE_FAST_PATH` — Default 1; set 0 to disable shortlisting
- `HEALTHY_SHORTLIST_SIZE` — Default 10 (clamped 8–15)
- `VENUE_INTELLIGENCE_CACHE_PATH` — Override cache file path
- `BACKGROUND_ENRICHMENT_QUEUE_PATH` — Override queue file path

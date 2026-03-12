# Chain Menu Ingestion

## Why this exists

Healthy Nearby must deliver **concrete value** beyond Google Places. Generic fallback recommendations ("protein bowl", "tandoori + dal + roti") make ranking weak and untrustworthy. Major chains already publish official menu/nutrition data online. We leverage that—but **never** fetch or parse chain menus live on user requests.

## Architecture

### Offline ingestion pipeline

1. **Source adapters** (`chain_menu_sources.py`) — `fetch_chain_source` / `parse_chain_source`
2. **Normalization** (`chain_menu_normalization.py`) — raw → canonical schema
3. **Store** (`chain_menu_ingestion.py`) — JSON-backed `chain_menu_ingested.json`
4. **Live path** — `resolve_chain_menu_for_place` reads only from cache/store

### Speed rule

**Absolutely no live fetching in `/places/healthy`.**

Live path uses only (in order):
- Venue intelligence cache (`venue_intelligence_cache`) – per-place cached candidates
- Local venue profiles (`local_venue_profiles`) – curated independents in launch areas
- Cached ingested chain items
- Chain registry templates
- Deterministic heuristics

## Ingestion schema

| Field | Description |
|-------|-------------|
| chain_key | Subway, mcdonalds, kfc, etc. |
| source_type | official_website_menu, curated_seed |
| source_url | URL for audit |
| market_tag | AU, US, etc. |
| item_key | Stable key (chain_itemname) |
| item_name | Display name |
| category | sub, burger, salad |
| estimated_calories, *_protein_g, *_fat_g, *_carbs_g | Macros |
| confidence | 0.45–0.98 |
| chosen_candidate_specificity_tier | exact_menu_match or chain_registry |
| last_ingested_at | ISO timestamp |

## Source adapters

First 4 chains with full adapter scaffolding:
- **subway_au**
- **mcdonalds_au**
- **kfc_au**
- **dominos_au**

Implementation:
- Curated seed from `chain_menu_coverage.json` (no live fetch)
- `parse_chain_source(raw_content, chain_key, market_tag)` normalizes items
- `fetch_chain_source` returns None by default (background job only)

## First 10 chain coverage

| Chain | Status |
|-------|--------|
| Subway | Ingested |
| McDonald's | Ingested |
| KFC | Ingested |
| Hungry Jack's | Ingested |
| Domino's | Ingested |
| Pizza Hut | Ingested |
| Guzman y Gomez | Ingested |
| Oporto | Ingested |
| Grill'd | Ingested |
| Boost Juice | Ingested |

Chains use either:
- Ingested exact items (preferred)
- Chain registry templates (fallback)

Not generic cuisine guesses.

## Running ingestion

```bash
cd backend
python scripts/run_chain_ingestion.py
```

Or programmatically:
```python
from chain_menu_ingestion import run_ingestion_all
run_ingestion_all(market_tag="AU", max_items_per_chain=30)
```

## Candidate priority

1. **Exact ingested chain item** — from `chain_menu_ingested.json`
2. **Chain registry template** — from `chain_menu_coverage.json`
3. **Enriched local profile**
4. **Cuisine heuristic**
5. **Generic fallback**

## Debug / audit visibility

Trace/audit exposes:
- `chain_source_used`: `ingested_chain_item` | `chain_registry_template` | country/global
- `menu_item_source`: `ingested_chain_item` when from ingestion
- `chosen_candidate_specificity_tier`: `exact_menu_match` for ingested
- `last_ingested_at`, `source_url` when available

## Key files

- `backend/chain_menu_ingestion.py` — Store, `get_chain_items`, `run_ingestion_for_chain`
- `backend/chain_menu_sources.py` — Adapters, `parse_chain_source`
- `backend/chain_menu_normalization.py` — Schema, `normalize_raw_item`
- `backend/chain_menu_registry.py` — Prefers ingested over template
- `backend/data/chain_menu_ingested.json` — Persisted store

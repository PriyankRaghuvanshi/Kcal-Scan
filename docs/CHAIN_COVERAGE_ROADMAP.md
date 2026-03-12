# Chain coverage roadmap

## Goal

Turn chain support into a maintainable, scalable system so Healthy Nearby coverage expands systematically—not ad hoc. Adding a new chain is mostly **data/config work**, not custom logic.

## Chain schema

Each chain roadmap entry supports:

| Field | Type | Description |
|-------|------|-------------|
| `chain_key` | string | Unique identifier (e.g. `subway`, `mcdonalds`) |
| `display_name` | string | Human-readable name |
| `aliases` | string[] | Name variants for matching (Subway, Sub-way, Maccas, etc.) |
| `market_tags` | string[] | Markets (AU, US, GB, NZ, IN) |
| `cuisine_tags` | string[] | Cuisine type (sandwich, burger, mexican) |
| `category_tags` | string[] | Category (fast_food, fast_casual, cafe) |
| `rollout_priority` | enum | See below |
| `confidence_tier` | enum | See below |
| `coverage_status` | enum | See below |
| `supports_swaps` | bool | Chain supports swap suggestions |
| `menu_template_count` | int | Number of menu templates |
| `notes` | string | Favored vs demoted items, expansion notes |

### rollout_priority

| Value | Meaning |
|-------|---------|
| `p0_core_trust` | Highest trust builders (Subway, McDonald's, etc.) |
| `p1_high_value` | Strong healthy-option relevance |
| `p2_regional_growth` | Regional expansion targets |
| `p3_long_tail` | Lower priority, long-tail chains |

### confidence_tier

| Value | Meaning |
|-------|---------|
| `tier_1_strong` | Strong nutrition data, verified |
| `tier_2_good` | Good data, some inference |
| `tier_3_basic` | Basic templates, heuristic |

### coverage_status

| Value | Meaning |
|-------|---------|
| `planned` | Roadmap only, not yet in chain_menu_registry |
| `partial` | Some items/templates, needs expansion |
| `live` | In chain_menu_registry, serving traffic |
| `enriched` | Full templates + swaps, high quality |

## Menu template schema

Per-chain menu templates:

| Field | Type | Description |
|-------|------|-------------|
| `template_key` | string | Unique key |
| `template_name` | string | Display name |
| `item_type` | string | sub, burger, bowl, pizza, etc. |
| `estimated_calories` | int | |
| `estimated_protein_g` | int | |
| `specificity_tier` | string | chain_registry |
| `cut_friendly` | bool | Suitable for cut/fat-loss goals |
| `food_quality_tags` | string[] | grilled, high_protein, etc. |
| `negative_flags` | string[] | fried, low_protein, etc. |
| `default_confidence` | float | 0–1 |
| `markets` | string[] | AU, US, etc. |
| `recommended_swap_keys` | string[] | Links to swap_templates |

## Swap template schema

| Field | Type | Description |
|-------|------|-------------|
| `swap_key` | string | Unique key |
| `swap_label` | string | User-facing label |
| `swap_type` | string | sauce_omit, add_vegetable, format_change, etc. |
| `calories_delta` | int | Estimated change |
| `protein_delta` | int | Estimated change |
| `reason` | string | Why this swap helps |
| `plausibility_score` | float | 0–1 |
| `markets` | string[] | Where applicable |

## First 50 chain roadmap

### Australia-first trust builders (1–25)

1. Subway — **live**, fully modeled  
2. McDonald's — **live**, fully modeled  
3. KFC — **live**, fully modeled  
4. Hungry Jack's — **live**, fully modeled  
5. Domino's — **live**, fully modeled  
6. Pizza Hut — **live**, fully modeled  
7. Guzman y Gomez — **live**, fully modeled  
8. Oporto — **live**, fully modeled  
9. Red Rooster — **live**  
10. Grill'd — **live**, fully modeled  
11. Nando's — **live**  
12. Boost Juice — **live**, fully modeled  
13. Soul Origin — partial  
14. Zambrero — **live**  
15. Mad Mex — planned  
16. Betty's Burgers — planned  
17. El Jannah — planned  
18. Crust Pizza — planned  
19. Starbucks — planned  
20. Krispy Kreme — planned  
21. Gloria Jean's — planned  
22. Sushi Hub — partial  
23. Roll'd — planned  
24. Jamaica Blue — planned  
25. Muffin Break — planned  

### Global trust builders (26–50)

26. Burger King — partial  
27. Taco Bell — planned  
28. Wendy's — planned  
29. Dunkin' — planned  
30. Chipotle — planned  
31. Panera Bread — planned  
32. Popeyes — planned  
33. Five Guys — planned  
34. Shake Shack — planned  
35. Chick-fil-A — planned  
36. Little Caesars — planned  
37. Papa John's — planned  
38. Carl's Jr / Hardee's — planned  
39. CAVA — planned  
40. Dutch Bros — planned  
41. Tim Hortons — planned  
42. Pret A Manger — planned  
43. Costa Coffee — planned  
44. Greggs — planned  
45. Jollibee — planned  
46. MOS Burger — planned  
47. Mixue — planned  
48. Baskin-Robbins — planned  
49. Panda Express — planned  
50. Wagamama — planned  

## Fully modeled chains (first 10)

These have 3–6 menu templates and 2–5 swap templates each. All first 10 chains:

- Use `chain_registry` specificity tier and `high` confidence
- Prefer chain-backed candidates over generic cuisine fallback when scores are close
- Have realistic chain-specific swaps (no mayo, thin crust, bowl instead of bread, etc.)

1. **Subway** — 6" grilled chicken, turkey, roast chicken bowl, veggie delite; swaps: no mayo, extra salad, bowl instead of bread, light dressing  
2. **McDonald's** — Hamburger, McChicken no mayo, Filet-O-Fish; swaps: no mayo, no tartar, water instead of soft drink, skip fries  
3. **KFC** — Tenders + side salad, fillet no mayo, Zinger no mayo; swaps: no mayo, skip gravy, side salad instead of chips  
4. **Hungry Jack's** — Whopper Jr no mayo, grilled chicken burger, garden salad + chicken; swaps: no mayo, extra salad  
5. **Domino's** — Thin crust chicken/margherita 2 slices, mini pizza + salad; swaps: thin crust, skip garlic bread, light cheese  
6. **Pizza Hut** — Thin n Crispy chicken/veg 2 slices, personal pan; swaps: thin n crispy base, skip garlic bread  
7. **Guzman y Gomez** — Grilled chicken burrito bowl, tacos, mini bowl; swaps: bowl instead of burrito, no sour cream  
8. **Oporto** — Grilled chicken Bondi burger, strip wrap, flame grilled salad; swap: no mayo  
9. **Grill'd** — Simply grilled chicken, bunless lighter burger, garden goodness bowl; swaps: bunless burger  
10. **Boost Juice** — Protein Supreme, All Berry Bang + protein, Mango Magic Lite; swaps: lower sugar blend, protein boost  

## How to add a new chain

1. **Add roadmap entry** in `backend/data/chain_coverage_roadmap.json`:
   - `chain_key`, `display_name`, `aliases`, `market_tags`
   - `rollout_priority`, `confidence_tier`, `coverage_status`
   - `notes` (what to favor vs demote)

2. **For live coverage**, add chain + items to `backend/data/chain_menu_coverage.json` (used by `chain_menu_registry`).

3. **For full templates**, add `menu_templates` and `swap_templates` to the roadmap entry.

4. **Optional**: Add identity record to `backend/data/global_chain_registry.json` for alias resolution.

No code changes required for data-only additions.

## Chain menu ingestion

Offline ingestion pipeline populates `chain_menu_ingested.json` with exact menu items from official sources. At runtime, **ingested items are preferred over registry templates**. See [CHAIN_MENU_INGESTION.md](CHAIN_MENU_INGESTION.md).

## Roadmap ↔ chain_menu_registry

- **chain_menu_registry** — Runtime: resolves place → chain → menu items. **Prefers** ingested items from `chain_menu_ingested.json`; falls back to `chain_menu_coverage.json`. This is the live path. No live fetch.
- **chain_coverage_roadmap** — Planning + templates: roadmap schema, priority, menu/swap templates. Uses `chain_coverage_roadmap.json`. Used for expansion planning and future template-based candidate generation.

The roadmap does not replace the registry. Chains in `coverage_status: live` should also have entries in `chain_menu_coverage.json`. The roadmap adds structure (priority, templates, swaps) that can feed future candidate generation or audit tooling.

## Helper API

| Function | Purpose |
|----------|---------|
| `list_chain_roadmap(rollout_priority=?, coverage_status=?, market_tag=?)` | List chains, optionally filtered |
| `get_chain_roadmap(chain_key)` | Get one chain's roadmap entry |
| `get_chain_templates(chain_key, market=?)` | Get menu templates |
| `get_chain_swaps(chain_key, template_key=?, market=?)` | Get swap templates (optionally for a specific menu template) |
| `match_chain_by_alias(place_name)` | Match place name to chain by alias |
| `list_chains_by_market(market_tag)` | List chains for a market |
| `validate_roadmap_schema()` | Validate schema; returns list of errors |

## Path override

`CHAIN_COVERAGE_ROADMAP_PATH` — Override the roadmap JSON path (default: `backend/data/chain_coverage_roadmap.json`).

## Local venue enrichment

For independents in launch suburbs, see `docs/LOCAL_VENUE_ENRICHMENT.md`. Local venue profiles provide chain-like specificity (candidates + swaps) for top local venues. Priority order: exact menu > chain > enriched local profile > heuristic > generic fallback.

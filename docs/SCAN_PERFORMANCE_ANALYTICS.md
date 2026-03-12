# Scan performance analytics

## Purpose

Measure and report scan performance so we can:
- Identify bottlenecks (vision, nutrition, meal_qa, enrichment)
- Track time-to-first-result vs time-to-final-result
- Monitor nutrition cache effectiveness
- Detect image resize savings

Analytics writes are **best-effort and non-blocking**. Scan success must never depend on analytics. If `record_scan_performance_event` fails, the scan still completes.

## Time definitions

### time_to_first_result_ms

Time from the moment the analysis pipeline **starts** (worker begins processing the job) until the **fast result** is first written and available to the client (when `on_fast_result` runs).

Includes: resize, priors, vision, nutrition, and building the fast result. Does **not** include: meal_qa, enrichment (storage, daily totals, coach), or any deferred work.

### time_to_final_result_ms

Time from pipeline start until `status=done` with full `result_json`. Includes all stages: resize, priors, vision, nutrition, meal_qa, enrichment.

**Baseline:** Both metrics use the same baseline: the time when `_run_analyze_pipeline` starts (which is when the worker picks up the job and begins work).

## Performance summary fields

`GET /scan-performance/summary?window_days=7` returns:

| Field | Description |
|-------|-------------|
| `total_scans` | Number of scans in the window |
| `median_time_to_first_result_ms` | p50 time to fast result |
| `median_time_to_final_result_ms` | p50 time to full result |
| `p90_time_to_first_result_ms` | p90 time to fast result |
| `p90_time_to_final_result_ms` | p90 time to full result |
| `median_vision_ms` | Median vision stage latency |
| `median_nutrition_ms` | Median nutrition stage latency |
| `median_meal_qa_ms` | Median meal_qa stage latency |
| `median_enrichment_ms` | Median enrichment stage latency |
| `median_resize_ms` | Median image resize latency |
| `median_priors_ms` | Median priors fetch latency |
| `cache_hit_rate` | nutrition_cache_hit_count / (hit + miss) across scans |
| `vision_cache_hit_rate` | fraction of scans that reused cached vision (skipped Gemini) |
| `vision_cache_hit_count` | total scans that reused cached vision in the window |
| `vision_cache_miss_count` | total scans that ran full vision in the window |
| `median_time_to_first_result_ms_when_vision_cache_hit` | p50 time when vision cache was reused (typically lower) |
| `median_time_to_first_result_ms_when_vision_cache_miss` | p50 time when full vision ran |
| `vision_cache_skipped_reasons` | counts by reason when cache existed but was not reused (low_confidence, no_items, etc.) |
| `average_image_resize_savings_pct` | % size reduction when image was resized |

## Identifying bottlenecks

1. **vision_ms dominates** – Consider model choice, timeout, or image sizing.
2. **nutrition_ms high** – Check cache hit rate; low hit rate suggests cache warming or normalization gaps.
3. **meal_qa_ms high** – Second LLM call; evaluate model or prompt efficiency.
4. **enrichment_ms high** – Storage, Supabase, or coach logic; consider async or batching.
5. **time_to_first_result >> sum of stages** – Overhead or blocking; inspect pipeline flow.
6. **time_to_final_result − time_to_first_result large** – meal_qa + enrichment are the gap; consider moving more work to deferred enrichment.

## Nutrition cache

See the nutrition resolution cache for lookup key normalization and caching. Cache hits avoid USDA API calls. Summary `cache_hit_rate` reflects how often repeated scans reuse cached nutrition for common foods.

## Vision result cache

`backend/vision_result_cache.py` caches vision classification output for near-identical resized images. When a scan image matches a cached fingerprint and the cached result passes safe-reuse rules, the pipeline skips the Gemini vision call and reuses the cached classification. This reduces `vision_ms` and improves `time_to_first_result_ms` for repeated scans of the same meal.

**Fingerprint:** SHA256 of the resized image bytes. Identical bytes → identical fingerprint.

**Safe reuse rules (conservative):**
- Cached `vision_confidence` ≥ threshold (default 0.72)
- Cached has non-empty `items`, each with valid `name` and `grams` > 0
- Item count ≤ 8 (avoid mixed/complex ambiguous meals)
- When in doubt, fall back to full vision

**Analytics fields (per event):** `vision_cache_reuse_used`, `vision_cache_skipped_reason`, `vision_cache_hit_count`, `vision_cache_miss_count`.

**Summary fields:** `vision_cache_hit_rate`, `vision_cache_hit_count`, `vision_cache_miss_count`, `median_time_to_first_result_ms_when_vision_cache_hit`, `median_time_to_first_result_ms_when_vision_cache_miss`, `vision_cache_skipped_reasons`.

**Why conservative:** Reusing a wrong classification for a different meal would misreport nutrition. We only reuse when the image is byte-identical (same fingerprint) and the cached result had sufficient confidence.

## Storage

Events are stored in `backend/data/scan_performance_events.json` (override with `SCAN_PERFORMANCE_EVENTS_PATH`). Same pattern as meal_feedback_store. Can be migrated to a DB later.

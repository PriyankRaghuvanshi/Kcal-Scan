# Healthy Nearby Audit Tool

Developer-only tool to inspect **why each restaurant ranked where it did** for Healthy Nearby. No ranking logic is changed; no LLM is used in the audit path. Use this to tune real cases (e.g. Chennai Filter, Darbar, Pizza Hut, Subway, local cafes).

**Candidate generation** now uses cuisine-specific archetypes (`backend/cuisine_candidate_rules.py`). The audit tool lets you inspect the chosen candidate and, with `include_candidate_debug=true`, the list of generated candidates per venue (primary + alternatives) so you can see why a given meal was selected and tune Indian / cafe / juice / pizza / Subway cases.

---

## 1. Audit endpoint

**Path:** `GET /places/healthy/audit`

**Query parameters:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `lat` | Yes | - | Latitude |
| `lng` | Yes | - | Longitude |
| `radius_m` | No | 3000 | Search radius in metres |
| `goal` | No | - | e.g. `cut`, `fat_loss` |
| `remaining_calories` | No | - | Remaining calories for the day |
| `remaining_protein_g` | No | - | Remaining protein (g) |
| `context_mode` | No | - | Explicit mode override (e.g. `post_workout_recovery`, `late_night_damage_control`) |
| `post_workout` | No | false | Post-workout recovery mode |
| `late_night` | No | false | Late-night damage-control mode |
| `local_hour` | No | 12 | Local hour 0–23 for breakfast/lunch/dinner inference |
| `poor_sleep_flag` | No | false | Slight satiety preference |
| `high_craving_risk_flag` | No | false | Penalty for hyper-palatable combos |
| `sort_mode` | No | `flat_score` | `flat_score` or `sectioned` |
| `limit` | No | 10 | Max results returned |
| `include_filtered_out` | No | false | If true, include places beyond `limit` in `filtered_out` |
| `include_candidate_debug` | No | false | If true, each result includes `candidate_debug`: list of generated candidates (name, calories, protein, source, confidence, why_kept) |
| `include_alert_candidates` | No | false | If true, response includes `alert_candidates`: smart food alert candidates (alert_type, alert_score, why_triggered, suppression_reasons, eligible_to_send). Push delivery uses same candidates via `POST /push/send-smart-alerts`. |
| `user_id` | No | - | If provided, results include personal memory fields (worked_before, personal_memory_label, averages, rates) |

Notes:
- Results now include **`selected_candidate_source`**, **`candidate_source_priority`**, and **`best_item_swaps`** (when available) so you can see whether the best item came from **real_menu** vs **chain_registry** vs heuristics, and what swaps we recommend.
- With `user_id`, results can also include: **`personal_memory_label`**, **`worked_before`**, **`avg_fullness`**, **`avg_craving_score`**, **`times_chosen`**, **`repeat_success_rate`**, **`swap_accept_rate`**.
- Personal-memory scoring fields:
  - `personal_history_bonus_100`, `personal_history_penalty_100`, `personal_history_net_100` (bounded in \[-6, +6])
  - `personal_memory_reason` (e.g. `positive:worked_before,strong_label` or `negative:label_cravings`)
  - `memory_sample_count`, `memory_applied`
- Context-aware ranking fields:
  - `context_bonus_100`, `context_penalty_100`, `context_net_100` (bounded in \[-8, +8])
  - `context_mode`, `context_reason`, `context_applied`, `context_components`

**Example:**

```bash
curl "http://localhost:8000/places/healthy/audit?lat=-33.80&lng=150.97&goal=cut&remaining_calories=700&remaining_protein_g=45&radius_m=2500&limit=10"
```

**Sample response shape:**

```json
{
  "query": {
    "lat": -33.8,
    "lng": 150.97,
    "radius_m": 2500,
    "goal": "cut",
    "remaining_calories": 700,
    "remaining_protein_g": 45,
    "sort_mode": "flat_score",
    "limit": 10
  },
  "summary": {
    "places_considered": 15,
    "places_returned": 10,
    "sort_mode": "flat_score",
    "generated_at": "2025-03-10T12:00:00.000000+00:00"
  },
  "results": [
    {
      "rank": 1,
      "place_name": "Darbar",
      "place_id": "ChIJ...",
      "distance_m": 450,
      "display_rank_score_100": 84,
      "meal_fitness_score_100": 84.0,
      "venue_prior_score_100": 82,
      "eligibility_band": 3,
      "section": "Best nearby",
      "recommendation_label": "Best pick",
      "confidence_label": "Verified",
      "rank_reason_short": "Higher protein, better whole-food option",
      "why_this_ranked_here": "...",
      "best_item_name": "Tandoori chicken + dal",
      "best_item_calories": 610,
      "best_item_protein": 42,
      "best_item_source": "real_menu",
      "best_item_is_generic_fallback": false,
      "best_item_needs_menu_check": false,
      "fit_today_score_100": 88.0,
      "calorie_fit_score_100": 85.0,
      "protein_fit_score_100": 90.0,
      "overshoot_penalty_100": 0.0,
      "score_breakdown": {
        "macro_fit": 80,
        "protein_density": 85,
        "food_quality": 82,
        "satiety": 75,
        "confidence": 88,
        "distance": 70,
        "price_value": 50,
        "personal_history": 50,
        "penalties": {
          "ultra_processed_penalty": 0,
          "combo_meal_penalty": 0,
          "deep_fried_penalty": 0,
          "sugary_drink_penalty": 0,
          "hyper_palatable_penalty": 0,
          "low_protein_density_penalty": 0,
          "generic_fallback_penalty": 0,
          "overshoot_penalty": 0
        }
      },
      "audit_one_liner": "#1 Darbar | Score 84 (+3 personal, +2 context) | Band 3 | Best pick | Verified | Tandoori chicken + dal | 610 kcal | 42g protein | Higher protein, better whole-food option"
    }
  ]
}
```

With `include_filtered_out=true`, the response also includes a `filtered_out` array (places beyond `limit`), each with `place_name`, `reason_filtered_out` (e.g. `"limit"`), and optional diagnostics.

---

## 2. CLI usage

**Script:** `backend/tools/audit_healthy_places.py`

**Prerequisites:** Backend running (e.g. `uvicorn main:app` from `backend/`), and `requests` installed.

**Examples:**

```bash
# From repo root (or set KCAL_AUDIT_BASE_URL if backend is elsewhere)
python backend/tools/audit_healthy_places.py \
  --lat -33.80 \
  --lng 150.97 \
  --goal cut \
  --remaining-calories 700 \
  --remaining-protein 45 \
  --radius-m 2500 \
  --limit 10
```

```bash
# Raw JSON
python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --json
```

```bash
# Markdown table (paste into docs/chats)
python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --markdown
```

```bash
# Include places beyond limit in output
python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --limit 5 --include-filtered-out
```

**CLI options:** `--lat`, `--lng` (required), `--radius-m`, `--goal`, `--remaining-calories`, `--remaining-protein`, `--sort-mode`, `--limit`, `--include-filtered-out`, `--context-mode`, `--post-workout`, `--late-night`, `--local-hour`, `--poor-sleep-flag`, `--high-craving-risk-flag`, `--base-url`, `--json`, `--markdown`.

---

## 3. Inspecting a real suburb / area

1. Get lat/lng for the area (e.g. map click or a known venue).
2. Call the audit endpoint or CLI with that `lat`, `lng`, and a `radius_m` (e.g. 2000–5000).
3. Set `remaining_calories` and `remaining_protein_g` to reflect a typical “lunch left” scenario if you care about fit_today and overshoot.
4. Use `sort_mode=flat_score` to see strict score order; use `sectioned` if you want the same section order as the app.
5. Use `audit_one_liner` for quick scan; use `score_breakdown` and `penalties` to see why a place is penalised or boosted.

---

## 4. Comparing Pizza Hut vs Indian / Subway / cafe

- Candidate generation is cuisine-specific: Indian → tandoori/dal/tikka; South Indian → idli/dosa/egg dosa; cafe → eggs on toast / wrap; juice → lower confidence, no invented protein bowl; pizza → thin-crust controlled portion; Subway → grilled chicken sub/salad bowl.
- Run the same query (same lat/lng, radius, goal, remaining calories/protein) and compare:
  - **display_rank_score_100** – main rank score; higher = better.
  - **eligibility_band** – band used for sections/labels (e.g. 3 = top tier).
  - **recommendation_label** – e.g. “Best pick”, “Strong option”, “Needs menu check”.
  - **confidence_label** – “Verified” vs “Estimated” vs “Needs menu check”.
  - **score_breakdown.penalties** – e.g. `generic_fallback_penalty`, `overshoot_penalty`, `ultra_processed_penalty`, `low_protein_density_penalty`.
  - **fit_today_score_100**, **calorie_fit_score_100**, **protein_fit_score_100**, **overshoot_penalty_100** – how well the best item fits the day.
- Use **audit_one_liner** to quickly compare Darbar vs Pizza Hut vs Subway vs a local cafe in one scan.

---

## 5. Interpreting key fields

- **display_rank_score_100** – Final ranking score 0–100 (= core + personal + context). Order in `flat_score` mode is by this (descending).
- **eligibility_band** – Integer band (e.g. 1–3); higher = stronger tier; used for sectioning and labels.
- **recommendation_label** – User-facing label (e.g. “Best pick”, “Strong option”, “Suggested healthier”, “Needs menu check”).
- **confidence_label** – “Verified” (real menu / high confidence), “Estimated”, or “Needs menu check”.
- **score_breakdown** – Components: macro_fit, protein_density, food_quality, satiety, confidence, distance, price_value, personal_history.
- **score_breakdown.penalties** – Why a place was pulled down: ultra_processed, combo_meal, deep_fried, sugary_drink, hyper_palatable, low_protein_density, generic_fallback, overshoot.
- **context_net_100**, **context_mode**, **context_components** – Context-aware modifier (e.g. post-workout, late-night, low calories left); bounded ±8.

### Smart Food Alerts (include_alert_candidates=true)

When `include_alert_candidates=true`, the response includes an **`alert_candidates`** array. Each candidate has:
- **alert_type** – protein_rescue, post_workout_recovery, late_night_damage_control, worked_before_repeat, habit_rescue
- **alert_score** – need + timing + quality + relevance − fatigue (threshold 55)
- **why_triggered** – e.g. `need:protein_rescue|score:78|protein:35g|dist:400m`
- **suppression_reasons** – e.g. max_alerts_6h, ignored_streak if suppressed
- **eligible_to_send** – true only when score ≥ 55, confidence strong, no suppression
- **audit_one_liner** – e.g. `protein_rescue | Score 91 | Subway | 30g protein | 4 min away | eligible`

**Debug endpoint:** `GET /smart-food-alerts/candidates` — same inputs as /places/healthy plus fatigue params (`recent_alerts_count_6h`, `recent_alerts_count_24h`, `weekly_alert_count`, `ignored_streak`, `recently_opened_app`, `recently_viewed_nearby`). Returns `candidates` with full payload and `audit_one_liner` per candidate. Use `eligible_only=true` to filter to sendable alerts.

---

## 6. Safety / scope

- This is a **dev/debug** tool. If your project restricts debug routes, protect this endpoint (e.g. behind a debug flag or only in non-production).
- The audit path **reuses** the same retrieval and canonical ranking as `GET /places/healthy`; it does not change ranking math.

---

## 7. Files and tests

- **Endpoint:** `backend/main.py` – `GET /places/healthy/audit`
- **Helpers:** `backend/healthy_places_audit.py` – `build_audit_one_liner`, `build_audit_result_row`, `build_filtered_out_entry`
- **CLI:** `backend/tools/audit_healthy_places.py`
- **Tests:** `backend/test_healthy_places_audit.py` – required fields, flat order, include_filtered_out, markdown columns, candidate_debug
- **Smart alerts:** `backend/smart_food_alerts.py` – `build_smart_food_alert_candidates()`; `backend/test_smart_food_alerts.py` – protein rescue, post-workout, late-night, worked-before, suppression, payload shape

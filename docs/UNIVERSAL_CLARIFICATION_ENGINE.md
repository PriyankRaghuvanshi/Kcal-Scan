# Universal Ingredient Clarification Engine — Design

**Goal:** When a user scans any food, the system should automatically identify meal type and components, detect hidden ingredients/add-ons/preparation choices that materially change calories or macros, ask the **minimum number** of highest-impact follow-up questions, remember answers for future scans, and work even when the meal was never explicitly hardcoded.

The food examples in the product brief (oatmeal, eggs, yogurt, coffee, smoothies, salads, curries, wraps, etc.) are **examples only**. This document describes a **general, reusable engine** that works across **any detected meal**.

---

## 1. Why example-based clarification logic is not enough

**Example-based logic** means: maintain a list of meal patterns (e.g. “oatmeal”, “coffee”, “salad”) and for each pattern hardcode a fixed set of questions (milk type, sweetener, dressing, etc.). That approach is insufficient for a universal engine.

- **Coverage ceiling:** Every new dish (biryani, pho, poke, dosa, shakshuka, acai bowl) requires a new rule. The long tail of global and regional foods is never fully covered, so users repeatedly get no clarification for unseen meals or irrelevant questions copied from a “similar” rule.
- **Brittleness:** Slight name variation (“savory oats”, “steel-cut oatmeal”, “oat bowl”) can miss the rule or match the wrong one. Regex or keyword rules don’t generalize across languages or naming styles.
- **No impact awareness:** All questions in a rule are treated equally. We don’t rank by calorie or macro swing, so we may ask low-impact questions while skipping high-impact ones.
- **Composition ignored:** A “bowl” or “plate” has multiple components (grain, protein, sauce, toppings). Rule-by-item doesn’t model meal-level ambiguity (e.g. “which protein?” vs “how much rice?” vs “oil in the sauce?”). We need a model that can attach dimensions to the right scope (item vs meal).
- **Duplicate and conflicting signals:** Vision already returns `ingredient_hints` and sometimes a single `clarifying_question`. A separate rule list duplicates part of that and can conflict (e.g. vision says “no dressing” but rule says “ask dressing”).
- **Maintenance cost:** Product wants “any current or future meal type.” Scaling by adding more meal-specific rules does not scale; we need a **dimension-based, impact-ranked, memory-aware** pipeline that can support unseen meals via taxonomy and optional LLM.

**Bottom line:** A universal engine must be driven by **generic dimensions of ambiguity** (added fat, dairy type, sweetener, protein type, starch portion, sauce richness, etc.), **impact ranking**, and **memory + inference**, with rules and optional LLM as **sources of candidate dimensions**, not as the sole definition of “what to ask.”

---

## 2. Universal clarification engine architecture

The engine is a **single pipeline** that runs for every scan. It does not branch by meal name; it branches by “do we have candidate dimensions, and which are still unresolved?”

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ INPUT: Scan result (items, vision_confidence, ingredient_hints,               │
│        optional meal_context, user_id, venue_id)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ A. AMBIGUITY DETECTION (dimension-agnostic)                                   │
│    For each item (and optionally meal): infer likely meal type/components,  │
│    then which dimensions are ambiguous. Sources:                              │
│    • Rules (pattern → dimensions)                                            │
│    • Taxonomy (meal category → likely dimensions)                             │
│    • Vision (ingredient_hints, cooking_method, label)                         │
│    • Optional LLM for unseen items                                           │
│    Output: list of (item_id, dimension_id, options, impact, inferred?)      │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ B. MEMORY LOOKUP                                                             │
│    user-level defaults + (user_id, food_token) + (user_id, venue_id)         │
│    Mark dimensions as resolved where we have a stored/default choice.         │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ C. INFERENCE FROM NAME / HINTS / LABEL                                        │
│    For each remaining dimension: resolve from item name, ingredient_hints,     │
│    or food label when confident. Remove from “need to ask.”                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ D. QUESTION RANKING & BUDGET                                                 │
│    Score by calorie impact, macro impact, confidence gap; apply question      │
│    budget (0–2 typical, 3 rare). Merge similar dimensions. Output final list. │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ OUTPUT: clarifying_question (single, existing) + clarification_questions     │
│         (list). No change to API contract; mobile consumes as today.         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Principles:**

- **Deterministic first:** Memory, inference from name/hints/label, impact table, and ranking are deterministic. LLM is not on the critical path for most scans.
- **One pipeline for all meals:** “Oatmeal” and “biryani” go through the same steps; only the sources of candidate dimensions differ (rules, taxonomy, or LLM).
- **Preserve current surface:** Keep existing `clarifying_question` (single, e.g. oil/dressing) and `clarification_questions` (list). The engine only decides *what* to add to the list and in what order.
- **Fast path:** Ambiguity detection can use rules + taxonomy only (no LLM); memory + inference + ranking are cheap. So “most scans” can complete without any LLM call.

---

## 3. Ingredient ambiguity detection model

The system infers **likely hidden ingredients / add-ons / preparation choices** from several signals. The output is always a list of **dimensions** (e.g. `added_fat`, `dairy_type`, `sweetener`, `protein_type`, `starch_portion`) with options and impact—not meal-specific questions.

### 3.1 Dimension registry (meal-agnostic)

A single registry defines the universe of dimensions the engine can ask about:

| dimension_id    | Description              | Example options                    | Default impact (kcal) |
|-----------------|--------------------------|------------------------------------|------------------------|
| added_fat       | Oil, butter, dressing    | None, Light, Normal, Heavy         | High (50–200+)         |
| dairy_type      | Milk/cream type          | None, Whole, Skim, Almond, Oat, Soy| Medium (20–80)        |
| sweetener       | Sugar, syrup, honey      | None, Sugar, Honey, Syrup, Other   | Medium (20–100)       |
| spread          | Mayo, butter on bread    | None, Butter, Mayo, Both           | Medium (50–150)       |
| protein_type    | Protein in mixed dish    | Chicken, Beef, Lamb, Tofu, None    | High (varies)         |
| starch_portion   | Rice/bread/noodles size   | Small, Medium, Large               | High (100–300)         |
| sauce_richness  | Creamy vs light           | Light, Normal, Rich                | Medium–high            |
| toppings        | Nuts, cheese, extras     | None, Light, Heavy                 | Medium                 |
| cooking_method  | Fried vs grilled, etc.   | Grilled, Fried, Baked, etc.       | High for fried         |
| portion_size    | Overall portion          | Small, Medium, Large                | High                   |

Rules and taxonomy **map to these dimension_ids**; they do not define new question types ad hoc.

### 3.2 How we infer ambiguity from each signal

**Food label (when present)**  
- If the scan includes packaged-food recognition or barcode, label may give exact ingredients.  
- **Use:** Where label clearly states “no added sugar”, “oat milk”, “light dressing”, set the corresponding dimension to *resolved* (inferred) so we don’t ask.  
- **Ambiguity:** For dimensions not on the label (e.g. portion eaten, extra toppings added at home), keep them as candidates.

**Detected item names**  
- Item names (e.g. “chicken curry”, “oat milk latte”, “caesar salad”) often contain clues.  
- **Use:** Name-hint rules (e.g. “oat milk” → `dairy_type: Oat`; “no dressing” → `added_fat: None`) resolve dimensions when the name clearly implies a value.  
- **Inference:** Same as today’s `_infer_ingredient_choices_from_name`: phrase/substring or regex match to option value. If inferred, dimension is not asked.  
- **Ambiguity:** If the name suggests a category (e.g. “curry”, “smoothie”, “wrap”) but does not specify a dimension (e.g. milk type, protein type), that dimension stays as a candidate (from taxonomy or rules).

**Image interpretation (vision)**  
- Vision returns `ingredient_hints` (e.g. milk_type, dressing), `cooking_method`, and sometimes a single `clarifying_question`.  
- **Use:** If `ingredient_hints` contains a confident value for a dimension, treat it as *resolved* and do not ask.  
- **Use:** If `cooking_method` is in a list that typically requires oil (e.g. fried), add or keep `added_fat` as a candidate (existing “always_ask_oil” behavior).  
- **Ambiguity:** If the item looks like a “bowl” or “curry” but vision does not specify protein or sauce richness, taxonomy can still suggest those dimensions as candidates; vision didn’t resolve them.

**Meal category (taxonomy)**  
- A small, coarse **meal category** (e.g. beverage, grain_bowl, sandwich, salad, soup, curry, breakfast_base, pasta_noodles) can be inferred from:  
  - Keywords in item names, or  
  - A tiny classifier, or  
  - An optional vision field.  
- **Use:** Each category maps to a **likely set of dimensions** (e.g. beverage → dairy_type, sweetener; grain_bowl → protein_type, starch_portion, sauce_richness). We don’t hardcode “oatmeal” or “biryani”; we hardcode “breakfast_base” → [dairy_type, sweetener, …], “grain_bowl” → [protein_type, starch_portion, sauce_richness].  
- **Ambiguity:** For items in that category, those dimensions are candidates unless already resolved by name, label, or vision.

**Past user behavior (memory)**  
- Memory (user-level defaults, food-token memory, venue memory) is **not** used to *detect* ambiguity; it is used to *resolve* it.  
- **Use:** After we have a list of candidate dimensions, we look up stored choices. If the user has a stored value for (user, food_token, dimension_id) or (user, venue, dimension_id), we treat that dimension as resolved and do not ask.  
- So: **ambiguity detection** = “what could vary?”; **memory** = “what do we already know for this user?” Resolution can also come from inference (name, label, vision).

### 3.3 Output of ambiguity detection

For each (item_id, dimension_id) we produce:

- `ambiguous`: whether we still need to ask (not resolved by memory or inference).  
- `plausible_options`: list of options (from registry or LLM).  
- `inferred_value`: if we inferred from name/label/vision, no need to ask.  
- `estimated_impact_kcal` (and optionally macro impact): for ranking.  
- `source`: rule | taxonomy | llm (for observability).

Rules, taxonomy, and optional LLM all **produce** this same structure; the rest of the engine is dimension-agnostic.

---

## 4. Question ranking strategy

We only ask questions that are **worth it**: high impact, unresolved, and within a strict question budget.

**Calorie impact**  
- Each dimension has an estimated kcal range (from registry or heuristic).  
- Use a single number for ranking, e.g. midpoint or “high/medium/low” mapped to a score (e.g. high=150, medium=60, low=25).  
- Prefer dimensions that can swing total meal kcal the most (e.g. added_fat, starch_portion, portion_size).

**Macro impact**  
- For users with a protein (or other macro) goal, optionally weight dimensions that affect that macro more (e.g. protein_type, dairy_type for protein).  
- Can be a multiplier on the base score (e.g. 1.0 default, 1.2 for “protein-relevant” when user is in “high protein” mode).  
- Keeps the same pipeline; only the scoring weights change.

**Confidence gap**  
- Prefer asking when we are **uncertain**. If vision_confidence is low for that item, or we have no hint for that dimension, (1 − confidence) is high.  
- **Score component:** `impact_score × (1 − confidence_resolved)`. So high impact + low confidence = ask; high impact + already inferred = don’t ask.

**User annoyance / question budget**  
- **Budget:** Most scans 0–2 questions; rarely 3, only when total nutrition swing is large (e.g. >200 kcal potential delta).  
- **Cap:** Sort candidates by combined score (calorie + optional macro weight) × (1 − confidence); take top 2. If the top dimension has very high impact (e.g. >150 kcal), allow a 3rd question; otherwise cap at 2.  
- **Merge:** If two dimensions are redundant for the same item (e.g. “dressing” and “added_fat”), merge into one question with combined options so we don’t burn two slots on the same thing.  
- **Result:** 0 questions when everything is resolved or impact is low; 1–2 in typical cases; 3 only in high-swing cases.

**Formula (summary)**  
- `score(d) = impact_kcal(d) × macro_weight(d) × (1 − confidence_resolved(d))`  
- Sort descending; apply merge; then take top 2 (or 3 if top is very high impact).  
- No meal-specific logic in the ranker—only dimension_id and numeric impact/confidence.

---

## 5. Memory design

Memory ensures we **ask less over time** by reusing the user’s (and optionally venue’s) past choices.

**User-level defaults**  
- **Concept:** “For this user, when we have no food-token or venue memory, assume X for dimension D.”  
- **Example:** User sets “I usually take oat milk in coffee.” That can be stored as (user_id, dimension_id=dairy_type, default=Oat) for a scope like “beverage” or “coffee.”  
- **Use:** When we have a candidate dimension and no food-token or venue memory, we can pre-fill (or auto-apply) the user default and optionally skip asking.  
- **Implementation:** Optional table or key path: `user_defaults[user_id][dimension_id]` or `user_defaults[user_id][meal_category][dimension_id]`.  
- **Confirmation vs auto-apply:** See below.

**Food-token memory**  
- **Concept:** (user_id, food_token) → { dimension_id: value }.  
- **Token:** Normalized primary item name (e.g. “oatmeal”, “latte”) or meal-type/taxonomy label (e.g. “grain_breakfast”, “beverage”) so “steel-cut oatmeal” and “oatmeal” can share memory.  
- **Use:** On scan, we look up stored choices for the resolved food_token(s). Any dimension that has a value is treated as resolved and not asked again (unless user or product chooses “confirm each time” for that dimension).  
- **Persistence:** Existing `user_ingredient_choices` or equivalent; key = (user_id, food_token), value = { dimension_id: option }.

**Venue-specific memory**  
- **Concept:** (user_id, venue_id) → { dimension_id: value }.  
- **Use:** “At this café I always get oat milk” or “At this chain I usually get the smaller size.” When venue_id is available (e.g. from context or future features), lookup can resolve dimensions for that venue.  
- **Priority:** When both food-token and venue memory exist, product can define precedence (e.g. venue overrides food-token for “size” when at a chain).  
- **Implementation:** Optional store: `venue_choices[user_id][venue_id]` or same store with composite key.

**Confirmation vs auto-apply**  
- **Auto-apply:** Use stored (or user-default) value silently to set the dimension and do not show a question. Fastest UX; user sees fewer prompts.  
- **Confirmation:** Pre-fill the question with the stored value but still show “Milk? [Oat ▼]” so the user can change or confirm. Adds one tap but increases trust and allows corrections.  
- **Recommendation:** Default to **auto-apply** for food-token and user defaults; optionally “confirm once per session” or “confirm for high-impact dimensions” (e.g. added_fat) to avoid large errors from stale memory.  
- **Product knob:** Per dimension or global: “always_ask” | “auto_apply” | “confirm_then_apply”.

---

## 6. Rules + LLM fallback design

**Rules (deterministic, fast)**  
- **Role:** For **known** patterns (e.g. names that match a regex or keyword set), rules output **which dimensions apply** and their options + name_hints for inference.  
- **Form:** Pattern (e.g. regex or keyword list) → list of (dimension_id, options, name_hints). Existing `_CLARIFICATION_RULES` can be refactored to **emit** dimension_ids and options instead of ad-hoc keys.  
- **When:** Run first, on every item; no network, no latency.  
- **Output:** Merged into the same candidate-dimension list as taxonomy and LLM.

**Taxonomy (deterministic, fast)**  
- **Role:** For items that match **no** rule, taxonomy maps meal_category → likely dimensions. So “unseen” dish names that map to “grain_bowl” still get candidates like protein_type, starch_portion, sauce_richness.  
- **When:** After rules; no LLM.  
- **Output:** Same candidate list.

**LLM (optional fallback)**  
- **Role:** When an item matches **no** rule and **no** taxonomy (or taxonomy is low-confidence), one **optional** LLM call suggests 1–2 dimension_ids (and optionally options) for that item.  
- **When:** Only if feature flag (e.g. CLARIFICATION_LLM_ENABLED) and no rule/taxonomy hit; strict timeout (e.g. 2–3 s).  
- **Input:** Item names (and optionally meal_category if we have it).  
- **Output:** List of (dimension_id, options) merged into the same candidate list.  
- **Failure:** On timeout or error, return no extra questions; do not block the scan. Deterministic path (rules + taxonomy + memory + inference + ranking) still runs.

**How they work together**  
- Pipeline always runs: rules → taxonomy → [optional LLM for unmatched items].  
- All outputs are **candidate dimensions** in the same format. Then: memory lookup → inference → ranking → final 0–2 (or 3) questions.  
- No separate “rule path” vs “LLM path” in the rest of the engine; one pipeline, multiple sources.

---

## 7. Low-confidence / no-question behavior

**Vision confidence low**  
- Existing behavior stays: we can show a single `clarifying_question` (e.g. oil/dressing) when vision_confidence &lt; threshold or cooking_method in “always_ask_oil”.  
- The engine can also add `added_fat` (or equivalent) to `clarification_questions` if not already covered by that single question.  
- We do **not** invent extra unrelated questions just because confidence is low.

**Engine can’t propose dimensions**  
- If after rules + taxonomy (+ optional LLM) we have **no** candidate dimensions for an item, we ask **nothing** extra for that item.  
- **Fail closed:** Better to ask zero than to ask a generic or irrelevant question.  
- Existing `clarifying_question` (from vision) can still be shown.

**LLM timeout or error**  
- No extra questions from the engine for that scan. Rules and taxonomy output only.  
- Scan result still returned; user can correct manually if needed.

**No good question exists**  
- If the only candidates have very low impact (e.g. &lt;20 kcal) or are all resolved by memory/inference, the ranked list is empty.  
- **Behavior:** Return 0 clarification_questions. Do not ask “just one” for the sake of it; only ask when it materially improves accuracy (by impact and confidence gap).

**Stale or missing memory**  
- If memory lookup fails or returns nothing, treat all dimensions as unresolved and rank as usual. No special fallback; we may ask 1–2 questions we could have skipped with memory.

---

## 8. Mobile UX flow

**Fast first result**  
- Backend returns scan result (items, totals, confidence) and **at most** one `clarifying_question` + a list `clarification_questions` (0–3 items).  
- Mobile shows the result **immediately**: hero, macros, goal-fit line, items. No need to wait for clarification to show “first pass” nutrition.  
- Clarification is **progressive**: show the result first, then show “Improve accuracy” (or similar) with 0–2 (rarely 3) questions below the fold or in a compact block.

**Then clarify if needed**  
- If `clarification_questions.length > 0`, show them in one place (e.g. “Confirm details” / “Improve accuracy”) with chips or dropdowns.  
- Single “Apply” (or “Apply and update kcal”) that sends all answers in one request.  
- Optional: show one question at a time only if product wants to minimize cognitive load; backend can still receive all answers in one payload.

**Then recompute**  
- On “Apply”, mobile sends selected options (key → value) to backend.  
- Backend applies choices to items (e.g. adjust milk type, dressing, portion), reruns nutrition lookup or adjustment, and returns updated totals and items.  
- Mobile replaces the first-pass result with the updated result (same UI, updated numbers).

**Then remember**  
- Backend (or client) persists (user_id, food_token, dimension_id → value) and optionally (user_id, venue_id, dimension_id → value).  
- Next time the user scans the same (or similar) food, memory lookup resolves those dimensions and we ask 0 or fewer questions.  
- No extra UX step for “remember”; it happens as part of apply. Optionally show a brief “We’ll remember this for next time” for trust.

**Summary flow**  
1. Scan → **fast first result** (show immediately).  
2. If clarification_questions → show **clarify** block; user answers; **Apply**.  
3. Backend **recompute**; return updated result; mobile updates UI.  
4. Backend **remember** (food-token + optional venue); next scan asks less.

---

## 9. Data model / storage suggestions

**Clarification choices (existing or extended)**  
- **Key:** `(user_id, food_token)` or `(user_id, food_token, venue_id)` (if venue scope added).  
- **Value:** `{ dimension_id: selected_option }`, e.g. `{ "dairy_type": "Oat", "sweetener": "None" }`.  
- **Storage:** File-based (e.g. `user_ingredient_choices.json`) or DB table `user_clarification_choices (user_id, food_token, venue_id?, dimension_id, value, updated_at)`.  
- **Token normalization:** Same as today (normalized name, length cap); optionally add `meal_category` or taxonomy label as an alternate token for sharing across similar dishes.

**User-level defaults (optional)**  
- **Key:** `user_id`, optionally scoped by `meal_category` or dimension_id.  
- **Value:** `{ dimension_id: default_option }`, e.g. `{ "dairy_type": "Oat" }` for beverages.  
- **Storage:** Same store as above with a reserved token like `"__defaults__"` or a separate table `user_clarification_defaults`.

**Venue-specific (optional)**  
- **Key:** `(user_id, venue_id)`.  
- **Value:** `{ dimension_id: option }`.  
- **Storage:** Table or key path `venue_choices[user_id][venue_id]`.

**Dimension registry**  
- **Content:** dimension_id, label, options[], default_impact_kcal (or high/medium/low), optional macro_weights, optional “confirm vs auto_apply”.  
- **Storage:** Config (JSON/YAML) or code; no per-user storage.

**Observability**  
- Log: scan_id, items, candidate dimensions (with source: rule | taxonomy | llm), resolved by (memory | inference), asked dimensions, and final question count.  
- Enables tuning impact scores and adding rules without hardcoding meal names.

---

## 10. Recommended implementation order (MVP → smarter)

**Phase 1 — MVP (deterministic, no new UX)**  
1. **Dimension registry:** Single source of dimension_id, options, default impact (kcal band). Refactor existing rules to emit (dimension_id, options, name_hints) instead of ad-hoc keys.  
2. **Unify pipeline:** For each item, run rules → produce candidate dimensions; apply vision `ingredient_hints` and existing `clarifying_question` (e.g. map to added_fat). Output one list of (item_id, dimension_id, options, impact, inferred?).  
3. **Memory + inference:** Look up (user_id, food_token); infer from name_hints where possible; drop resolved dimensions.  
4. **Ranking + cap:** Score by impact × (1 − confidence); cap at 2 (or 3 if top impact very high); output `clarification_questions` in current API shape.  
5. **Persistence:** On apply, save (user_id, food_token, dimension_id → value) in existing or extended store.

**Phase 2 — Taxonomy (unseen meals without LLM)**  
6. **Meal category:** Add coarse taxonomy (e.g. beverage, grain_bowl, sandwich, salad, soup, curry, breakfast_base, pasta_noodles). Infer from item name keywords or a small classifier.  
7. **Category → dimensions:** Map each category to 1–3 likely dimensions. For items with no rule match, attach these as candidates.  
8. **Merge and dedupe:** When both rule and taxonomy suggest the same dimension for the same item, keep one; when similar (e.g. dressing + added_fat), merge into one question.

**Phase 3 — Smarter and calmer**  
9. **Macro-aware ranking:** Optional weight by user goal (e.g. protein) so protein_type or dairy_type ranks higher when relevant.  
10. **User defaults:** Allow user to set “usual” choices per dimension (or per category); use when no food-token/venue memory.  
11. **Confirmation vs auto-apply:** Product knob: for high-impact dimensions, optionally “confirm then apply” instead of pure auto-apply from memory.  
12. **LLM fallback:** For items with no rule and no taxonomy hit, optional single LLM call (strict timeout) to suggest 1–2 dimension_ids; merge into candidates and run same ranking.  
13. **Venue memory (if product needs it):** Store and lookup (user_id, venue_id) for dimension choices; precedence rule when both food-token and venue have values.  
14. **Observability:** Log candidates, resolved, asked; use to tune impact and add rules for high-value meals without hardcoding every example.

This order keeps the current app and API intact, makes the engine universal and dimension-based, and adds taxonomy and LLM as optional layers so that **any current or future meal type** can get 0–2 (rarely 3) high-impact questions without a meal-specific rule list.

# General Clarification-Question Engine — Design

**Goal:** When a user scans any meal, the system should automatically detect meal pattern, infer which variables could materially change calories/macros, ask a minimal number of high-impact follow-up questions, remember answers for next time, and work even when there is no hardcoded rule for that food.

Examples (oatmeal, salad, coffee, curry, sandwich, smoothie, rice bowl, pasta) are **illustrations only**. This document describes a **general engine** that generalizes to unseen meals.

---

## 1. Why example-based logic is not enough

### Current approach (pattern + rules)

- **Pattern–question rules:** Regex on item name (e.g. `^(oatmeal|porridge|oats)\b`) maps to a fixed list of questions (milk, sweetener, egg, yogurt). Each rule is hand-maintained.
- **Limitations:**
  - **Coverage:** Every new dish (biryani, pho, poke, dosa, shakshuka) requires a new rule. The long tail of meals is never fully covered.
  - **Brittleness:** Slight name variation (“savory oats”, “steel-cut oatmeal”) can miss the rule or match the wrong one.
  - **No notion of impact:** All questions in a rule are treated equally; we don’t rank by how much they change kcal/macros.
  - **Composition ignored:** A “bowl” might be grain + protein + sauce; rule-by-item doesn’t model meal-level ambiguity (e.g. “which protein?” vs “how much rice?”).
  - **Duplicate effort:** Vision already returns `ingredient_hints` and a single `clarifying_question`; rule logic partly duplicates and partly conflicts with that.

### What we need instead

- **Meal-agnostic dimensions:** Model “what could vary” as generic dimensions (added fat, dairy type, sweetener, protein type, portion of starch, etc.) that can apply to many foods, not only to a fixed list of dish names.
- **Impact-driven choice:** Ask only questions that have high expected calorie/macro impact and that we cannot infer or remember.
- **Unseen meals:** When no rule matches, the system should still propose a small set of plausible, high-impact questions (e.g. via a fast LLM or a small set of generic templates), not silently ask nothing or fall back to a single generic prompt.

---

## 2. General clarification engine design

### High-level flow

```
Scan result (items + vision_confidence + ingredient_hints + optional meal_context)
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 1. AMBIGUITY DETECTION                                                 │
│    For each item (and optionally meal-level): infer which dimensions  │
│    are ambiguous and what range of values is plausible.                │
│    Input: item name, grams, cooking_method, ingredient_hints, vision   │
│    Output: list of (dimension_id, item_id, confidence_ambiguous,     │
│            plausible_options, estimated_impact_kcal_range)            │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 2. MEMORY LOOKUP                                                       │
│    For (user_id, food_token or meal_token): which dimensions already  │
│    have a stored choice? Remove those from “need to ask”.              │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 3. INFERENCE FROM NAME / HINTS                                         │
│    For each remaining dimension: can we infer value from item name     │
│    or vision ingredient_hints? If yes, apply and remove from “ask”.    │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 4. QUESTION RANKING                                                    │
│    Rank remaining dimensions by impact × (1 − confidence_already).     │
│    Cap at 2–3 questions; optionally merge similar dimensions.        │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 5. OUTPUT                                                              │
│    clarifying_question (single, from vision or oil/dressing logic)     │
│    + clarification_questions (list, from engine)                      │
│    Both consumed by existing UI; no change to contract.               │
└───────────────────────────────────────────────────────────────────────┘
```

### Principles

- **Deterministic first:** Where possible (memory, name/hint inference, impact tables), use deterministic logic so behavior is reproducible and fast.
- **LLM optional:** LLM is used only when we need to propose or score dimensions for **unseen** meals or to merge/rewrite questions; it is not required for every scan.
- **Preserve current surface:** Keep `clarifying_question` (single) and `clarification_questions` (list) and their semantics; the engine only decides **what** to ask, not how the client displays it.
- **One pipeline:** The same pipeline runs for “oatmeal” and “biryani”; rule-based logic becomes one way to **populate** ambiguity dimensions, not the only path.

---

## 3. Ingredient ambiguity detection model

### Dimension-centric model

Instead of “if oatmeal then ask milk, sweetener, egg”, we define **dimensions** that can apply across many items:

| Dimension ID       | Description (for logic)   | Example options (configurable)        | Typical impact (kcal) |
|--------------------|---------------------------|--------------------------------------|------------------------|
| `added_fat`        | Oil, butter, dressing     | None, Light, Normal, Heavy            | High (50–200+)        |
| `dairy_type`       | Milk / cream type         | None, Whole, Skim, Almond, Oat, Soy | Medium (20–80)        |
| `sweetener`        | Sugar, syrup, honey       | None, Sugar, Honey, Syrup, Other     | Medium (20–100)       |
| `spread`           | Mayo, butter on sandwich  | None, Butter, Mayo, Both             | Medium (50–150)        |
| `protein_type`     | In mixed dish             | Chicken, Beef, Lamb, Tofu, None      | High (varies)          |
| `starch_portion`   | Rice, bread, noodles size | Small, Medium, Large                  | High (100–300)        |
| `sauce_richness`   | Creamy vs light sauce     | Light, Normal, Rich                  | Medium–high            |
| `toppings`         | Nuts, cheese, etc.        | None, Light, Heavy                   | Medium                 |
| …                  |                           |                                      |                        |

- **Dimension registry:** A single config (or code) defines `dimension_id`, default `options`, and a **default impact score** (e.g. kcal range or “high/medium/low”). This is not meal-specific; it’s a shared vocabulary.
- **Per-item ambiguity:** For each detected item we don’t “match a rule”; we **propose candidate dimensions** that could apply and whether each is ambiguous.

### How to get “which dimensions apply” without hardcoding every meal

- **Rule layer (deterministic):** Existing pattern-based rules can be **mapped into** dimensions. Example: oatmeal rule → dimensions `dairy_type`, `sweetener`, `egg_added`, `yogurt_type`. So current rules become one source of (item_pattern → list of dimension_ids + options).
- **Vision / structure:** Vision already returns `ingredient_hints` (e.g. milk_type, dressing). If a hint is present and confident, that dimension is **resolved**; if the item suggests a category (e.g. “curry”, “bowl”) but no hint, we can mark dimensions like `sauce_richness` or `starch_portion` as **ambiguous**.
- **Generic item taxonomy (optional):** A small, coarse taxonomy (e.g. “beverage”, “grain_bowl”, “sandwich”, “salad”, “soup”, “curry”, “breakfast_base”) can be:
  - Inferred from name keywords or a tiny classifier, or
  - Returned by vision as an extra field.
  Taxonomy then maps to **likely dimensions** (e.g. beverage → dairy_type, sweetener; grain_bowl → protein_type, starch_portion, sauce_richness). No need to enumerate every dish.
- **LLM fallback for unseen:** For items that match no rule and have no taxonomy hit, a **single** fast LLM call (e.g. “Given item names [X], which of these dimensions are ambiguous: [list dimension_ids]? Return only dimension_ids and optional options.”) can propose 1–3 dimensions. This stays optional and behind a flag/timeout.

### Output of ambiguity detection

For each (item_id, dimension_id) we want:

- `ambiguous: bool` — we don’t know the value (or we’re not confident).
- `plausible_options: list[str]` — from dimension registry or LLM.
- `inferred_value: str | None` — if we inferred from name/hints, no need to ask.
- `estimated_impact_kcal: float` — used later for ranking (can be from registry or heuristic).

So the “ingredient ambiguity detection” is: **produce a list of (item_id, dimension_id, options, impact, inferred_or_none)**. Rules, vision hints, taxonomy, and optional LLM all feed this list; the rest of the engine is dimension-agnostic.

---

## 4. Question ranking strategy

- **Already resolved:** Dimensions with a stored choice (memory) or inferred value (name/hints) are not asked.
- **Impact score:** Use `estimated_impact_kcal` (or high/medium/low mapped to numbers). Optionally weight by macro (e.g. protein-heavy dimension for users focused on protein).
- **Uncertainty:** Prefer dimensions where we’re **uncertain** (e.g. vision_confidence low for that item, or no hint). So: `score = impact × (1 − confidence_resolved)`.
- **Cap and merge:** Sort by score descending; take top 2–3. If two dimensions are very similar (e.g. “dressing” and “added_fat” for same item), merge into one question with combined options.
- **Global cap:** Hard cap at 3 questions (configurable). If the engine produces more candidates, only the top 3 are returned. This keeps UX minimal and “avoid annoying the user” as required.

---

## 5. Memory design

- **Keep current store:** `(user_id, food_token) → { dimension_key: value }` (e.g. `user_ingredient_choices`) remains. No need to change the storage format initially.
- **Stable token:** `food_token` today is normalized item name. For a general engine we can:
  - Keep **item-name-based token** for “this exact item” (e.g. “oatmeal”), and/or
  - Add an optional **meal-type token** (e.g. “oatmeal” or “grain_breakfast”) so that “steel-cut oatmeal” and “oatmeal” share the same memory. Token can be: primary item name normalized, or taxonomy label if we have it.
- **What we store:** When the user answers a clarification question, we store `(user_id, food_token, dimension_id → selected_option)`. Next time we run ambiguity detection + memory lookup; if `dimension_id` is in stored choices we don’t add it to “need to ask”.
- **Scope:** Memory is per (user, token). We do not need global “most people choose X” for this design; that could be a later enhancement (e.g. default option when no memory).

So: **memory design = keep existing store, optionally generalize token to meal-type/taxonomy so that similar dishes share memory; apply memory after ambiguity detection and before ranking.**

---

## 6. Rules vs LLM fallback

| Concern            | Rules (deterministic)                          | LLM (optional)                                      |
|--------------------|-------------------------------------------------|------------------------------------------------------|
| **Role**           | Define which dimensions apply for **known** patterns; provide options and name_hints for inference. | Propose dimensions (and optionally options) for **unseen** items. |
| **When**           | First; run for every item (pattern match).     | Only when no rule matches and CLARIFICATION_LLM_ENABLED. |
| **Speed**          | Fast (regex + table lookup).                    | One short call, strict timeout (e.g. 2–3 s).         |
| **Determinism**    | Fully deterministic.                            | Non-deterministic; use only to suggest candidates.  |
| **Output**         | List of (dimension_id, options, name_hints).    | List of (dimension_id, options) for 1–2 dimensions.  |

- **Merge:** Rule output and LLM output are merged into the same “candidate dimensions” list. Then memory + inference + ranking run on that list; no special case for “from LLM” in the rest of the pipeline.
- **No rule for this food:** If an item matches no rule, we either:
  - Ask nothing (current behavior when LLM off), or
  - Use taxonomy to attach generic dimensions, or
  - Use one fast LLM call to suggest 1–2 dimensions. So “no rule” does not mean “no clarification” when we want to support unseen meals.

---

## 7. Graceful failure when confidence is low

- **Vision confidence low:** We already have a single `clarifying_question` (e.g. oil/dressing) when confidence &lt; threshold or method in `always_ask_oil_for_methods`. That stays as-is. The **engine** can additionally mark “added_fat” as ambiguous for that item and include it in clarification_questions if not already covered.
- **Engine can’t propose dimensions:** If ambiguity detection returns nothing (no rule, no taxonomy, LLM off or failed), we return **no extra** clarification_questions. We don’t invent generic questions that might be irrelevant. So: fail closed (ask nothing extra) rather than annoying.
- **LLM timeout/error:** Same: no extra questions; existing vision `clarifying_question` and oil logic unchanged.
- **Stale or missing memory:** If memory lookup fails, we simply treat all dimensions as “not resolved” and rank them as usual. No special fallback.

---

## 8. Recommended implementation order

1. **Dimension registry and impact table**  
   Add a single source of truth: dimension_id, default options, default impact (e.g. kcal or high/medium/low). Refactor existing `_CLARIFICATION_RULES` to **emit** (dimension_id, options, name_hints) from patterns instead of ad-hoc keys. No new questions yet; just internal representation.

2. **Unify vision + rules into “candidate dimensions”**  
   For each item: (a) run existing pattern rules → dimensions; (b) apply vision `ingredient_hints` (resolved) and vision `clarifying_question` (e.g. map to `added_fat`). Output: list of (item_id, dimension_id, options, inferred_or_none, impact). Keep existing `clarifying_question` generation as-is; engine only produces `clarification_questions`.

3. **Memory and inference in the pipeline**  
   After candidates: (a) memory lookup by (user_id, food_token); (b) infer from name using existing name_hints; (c) drop resolved dimensions. This is already partly there; ensure it runs on the new dimension list and that stored keys are dimension_ids.

4. **Ranking and cap**  
   Rank remaining dimensions by impact × (1 − confidence); cap at 2–3; optionally merge “same dimension” for same item. Output `clarification_questions` in current format (key, label, options).

5. **Taxonomy (optional)**  
   Add a small, coarse meal-type taxonomy (keyword or tiny model). Map taxonomy → default dimensions for “unseen” items so we can ask 1–2 questions without LLM.

6. **LLM fallback for unseen**  
   When an item has no rule and no taxonomy dimensions: one optional LLM call to suggest 1–2 dimension_ids (and optionally options). Strict timeout; on failure, ask nothing extra.

7. **Observability and tuning**  
   Log which dimensions were proposed, which were resolved by memory/inference, and which were asked. Use this to add rules or adjust impact for high-value meals without hardcoding every example.

This order keeps the current architecture (vision, oil logic, memory, API contract) intact, makes rules a subset of a general pipeline, and adds generalization (dimensions, ranking, optional taxonomy + LLM) without requiring an LLM on every request.

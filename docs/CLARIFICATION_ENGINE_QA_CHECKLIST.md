# Manual QA Checklist — Universal Clarification Engine MVP

**Purpose:** Verify that the clarification engine feels smart, relevant, fast, and non-annoying in realistic product use. Focus on real behavior in the app, not unit tests.

**Scope:** Dimension-based engine with alias mapping, memory, name/hint inference, impact ranking, and 0–2 question cap. No LLM fallback or taxonomy in scope.

---

## 1. QA goals

- **Relevance:** Questions asked are about things that materially affect calories/macros (dairy, fat, sweetener, spread, cooking method, etc.), not noise.
- **Minimal friction:** Most scans ask 0 or 1 question; 2 only when impact justifies it. No low-value questions (impact &lt; 35 for first, &lt; 45 for second).
- **Memory works:** Repeat scans for the same (or similar) food show fewer or zero questions when the user has already answered.
- **Alias safety:** Old stored keys (e.g. `milk_type`, `dressing`) still resolve; vision or rules using old keys don’t break; output uses canonical dimension keys.
- **Inference works:** When the item name or `ingredient_hints` clearly indicate an answer (e.g. “oat milk latte”), we don’t ask that dimension.
- **Product feel:** Flow feels fast, questions feel useful, and the experience is not annoying.

---

## 2. Core manual test categories

| Category | Focus |
|----------|--------|
| **A. Zero questions** | Unambiguous foods, or everything resolved by name/hints/memory. |
| **B. One question** | One high-impact dimension unresolved; others inferred or stored. |
| **C. Two questions max** | Two high-impact dimensions unresolved; no third question. |
| **D. Memory / repeat scans** | Same user, same (or similar) food again; fewer questions. |
| **E. Alias compatibility** | Stored or vision using old keys; behavior correct, no duplicate or wrong questions. |
| **F. Low-value suppression** | Weak-impact candidates don’t surface; empty list when nothing passes threshold. |
| **G. Product feel** | Speed, relevance, wording, and overall “does this feel good?” |

---

## 3. Detailed manual test cases

### 3.1 Foods that should ask **no** clarification questions

| # | Test meal | Why it matters | Expected count | Example dimensions | Failure if |
|---|-----------|----------------|----------------|--------------------|------------|
| 1 | **Black coffee** (name like “black coffee” or “espresso no milk”) | Name implies no dairy, no sweetener. | 0 | — | Any question asked. |
| 2 | **Oat milk latte** (name contains “oat milk”) | Name implies dairy_type = Oat. | 0 | — | dairy_type or sweetener asked. |
| 3 | **Plain Greek yogurt** (name like “Greek yogurt plain”) | Name implies dairy type; no toppings specified but low ambiguity if name is clear. | 0 or 1 | If 1: toppings only if high impact | dairy_type asked when name says “Greek.” |
| 4 | **Salad with “no dressing” in name** | Name implies added_fat = None. | 0 | — | added_fat / dressing asked. |
| 5 | **Scrambled eggs** (name clear, no oil question from vision) | cooking_method can be inferred; egg_count may be in name. | 0 or 1 | If 1: egg_count or cooking_method only if impactful | 2 questions or irrelevant dimension. |
| 6 | **Simple single item** (e.g. “banana”, “apple”) | No rule match → no candidates. | 0 | — | Any clarification question. |
| 7 | **Sandwich described as “dry” or “no mayo”** | Name implies sauce_or_spread = None. | 0 | — | sauce_or_spread / spread asked. |

### 3.2 Foods that should ask **1** useful question

| # | Test meal | Why it matters | Expected count | Example dimensions | Failure if |
|---|-----------|----------------|----------------|--------------------|------------|
| 8 | **Latte** (name just “latte”, no milk/sugar in name) | Dairy and possibly sweetener ambiguous. | 1 | dairy_type (impact ≥ 35) | 0 questions when we should ask milk; or 2 questions when one is low impact. |
| 9 | **Smoothie** (name “fruit smoothie”, base/sweetener unknown) | One high-impact dimension. | 1 | dairy_type or sweetener | 0 or 2+ questions; or sweetener when name says “unsweetened.” |
| 10 | **Caesar salad** (no dressing in name) | Dressing is high impact. | 1 | added_fat | 0 questions; or 2; or wrong dimension. |
| 11 | **Oatmeal** (name “oatmeal”, no milk/sugar/egg) | One or two dimensions; cap and ranking should leave 1 if only one passes threshold. | 1 | dairy_type or sweetener (one of the top two) | 0 when we should ask; or 2 when only one is high impact; or protein_add_on when irrelevant. |
| 12 | **Yogurt parfait** (type/toppings unclear) | One dimension often enough. | 1 | dairy_type or toppings-related | 0 or 2+; or duplicate “dairy” questions. |
| 13 | **Eggs** (name “eggs” or “fried eggs”) | Cooking or count may be the one we ask. | 1 | cooking_method or egg_count | 0 when method/count unknown; or 2 low-impact questions. |
| 14 | **Wrap or burger** (name only, no spread in name) | Spread is high impact. | 1 | sauce_or_spread | 0; or 2; or non-spread dimension when spread is the gap. |

### 3.3 Foods that should ask **2** useful questions (max)

| # | Test meal | Why it matters | Expected count | Example dimensions | Failure if |
|---|-----------|----------------|----------------|--------------------|------------|
| 15 | **Oatmeal** with milk/sweetener/egg all ambiguous | Multiple high-impact dimensions. | 2 | e.g. dairy_type + sweetener, or dairy_type + protein_add_on | 0 or 1 when two are clearly ambiguous; or 3+ questions. |
| 16 | **Coffee drink** (e.g. “coffee” or “mocha”) with milk and sweetener unknown | Two dimensions with sufficient impact. | 2 | dairy_type + sweetener | 0 or 1; or 3; or dimensions not about milk/sugar. |
| 17 | **Smoothie** with base and sweetener both unknown | Two impactful dimensions. | 2 | dairy_type + sweetener | 0 or 1; or more than 2. |
| 18 | **Yogurt bowl** with type and toppings unknown | Two dimensions. | 2 | dairy_type + toppings (if both high impact) | 0 or 1 when both unclear; or 3+. |
| 19 | **Salad** with dressing and protein add-on unclear | added_fat + protein_add_on. | 2 | added_fat + protein_add_on | 0 or 1; or 3; or irrelevant dimensions. |
| 20 | **Sandwich** with spread and portion/size unclear | sauce_or_spread + one other if high impact. | 2 | sauce_or_spread + portion_size or similar | 0 or 1; or 3+; or low-impact second question. |

**Cap check:** For any meal, never show more than **2** clarification questions. If three or more appear, treat as failure.

---

## 4. Memory / repeat-scan test cases

**Setup:** Use the same test user (or device) and the same or very similar food names so that `food_token` and stored choices apply.

| # | Scenario | Why it matters | Steps | Expected | Failure if |
|---|----------|----------------|-------|----------|------------|
| 21 | **First scan: latte** | Establish baseline. | Scan “latte”; note question count (e.g. 1: dairy_type). Answer e.g. “Oat.” Apply. | 1 question, then updated result. | No question when we should ask; or apply doesn’t complete. |
| 22 | **Second scan: latte (same user)** | Memory should resolve dairy. | Scan “latte” again (same user). | 0 questions (dairy_type resolved by memory). | dairy_type asked again. |
| 23 | **Second scan: cappuccino (same user)** | Same token or similar may share memory. | Scan “cappuccino” after having answered “Oat” for “latte.” | 0 questions if token matches or is shared; or 1 if token differs. | Document behavior for product (same-token vs different beverage). |
| 24 | **First scan: oatmeal** | Establish baseline. | Scan “oatmeal”; answer e.g. dairy_type “Milk” and sweetener “None.” Apply. | 1–2 questions, then result. | — |
| 25 | **Second scan: oatmeal (same user)** | Memory should reduce questions. | Scan “oatmeal” again. | Fewer questions (0 or 1); dairy_type and sweetener not both asked if both stored. | Both asked again after being saved. |
| 26 | **Stored value empty or blank** | We should not treat blank as “resolved.” | (Requires DB/file edit or test harness: set stored choice to `""` for a dimension.) Scan that food. | Question for that dimension still appears. | Question suppressed because of blank stored value. |
| 27 | **Clear / new user** | No memory. | Use a user with no stored choices for the food. | Same as first-scan expectations (0–2 questions by rules/inference). | N/A. |

---

## 5. Alias compatibility test cases

**Context:** Stored choices or vision may still use old keys (`milk_type`, `milk_base`, `yogurt_type`, `dressing`, `spread`, `how_cooked`). The engine should treat them as resolving the corresponding canonical dimension.

| # | Scenario | Why it matters | Steps | Expected | Failure if |
|---|----------|----------------|-------|----------|------------|
| 28 | **Stored key `milk_type` = "Oat"** | Backward compatibility. | Set stored choice `milk_type: "Oat"` for user+token (e.g. “latte”). Scan “latte.” | 0 questions for dairy_type (resolved via alias). | dairy_type question still asked. |
| 29 | **Stored key `dressing` = "Light"** | Backward compatibility. | Set stored `dressing: "Light"` for user+token (e.g. “salad”). Scan “salad.” | 0 questions for added_fat. | added_fat question still asked. |
| 30 | **Stored key `spread` = "Mayo"** | Backward compatibility. | Set stored `spread: "Mayo"` for user+token (e.g. “wrap”). Scan “wrap.” | 0 questions for sauce_or_spread. | sauce_or_spread question still asked. |
| 31 | **Vision hint key `milk_type`** | Vision may still send old keys. | (If controllable: item with ingredient_hints `{ "milk_type": "Oat" }`.) | No dairy_type question; result uses Oat. | dairy_type asked despite hint. |
| 32 | **Vision hint key `dressing`** | Same for dressing. | Item with ingredient_hints `{ "dressing": "None" }`. | No added_fat question. | added_fat asked. |
| 33 | **Output uses canonical keys only** | API contract. | For any scan that returns clarification_questions, inspect each `key`. | Every `key` is a canonical dimension ID (e.g. `dairy_type`, `added_fat`, `sauce_or_spread`, `cooking_method`, `egg_count`, etc.). | Any key is an old alias (e.g. `milk_type`, `dressing`) in the response. |

---

## 6. Edge cases: low-value question suppression

| # | Scenario | Why it matters | Steps | Expected | Failure if |
|---|----------|----------------|-------|----------|------------|
| 34 | **Only low-impact candidates** | Questions below threshold should not appear. | Use a meal that would only produce candidates with impact &lt; 35 (may require rule/data that yields low impact). | 0 questions. | Any question with effective impact &lt; 35. |
| 35 | **First candidate &lt; 35, second ≥ 45** | First question has threshold too. | (May need mock or specific item.) | 0 questions (first not asked; second alone is not “first” so cap logic may still allow 0). Per spec: first only if ≥ 35. | First question shown with impact &lt; 35. |
| 36 | **Exactly one candidate at 35** | Threshold boundary. | Meal that yields one dimension with impact 35. | 1 question. | 0 questions. |
| 37 | **Two candidates: 50 and 40** | Second must be ≥ 45. | Meal that yields two dimensions with impact 50 and 40. | 1 question only (second suppressed). | 2 questions. |
| 38 | **Two candidates: 50 and 45** | Both pass. | Meal that yields 50 and 45. | 2 questions. | 0 or 1 or 3+ questions. |

---

## 7. Product feel checks

Run these subjectively while doing the above; note pass/fail and short notes.

| # | Check | Pass criteria | Notes |
|---|--------|----------------|------|
| 39 | **Speed** | Scan result (with or without clarification) appears without noticeable delay from the clarification engine. | No extra 1–2 s wait attributable to clarification. |
| 40 | **Relevance** | Every question feels like “this could change my calories/macros.” | No “why are you asking this?” moments. |
| 41 | **Wording** | Labels are short and clear (e.g. “Milk?”, “Dressing/oil?”, “Spread/butter?”). | No confusing or overly long labels. |
| 42 | **Options** | Options are actionable and cover common cases. | No missing obvious choice (e.g. “Oat” for milk). |
| 43 | **Not annoying** | 0–2 questions feel acceptable; no sense of interrogation. | More than 2 questions or repeated questions after answering. |
| 44 | **Apply flow** | After answering and applying, result updates and reflects choices. | Apply fails or numbers don’t update. |
| 45 | **Remember feel** | On repeat scan, fewer questions give a “it remembered me” feeling. | No reduction when it should have remembered. |
| 46 | **Unambiguous foods** | Simple items (fruit, plain items) don’t ask. | Any question for clearly unambiguous items. |
| 47 | **Coverage** | At least one test each for coffee, smoothie, salad, oatmeal, yogurt, eggs, sandwich/wrap, and one “no rule” simple food. | Any category missing from manual run. |

---

## 8. Exit criteria for MVP clarification quality

**MVP is acceptable only if:**

1. **Cap:** No scan ever shows more than **2** clarification questions.
2. **Thresholds:** No first question with impact &lt; 35; no second with impact &lt; 45 (validated via known scenarios or logging).
3. **Zero when appropriate:** Unambiguous or fully resolved foods (by name, hints, or memory) show **0** questions; no irrelevant questions for simple/unambiguous items.
4. **Memory:** For at least 2 foods (e.g. latte, oatmeal), a repeat scan with stored choices shows **fewer** questions than the first scan.
5. **Alias:** At least one alias case (e.g. stored `milk_type` or `dressing`) correctly suppresses the corresponding canonical dimension question.
6. **Output shape:** Every `clarification_questions` item has exactly `key`, `label`, `options`; every `key` is a canonical dimension ID.
7. **Product feel:** No critical “annoying” or “wrong” in the product feel checks; apply and remember flows work.

**Optional (nice-to-have):**

- At least one test case each for: coffee/tea, smoothie, salad, oatmeal, yogurt, eggs, sandwich/wrap, and one simple food.
- No regression in scan latency attributed to the clarification engine.

---

## Quick reference: canonical dimensions (MVP)

- `added_fat`, `dairy_type`, `sweetener`, `protein_add_on`, `sauce_or_spread`, `portion_size`, `starch_portion`, `cooking_method`, `egg_count`

**Aliases (old → canonical):** milk_type, milk_base, yogurt_type → dairy_type; dressing → added_fat; spread → sauce_or_spread; how_cooked → cooking_method.

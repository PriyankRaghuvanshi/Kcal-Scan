# Coach Voice Improvements

This doc summarizes how the daily coach voice was improved: **human-like data-aware coaching**, **tone**, **balance of levers**, **variety**, and **less repetition**.

---

## 1. Human coach: data-aware, varied language

The coach is framed as a **real human coach** who has seen the user’s meal scans, fat loss stats, and gaps. It should use **different words every time** and reference their actual data in natural language.

- **Daily coach system prompt:** "You are a real human nutrition coach talking to a client. You have seen their meal scans, today's totals, protein/fiber gaps, fat loss stats, and weekly patterns. Talk like a coach who actually looked at their data; reference their numbers and meals in natural language. Use different words and sentence structures every time—never repeat the same phrases. Sound like a person, not a template."
- **Coach voice (meal-level):** Same idea—real human who has seen their meals and stats; natural, varied language; reference scans, gaps, patterns.
- **Daily prompt (full + fast):** Explicit "Voice:" instruction: write like a real human coach who has seen their meal scans and fat loss stats; reference actual numbers and patterns in natural, varied language; don’t sound like a script.
- **Tone rewrite:** For indian_coach, use natural Hinglish (vary phrases), not just 2–3 canned words.

---

## 2. Tone: Distinct coach personas

The coach can sound different based on user choice so it’s clearly “which coach they chose.”

**System prompt** (`main.py`):

```text
Your voice must feel distinctly different by the requested tone (supportive/strict/funny/indian_coach):
use that tone's phrasing, energy, and sentence style so the user can tell which coach they chose.
```

**Tone definitions** (`_DAILY_TONE_PROMPTS`, `_DAILY_TONE_PACK`):

| Tone          | Style |
|---------------|--------|
| **Supportive** | Warm, acknowledge effort, no guilt, practical next step, no shame. Phrases: "Small win", "Let's make it easy", "You're building momentum". |
| **Strict**     | Direct, accountable, short command-style, one concise consequence line. Phrases: "Minimum standard", "Do this today", "Non-negotiable". |
| **Funny**      | Playful, one hook phrase ("Plot twist", "Cheat code", "Boss move"), max 2 emoji, facts unchanged. |
| **Indian coach** | Natural Hinglish like a real Indian coach—mix Hindi/English as people speak (bhai, dost, yaar, chalo, sahi hai, theek hai, dekho, pakka, mast, no tension, ho jayega, etc.). Vary phrases; don’t limit to 2–3 words. Reference their scans and stats in natural Hinglish. |

**Style banks** (`_COACH_SUMMARY_STYLE_BANK`, `_COACH_WHY_STYLE_BANK`, `_COACH_ACTION_STYLE_BANK`): multiple templates per tone so summaries, “why it matters”, and “if you do one thing” vary by persona instead of sounding generic.

---

## 3. Balance levers: Don’t default to glycemic

Previously the coach could over-focus on glycemic load. Now protein and fiber gaps are weighted fairly and glycemic is primary only when the data clearly supports it.

**LLM prompt rules** (`main.py`, daily coach prompt):

```text
- Balance levers: do not default to glycemic; weight protein and fiber gaps equally.
  Vary if_you_do_one_thing angle (protein vs fiber vs timing) when possible.
```

```text
- Balance levers: do not default to glycemic load every day. Weight protein gap and
  fiber gap equally with glycemic/UPF/timing; only make glycemic the primary lever
  when it is clearly the biggest risk from the data.
- Vary the primary lever day to day: e.g. protein one day, fiber another, timing or
  UPF another. Avoid repeating the same main lever two days in a row unless data
  strongly demands it.
- Vary if_you_do_one_thing and tomorrow_focus: do not repeat the same focus or same
  phrasing three days in a row. Pick a different angle (protein vs fiber vs timing
  vs quality) when possible.
```

**Rules fallback logic** (`coach_daily_logic.py`):

- **Balance levers:** Glycemic no longer dominates when protein/fiber gaps are big.
- **Scoring:** `protein_gap_score` and `fiber_gap_score` compete with `glycemic_score`, `upf_score`, `timing_score`. Glycemic weight is slightly reduced.
- **Bottleneck boost:** When protein gap ≥ 20g, protein lever is boosted (e.g. `protein_gap_score = max(..., 0.75)`); when fiber gap ≥ 15g, fiber is boosted. So protein/fiber can win over glycemic when gaps are large.
- **Top lever drives copy:** `one_sentence_summary` and `if_you_do_one_thing` are chosen from the **top bottleneck** (protein / fiber / glycemic / upf / timing), so the “one thing” reflects the real main lever, not always glycemic.

---

## 4. Variety: Vary primary lever and “if you do one thing”

- **Day-to-day:** Primary lever is varied (protein one day, fiber another, timing, UPF) and not repeated two days in a row unless data strongly demands it.
- **if_you_do_one_thing / tomorrow_focus:** Different angle (protein vs fiber vs timing vs quality); same focus/phrasing is not repeated three days in a row.
- **Fallback actions:** `_pick_non_repeating_advice_key` / `_pick_non_repeating_action` prefer advice whose `semantic_key` is **not** in recent keys, so the coach doesn’t keep suggesting the same action.
- **Voice (meal-level):** `_voice_action_candidates` offers multiple levers (protein, fiber, UPF, glycemic, leucine, consistency); `_pick_non_repeating_action` picks one that wasn’t recently used.

---

## 5. Less repetition: Style picker + reroll

- **Template banks:** Several summary/why/action templates per tone; one is chosen with a deterministic seed so the same day/user gets a stable but varied line.
- **Similarity check:** `_is_repetitive_line(candidate, recent_lines, threshold=0.86)` compares a candidate to recent lines (Jaccard on normalized words). If too similar, the next template is tried.
- **Reroll:** If the chosen summary is too similar to `prev_summary`, or the chosen “one thing” is too similar to `prev_one_thing`, we **reroll** with a different template and seed so we avoid repeating the same phrasing.

Relevant code (`main.py`):

```python
if prev_summary and _is_repetitive_line(summary_line, [prev_summary], threshold=0.86):
    summary_line = _pick_style_line(..., [prev_summary], ...)  # reroll
if prev_one_thing and _is_repetitive_line(one_action_line, [prev_one_thing], threshold=0.86):
    one_action_line = _pick_style_line(..., [prev_one_thing], ...)  # reroll
```

---

## 6. Where it lives in code

| Improvement            | Location |
|------------------------|----------|
| Tone prompts & style   | `main.py`: `_COACH_SYSTEM_PROMPT`, `_DAILY_TONE_PROMPTS`, `_DAILY_TONE_PACK`, `_COACH_SUMMARY_STYLE_BANK`, `_COACH_WHY_STYLE_BANK`, `_COACH_ACTION_STYLE_BANK` |
| Balance levers (LLM)   | `main.py`: daily coach prompt strings (~9035–9067) |
| Balance levers (rules) | `coach_daily_logic.py`: bottleneck scoring, `protein_gap_score`/`fiber_gap_score` boost, `top_key` → `one_sentence_summary` / `if_you_do_one_thing` |
| Variety (non-repeat)   | `main.py`: `_pick_non_repeating_advice_key`, `_pick_non_repeating_action`, `_voice_action_candidates` |
| Anti-repetition        | `main.py`: `_is_repetitive_line`, `_pick_style_line`, reroll blocks in `_build_voice_fallback` (~6904–6920) |
| Tone application       | `main.py`: `_apply_daily_coach_tone`, tone rewrite flow |

---

## Before vs after (conceptual)

| Before                         | After |
|--------------------------------|--------|
| Coach often sounded the same regardless of tone. | Tone (supportive/strict/funny/indian_coach) clearly changes phrasing and energy. |
| Glycemic load often dominated. | Protein and fiber gaps weighted equally; glycemic is primary only when it’s clearly the biggest risk. |
| Same “one thing” / lever repeated. | Primary lever and if_you_do_one_thing vary by day and angle; non-repeating advice keys. |
| Same summary/action phrasing.   | Multiple templates per tone + similarity check + reroll when too close to previous line. |

These changes implement the P2 coach improvements (Issues 1, 2, 6, 7): tone, balance levers, variety, and less repetition.

# App issues and fix plan (12 items)

Mapped from user feedback: coach, nearby/maps, navigation, alerts, barcode, oil/kcal, follow-up questions, scan speed.

---

## 1. Coach voice not interactive; sounds same for every coach

**Issue:** LLM coach doesn’t feel interactive; tone doesn’t change meaningfully when switching coach.

**Where:** Backend `main.py` – `_coach_user_prompt`, coach daily/voice; `coach_daily_logic.py`; mobile coach tone selector and display.

**Recommended:**
- **Prompt:** In `_COACH_SYSTEM_PROMPT` / `_coach_user_prompt`, pass `tone_preference` (supportive/strict/funny/indian_coach) and ask the LLM to vary sentence structure, openings, and energy by tone. Add 1–2 example phrases per tone so output diverges.
- **Voice fallback:** In `_voice_fallback_response` and any rule-based fallback, ensure empathy/insight text differs clearly by `tone_preference` (not just one line).
- **Mobile:** Show which coach/tone is active and that “Coach: Live” uses the selected tone; consider A/B copy per tone so the user sees the difference.

**Scope:** Medium (prompt + fallback copy).

---

## 2. Too much glycemic load; coach repeats daily (protein, fiber, tomorrow focus, pattern)

**Issue:** System over-emphasises glycemic load; coach repeats “early protein”, “short of fiber”, “tomorrow focus”; pattern detection feels repetitive.

**Where:** Backend `_coach_user_prompt` (signals: avg_glycemic_load, glycemic_bucket); `coach_daily_logic` (rule_alerts, diagnosis, tomorrow_focus); LLM template (one_sentence_summary, if_you_do_one_thing, tomorrow_focus).

**Recommended:**
- **Weights:** In scoring or prompt, reduce relative weight of glycemic_load vs protein/fiber/satiety so GL doesn’t dominate the “biggest lever” message every day.
- **Variety:** In prompt, ask for rotation: “Vary the primary lever (protein one day, fiber another, timing another); avoid repeating the same lever two days in a row unless critical.”
- **Tomorrow focus:** Add “vary tomorrow_focus; do not repeat the same focus three days in a row” (or use a small recent-focus buffer and pass it into the prompt).
- **Pattern:** Pass last N days’ “if_you_do_one_thing” / diagnosis keys and ask LLM to avoid repeating the same pattern; optionally use `_pick_non_repeating_advice_key`-style logic for the main action.

**Scope:** Medium (prompt + optional scoring tweak).

---

## 3. Healthy nearby maps slow to load

**Issue:** Healthy nearby / map takes a long time to load.

**Where:** Backend `GET /places/healthy`; `healthy_food_map.build_healthy_food_map_response`; `enrich_places_for_healthy_map`; mobile fetch and state for healthy places/map.

**Recommended:**
- **Backend:** Reduce `limit` for initial load (e.g. 20 instead of 40); return sections with fewer enriched places first, then lazy-load or paginate. Consider caching by (lat, lng, radius, goal) with short TTL (e.g. 2–5 min).
- **Enrichment:** Run enrichment in parallel (asyncio or batch); skip or defer heavy enrichment for “list” view and only enrich on “tap place” or when expanding.
- **Mobile:** Show a skeleton or “Loading map…” immediately; request a smaller radius or limit first, then expand; avoid blocking the whole screen on one big request.

**Scope:** Medium–high (API + mobile).

---

## 4. “What should I eat” hides Scan Menu / Scan Food; confusion where analysis is

**Issue:** User taps “what should I eat” or Scan Food/Menu and doesn’t see where the analysis happens; has to open Best Nearby or scroll to “analyse” to understand.

**Where:** Mobile `App.js` – launcher / home (Scan Food, Scan Menu, Best Nearby); navigation to analysis result or “analyse” button.

**Recommended:**
- **Copy/placement:** Make the primary action after Scan Food / Scan Menu go straight to the screen where the result (or “Analyse” CTA) is visible, or show a one-line “Result appears below” / “Scroll down to see analysis” near the buttons.
- **Flow:** After starting a scan, navigate to the analysis/results view (or a dedicated “Your scan” strip) instead of leaving the user on the same card. Ensure “Analyse” or “See result” is above the fold or in a fixed bottom bar when in scan context.
- **Best Nearby:** Don’t hide Scan Menu; keep it visible on the same tab (e.g. “Scan Menu” next to “Decide My Next Meal” or in the place card) so the user doesn’t need to remember to open Best Nearby first.

**Scope:** UX/navigation (mobile).

---

## 5. Smart food alerts only in-app; not as phone notification; same suggestions daily

**Issue:** Alerts only appear when the app is open; user wants push notifications and more variety.

**Where:** Backend: smart alert generation and any push-send path (e.g. push_rollout, push_send_flow, expo_push_service); mobile: push registration, notification handling, and where “Smart Food Alerts” in-app is rendered.

**Recommended:**
- **Push:** Ensure smart alerts are sent via Expo push (or current push channel) when a “protein rescue” / “nearby option” trigger fires, not only written to in-app state. Use existing `send_smart_alert_for_user` (or equivalent) from a job/cron that runs in the background.
- **Variety:** Add diversity rules: don’t suggest the same venue two days in a row; rotate message template (protein rescue vs timing vs “light option”); optionally use a small “last_sent_alert” store to avoid repetition.
- **Mobile:** Register for push and handle notification tap to open the app to the “Smart Food Alerts” or relevant nearby screen.

**Scope:** Medium (backend push + mobile registration + variety logic).

---

## 6. “If you do one thing” in fat loss intelligence repeats

**Issue:** Same as (2) – “if you do one thing” feels repetitive.

**Where:** Same as (2): LLM coach response shape `if_you_do_one_thing`; fallback in `coach_daily_logic.build_fallback_coach_response`; `_pick_non_repeating_advice_key` and voice templates.

**Recommended:**
- **Template pool:** Enlarge the set of “if you do one thing” templates and pick by `_pick_non_repeating_advice_key` (or equivalent) using last 5–7 days’ keys so the same key doesn’t repeat.
- **LLM:** In prompt, pass recent “if_you_do_one_thing” summaries and ask to choose a different angle today (protein vs fiber vs timing vs UPF) unless one is critical.

**Scope:** Small–medium (prompt + template pool).

---

## 7. Coach with human touch, reality after each scan, motivating, “look like AI”

**Issue:** User wants a coach that feels human, reacts to each scan, is motivating, but still clearly AI.

**Where:** Post-scan coach message (voice or text); `coach/voice` or equivalent; mobile screen that shows “reality after each scan”.

**Recommended:**
- **Post-scan hook:** After each meal scan, call a short “post-scan coach” endpoint (or include in analysis response) that takes: last scan summary (kcal, protein, item names), day context, and returns 1–2 sentences: “Reality” (what this meal does for the day) + one motivating nudge. Use a dedicated, short LLM prompt so it feels like a reaction, not a generic summary.
- **Tone:** In that prompt, ask for “human, warm, motivating; one concrete observation about this meal; one forward-looking line; sound like a supportive coach, not a report.”
- **Mobile:** Show this “reality” line immediately under the scan result (and optionally in coach tab as “Last scan: …”) so it’s clearly tied to the scan.

**Scope:** Medium (new or extended endpoint + mobile placement).

---

## 8. Barcode scanning shows only kcal, not full macros

**Issue:** Barcode result should show complete kcal and macros.

**Where:** Backend already returns `per_100g`: kcal, protein_g, carbs_g, fat_g (e.g. `/barcode/{code}`, `/barcode/manual`). Mobile was only showing kcal in the post-scan alert.

**Done:** Mobile `App.js` – barcode result alert now shows full macros per 100g when available: “X kcal • P Xg • C Xg • F Xg (per 100g)”.

**Optional:** In history or any barcode “stored” view, ensure the same `per_100g` object is displayed (kcal + P/C/F) wherever barcode results are shown.

**Scope:** Done for main alert; optional for other screens.

---

## 9. Ask about ingredients when system doesn’t understand (not only whey); remember choice

**Issue:** For any meal, when the system is unsure about ingredients, it should ask (not only for supplements/whey); and it should remember the user’s answer for next time.

**Where:** Backend: analysis/LLM flow that decides “needs clarification”; supplement/food clarification flow; any “user_food_priors” or per-user memory. Mobile: UI for “What’s in it?” and saving the answer.

**Recommended:**
- **Trigger:** In meal analysis, if confidence is low or item is ambiguous (e.g. “protein powder”, “smoothie”, “coffee”), return a `clarification_questions` list (e.g. “Milk type?”, “Sweetener?”) and optional `clarification_key` (e.g. `coffee_milk_type`) so the client can show a single follow-up.
- **Store:** When the user answers, send to backend and store in user-level memory (e.g. `user_food_priors` or `user_ingredient_choices`) keyed by `clarification_key` + stable meal descriptor (e.g. “coffee at home”). Next time the same context is detected, prefill or skip the question.
- **Scope:** Backend (analysis + storage) + mobile (show questions, send answers, prefill).

**Scope:** Large (analysis contract + storage + mobile).

---

## 10. No oil / less oil selection doesn’t change kcal

**Issue:** When the user selects “no oil” or “less oil”, displayed kcal doesn’t update.

**Where:** Backend: analysis rerun or “edits” application that applies `set_oil_added_tsp` (and optionally portion); recalculation of totals. Mobile: where oil/portion choices are sent and where the updated totals are displayed.

**Recommended:**
- **Backend:** In the analysis/edits pipeline, when applying `set_oil_added_tsp` (and portion_multiplier), recompute item kcal (e.g. oil ~40 kcal/tsp) and propagate to `totals` / `total_kcal` in the response. Ensure the response returned after “Save” or “Apply” contains the updated totals.
- **Mobile:** After applying oil/portion, refresh the displayed result from the API response (or from local recompute if you have a shared formula). Don’t show stale totals.

**Scope:** Medium (backend recompute + mobile refresh).

---

## 11. Smart follow-up questions (e.g. coffee: milk type, sweetener) and remember

**Issue:** System should ask contextual questions (e.g. for coffee: almond milk? normal milk? sweetener?) and remember the answer for that user.

**Where:** Same as (9): analysis output (clarification_questions), user memory store, mobile UI.

**Recommended:** Implement as part of (9): generic “clarification_questions” + “clarification_key” + user memory. For coffee, analysis would return e.g. `clarification_questions: [{ key: "milk_type", label: "Milk?", options: ["None", "Almond", "Whole", "Low-fat", "Oat"] }, { key: "sweetener", ... }]` and the app would show them and send back answers; backend stores by user + context key.

**Scope:** Large (same as (9)).

---

## 12. Scan and analyse food takes too long; goal ~2 seconds

**Issue:** User wants scan + analysis to feel instant (~2 seconds).

**Where:** Backend: meal analysis (image → LLM or pipeline); mobile: capture, upload, wait for response, render.

**Recommended:**
- **Backend:** Optimise analysis path: smaller image or resize before LLM; use a faster model or a two-step flow (quick draft in &lt;1.5 s, then optional refinement); cache by image hash for repeated scans; consider a “quick estimate” endpoint that returns kcal + main macros first, details later.
- **Mobile:** Show “Analyzing…” and a provisional result (e.g. “~400 kcal”) as soon as a quick estimate is available; stream or poll for full result. Don’t block the whole UI on the full response.
- **Perception:** Skeleton UI, progress bar, or “Almost there…” after 1 s can make the same latency feel faster.

**Scope:** High (backend + mobile).

---

## Priority summary

| Priority | Issue | Fix type | Scope |
|----------|--------|----------|--------|
| Done | 8 – Barcode macros | Mobile alert text | Small |
| P1 | 10 – Oil changes kcal | Backend recompute + mobile refresh | Medium |
| P1 | 4 – Navigation / where is analysis | Mobile UX/navigation | Medium |
| P2 | 3 – Map load speed | Backend limit/cache + mobile | Medium–high |
| P2 | 1, 2, 6, 7 – Coach tone & repetition | Prompts + fallbacks + optional post-scan | Medium |
| P2 | 5 – Smart alerts push + variety | Backend push + variety logic | Medium |
| P3 | 9, 11 – Clarification questions + memory | New flow + storage + mobile | Large |
| P3 | 12 – Scan speed | Backend + mobile optimisation | High |

---

**Progress:** Issue 8 done (barcode macros). **P2 done:** Issue 3 (map limit + mobile limit=12), Issues 1/2/6/7 (coach prompt + fallback balance), Issue 5 (smart alerts: recent_sent_place_ids variety + push flow limit=12). **P1 done:** Issue 10 (oil/portion → kcal: normalizeAnalyzeResult ensures total_kcal/totals from rerun response; backend already recomputes), Issue 4 (hint under launcher: "Scan Food or Scan Menu → tap Analyse below to see your result in the Scan a meal section"). **P3 started:** Issue 12 (scan speed: SCAN_MAX_EDGE_PX 1024, SCAN_JPEG_QUALITY 85, env overrides). **P3 (9/11) done:** Clarification questions + remember: backend returns `clarification_questions` (key, label, options) for rule-based ambiguous items (coffee/espresso/latte/chai → milk_type, sweetener; smoothie → milk_base, sweetener). Stored in `backend/user_ingredient_choices.py` (file store keyed by user_id + food_token). Rerun accepts `clarifying_answers: [{ key, value }]`, saves choices, enriches first item name for nutrition. Mobile shows "Confirm details (we'll remember)" with per-question options and "Apply and update kcal".

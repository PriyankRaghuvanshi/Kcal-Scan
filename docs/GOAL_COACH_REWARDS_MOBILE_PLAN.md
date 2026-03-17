# Goal Coach Rewards & Progress — Mobile Implementation Plan

**Scope:** Surface backend reward and progress signals in the app. No backend logic changes. Premium dark UI; flagship AI coaching feel.

**Backend fields already returned:**
- `daily_win`, `protein_streak_days`, `logging_streak_days`, `win_line`
- Updated consumed kcal / protein in Goal Coach daily payload
- `win_summary`
- `report_card_facts.protein_days_this_week` (weekly)

---

## 1. UX goals

- **Clarity:** User sees “today so far” (kcal + protein vs target) and understands progress at a glance.
- **Momentum:** Streaks (protein, logging) feel rewarding and visible without being gamified or childish.
- **Recognition:** After a scan that improves the day, the user gets a short, relevant reward line (e.g. “That keeps your protein streak alive,” “You’re now in range for today”).
- **Coherence:** Win/streak/reward UI lives in clear places: Goal Coach daily card, Journey, scan result, weekly review.
- **Premium feel:** Dark theme, restrained copy, no confetti or cartoon badges; feels like a top-tier coaching product.
- **Non-disruptive:** Add new UI without removing or burying existing features.

---

## 2. Goal Coach daily progress design

**Where:** Inside **DailyCoachCard** (“Today’s coach”). This card already shows calories and protein consumed vs target with progress bars.

**What to show:**
- **Primary:** Consumed vs target for **today** using `daily.consumed_so_far` and `daily.today_targets` (or equivalent from the daily payload). Already present; ensure data is **updated after a scan** by refetching Goal Coach daily when scan result is applied (or when user returns to home).
- **Elegant treatment:**
  - Keep the two-column layout (Calories | Protein) with numeric “X / Y” and a thin progress bar.
  - Use design tokens: `colors.success.primary` for bar fill when in range; optional subtle amber when over calorie target; keep bar background dark (`colors.surface.elevated` or existing `barBg`).
  - Add a single “Today so far” subheading above the row if the card title is “Today’s coach,” so it’s clear this is cumulative for the day.
- **After-scan updates:** When the user completes a scan and applies it (or when they “Done” from scan result), trigger `fetchGoalCoachDaily()` so the daily card shows updated consumed totals. No new API; same refetch that may already run on navigation or after check-in.

**Concrete changes:**
- **DailyCoachCard:** Accept and display `consumed_so_far` and `today_targets` from `daily` (already does). Optionally accept `daily_win` and surface a one-line “win” state (see win_line below).
- **App.js:** After scan apply / check-in / return to Let’s Go tab, call `fetchGoalCoachDaily()` so the card reflects latest consumed.

---

## 3. Streak and reward design

**Data:** `protein_streak_days`, `logging_streak_days` (from Goal Coach daily response).

**Presentation (premium, not childish):**
- **Option A — In DailyCoachCard:** Below the calorie/protein row, add a compact “momentum” row: two small streak indicators (e.g. “Protein 3d” and “Logging 5d”) as **pill chips** with muted background and success-tinted text. No flames or emoji; typography and color only.
- **Option B — In JourneyCard:** Journey already has “X days streak.” Extend to show **protein streak** and **logging streak** as two separate lines or two small stats (e.g. “Protein streak: 3 days” / “Logging streak: 5 days”) so Journey becomes the “progress + streaks” card and Daily Coach stays “today’s numbers + best action.”
- **Recommendation:** Show **both** streaks in **DailyCoachCard** (today’s context) as chips; optionally mirror or summarize in JourneyCard (e.g. “Protein streak: 3 · Logging: 5”) for consistency. Single source of truth: `goalCoachDaily.protein_streak_days` and `goalCoachDaily.logging_streak_days`.

**Styling:**
- Chips: `backgroundColor: colors.surface.elevated`, `borderColor: colors.surface.cardBorder`, `borderWidth: 1`, small padding, `fontSize: typography.xs`, `color: colors.success.text` (or `colors.text.secondary`). No gradient, no illustration.
- Only render if streak ≥ 1 (0 streak can be hidden or shown as “0” depending on product choice; recommend hide 0 to avoid noise).

**Placement:**
- **DailyCoachCard:** Below the progress row, above “Best action” / coach summary. One row with two chips: `Protein 3d` | `Logging 5d`.
- **JourneyCard:** Optional second line under “Day X of Y” / existing streak: “Protein 3d · Logging 5d” so users who scroll see it in Journey too.

---

## 4. `win_line` placement

**Data:** `daily.win_line` — e.g. “Protein target met.”, “3-day protein streak.”, “Day in range.”, “2-day logging streak.”

**Where to show:**
- **Primary:** Inside **DailyCoachCard**, below the progress row (and below streak chips if present). One line of copy, subtle success styling.
- **When to show:** When `win_line` is non-empty. When empty (e.g. first day, no wins yet), hide the block entirely.
- **When to emphasize:** Use normal emphasis (same as coach summary): readable but not loud. “Emphasized” can mean slightly larger font or success color; avoid a large banner so it doesn’t compete with “Best action.”

**Styling:**
- `fontSize: typography.sm`, `color: colors.success.text`, optional small icon (e.g. check or minimal dot) to the left. No box or card; a single text line with marginTop so it sits between progress/streaks and “Best action.”

**Hide when:**
- `win_line` is missing or empty string. Do not show a placeholder.

---

## 5. After-scan reward feedback design

**Goal:** When a scan improves the user’s day (e.g. moved toward protein target, kept streak, put them in range), show a short reward message in the **scan result** flow.

**When to show:**
- After the scan result is shown and we have:
  - Updated goal-coach context (e.g. from a refetched daily payload, or from scan response if backend ever returns a small “goal_coach_impact” object). **Practical MVP:** Refetch `goalCoachDaily` after “Apply” or “Done” from scan result; then derive “did this scan help?” from comparing previous vs new state, or from a single new optional field from backend (e.g. `scan_goal_impact: { win_line, improved_streak }`). If backend does not yet return scan-specific win text, use **heuristics on the client:** e.g. if `remainingToday` (or daily consumed) moved toward target and user has a protein streak, show “That keeps your protein streak alive.” or “Nice — this moved you closer to your protein target.”
- **Simplest MVP:** Add an optional prop to **ScanResultScreen**, e.g. `rewardLine: string | null`. When non-null, render it in a small block below the goal-fit line (or below macro card). App.js computes `rewardLine` after scan apply: e.g. call `fetchGoalCoachDaily()` then set state from `goalCoachDaily.win_line` or from a simple rule (“if protein_streak_days >= 1 and scan added protein, show streak line”). Alternatively backend could return a one-off `post_scan_win_line` in scan response; then App passes it as `rewardLine`.

**What to show (examples):**
- “Nice — this moved you closer to your protein target.”
- “That keeps your protein streak alive.”
- “You’re now in range for today.”
- “Protein target met today.”

**Where in scan result:**
- **Placement:** Below the **goal-fit line** (the “Fits your day” / “Good for protein today” line), above the “Done” / “Clear scan” actions. This keeps reward close to the macro/goal context.
- **Component:** A single **micro-coach line** (one line of text, success color, small font). Not a full card, not a toast; an inline block so it feels part of the result.
- **Optional:** If you prefer a compact card, use a thin bordered block (same style as goal-fit) with one line of copy; still no modal or toast.

**Implementation note:** To avoid delaying the scan result, show the reward line only when:
- User has already seen the result (hero + macro + goal-fit), and
- Either (a) backend includes a `post_scan_win_line` in scan/check-in response, or (b) after “Done” we refetch Goal Coach daily and then show the reward line (e.g. in the same view below the CTA, or on the next screen as a small banner). **Recommended for MVP:** Refetch after “Done”; if the daily payload’s `win_line` or streak values indicate a “win,” show a small reward line **above the primary CTA** on the next render (e.g. “You’re on a 3-day protein streak.”). Alternatively show it in the same ScanResultScreen if we pass updated `goalCoachDaily` back into the screen (e.g. after refetch parent re-renders and passes `rewardLine`).

---

## 6. Weekly reward / win summary design

**Data:** `win_summary` (e.g. “3/5 protein days this week.”, “Strong week: 4/5 protein days.”); `report_card_facts.protein_days_this_week` (number).

**Where to show:**
- **WeeklyPlanReviewCard** already shows “Weekly review,” headline, adherence, main win, bottleneck, next focus. Add a **win summary** block that surfaces `review.win_summary` and, if available, `review.report_card_facts.protein_days_this_week` (e.g. “Protein days this week: 4”).

**How:**
- **win_summary:** One line below the adherence score (or below “Main win” if that exists). Style: `typography.sm`, `colors.success.text`, no icon unless minimal. If `win_summary` is empty, hide.
- **protein_days_this_week:** Optional small stat: “Protein days: 4/7” in the same area or inside “report card” if you add a minimal facts row. Keeps it motivating but factual.

**Tone:** Premium and calm. Copy is already from backend; avoid extra decoration (no big medals or “You crushed it!”). “Strong week: 4/5 protein days.” is enough.

---

## 7. UI hierarchy recommendations

- **Goal Coach (Let’s Go tab):**
  - **GoalPlanCard:** Plan summary, targets, first steps. No change to hierarchy; keep as top card.
  - **JourneyCard:** Day X of Y, (optional) protein/logging streak summary, weight change, photo status, next milestone. Streaks here are secondary to “Day X” and journey milestones.
  - **DailyCoachCard:** Primary home for **daily progress** (kcal/protein bars), **streaks** (chips), **win_line** (one line). Then best action, coach summary, risk flags, CTAs. Order: title → “Today so far” progress row → streak chips → win_line → best action → summary → risks → CTAs.
  - **WeeklyPlanReviewCard:** Headline, adherence, main win, **win_summary** (+ optional protein_days_this_week), bottleneck, next focus, CTA.

- **Scan Result:**
  - Hero → Macro card → goal-fit line → **[reward line when present]** → insight/items/clarification/details → actions → disclaimer. Reward line is part of the same scroll, not a modal.

- **Fat Loss Intelligence (if present):**
  - Do not duplicate win_line or streaks here. FLI stays focused on predictions and risk; progress/streaks remain in Goal Coach and Journey.

- **General:** Progress and rewards live under Goal Coach and Journey; scan result only gets the one-off reward line. No new top-level tab or screen for “rewards.”

---

## 8. React Native implementation plan

**Assumptions:** Backend already returns the listed fields in existing endpoints. No new API contracts; only consumption and UI.

### 8.1 Files / components to touch

| Area | File(s) | Change |
|------|---------|--------|
| Daily progress + streaks + win_line | `mobile/components/DailyCoachCard.js` | Accept `daily.protein_streak_days`, `daily.logging_streak_days`, `daily.win_line`. Render progress (already there), add streak chips row, add win_line line. Use design tokens; no `gap` if current codebase avoids it (use margins). |
| Journey streaks | `mobile/components/JourneyCard.js` | Optional: accept `proteinStreakDays`, `loggingStreakDays` and show one short line (e.g. “Protein 3d · Logging 5d”). |
| Weekly win summary | `mobile/components/WeeklyPlanReviewCard.js` | Read `review.win_summary` and `review.report_card_facts?.protein_days_this_week`. Render win_summary line; optionally “Protein days: X/7”. |
| Scan result reward | `mobile/components/ScanResultScreen.js` | Add optional prop `rewardLine?: string`. When set, render a small block below goal-fit line (same section or new small section) with success styling. |
| Data flow / refetch | `mobile/App.js` | After scan apply or “Done,” call `fetchGoalCoachDaily()` so daily card and any downstream reward logic see updated data. Pass `goalCoachDaily` (or derived `rewardLine`) into ScanResultScreen when available. Compute `rewardLine` for scan: e.g. after refetch, if `win_line` is set or protein_streak_days ≥ 1 and scan had protein, set reward line state and pass to ScanResultScreen on next render; or pass updated daily into a small helper that returns a reward string. |
| Design tokens | `mobile/designTokens.js` | No change unless you add a token for “reward” or “streak” (optional; can use existing `success` and `slate`). |

### 8.2 Phasing (safe and incremental)

1. **Phase 1 — DailyCoachCard only**
   - Add `protein_streak_days`, `logging_streak_days`, `win_line` to props (from `daily`).
   - Render streak chips (only if ≥ 1) and win_line line.
   - No change to scan flow or weekly card. Verify Let’s Go tab shows streaks and win_line when backend sends them.

2. **Phase 2 — Weekly win summary**
   - In WeeklyPlanReviewCard, read and display `win_summary` and optionally `report_card_facts.protein_days_this_week`.
   - Verify weekly review shows the new line(s).

3. **Phase 3 — Scan result reward line**
   - Add `rewardLine` to ScanResultScreen; render below goal-fit when present.
   - In App.js, after “Done” or apply from scan, refetch Goal Coach daily; compute a single reward string (from `win_line` or simple heuristic) and pass as `rewardLine` (e.g. store in state and pass to ScanResultScreen; if result is still mounted, show it; otherwise show on next scan or on return to home). Keep logic minimal (e.g. “if win_line after refetch, use it as rewardLine for next time” or “if we have new daily_win, set rewardLine for current result view”).

4. **Phase 4 — Optional Journey streak line**
   - Pass streak counts from App to JourneyCard; show one compact line. Low priority.

### 8.3 Keeping business logic unchanged

- **No backend changes:** All data comes from existing `/goal-coach/daily` and `/goal-coach/weekly` and existing scan/check-in responses.
- **Refetch only:** After scan, the only new behavior is calling `fetchGoalCoachDaily()` (and possibly `fetchGoalCoachWeekly()` if you want weekly data fresh). No new endpoints.
- **Derived UI only:** `rewardLine` is derived from existing `daily.win_line` or from current daily state after refetch; no new business rules in backend.
- **Optional backend enhancement later:** Backend could add a `post_scan_win_line` or `scan_goal_impact` in the scan/check-in response so the app doesn’t need to refetch to show reward; that would be a later, optional step.

---

## 9. Recommended implementation order

1. **DailyCoachCard:** Add streak chips and win_line from `daily`. Ship and verify with real daily payload.
2. **WeeklyPlanReviewCard:** Add win_summary and optional protein_days_this_week. Ship and verify.
3. **ScanResultScreen:** Add optional `rewardLine` prop and render block. In App, after scan “Done” (or apply), refetch Goal Coach daily; set reward line from `goalCoachDaily.win_line` (or simple rule) and pass to ScanResultScreen (or show on next mount). Ship and verify.
4. **App.js:** Ensure refetch of Goal Coach daily runs after scan apply / check-in so daily card and reward line stay in sync.
5. **JourneyCard (optional):** Add optional streak summary line for consistency.

This order keeps the implementation practical, premium, and aligned with the existing architecture while surfacing all reward and progress signals in the right places.

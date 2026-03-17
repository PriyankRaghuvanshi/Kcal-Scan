# Home Screen Redesign Plan — Premium Hero Dashboard

**Goal:** Redesign the Home screen so it feels like a **premium hero dashboard** in the same quality tier as top App Store AI calorie coaching products—instantly premium, clear, aspirational, and conversion-friendly—while preserving CalorieClick.ai’s dark identity and keeping functionality rich.

**Constraints:** No branding clone; luxurious dark UI; App Store–grade polish; implementable inside the current React Native / Expo app.

---

## 1. Critique of the current Home screen

- **No single hero above the fold.** The first thing the user sees is the top row (title + plan + logout), then immediately the launcher card with “What should I eat right now?” and four actions (Scan Food, Scan Menu, Best Nearby, Smart Alerts, Goal Coach). “Today” (remaining kcal/protein, win line, streak) is buried inside the Goal Coach block, which is itself inside one large card far down the scroll. So the user does not get “how am I doing today?” or “what’s my one next step?” in the first 5 seconds.
- **Launcher and progress are inverted.** The launcher is action-focused (good) but competes with four equal-weight secondary cards (Scan Menu, Best Nearby, Smart Alerts, Goal Coach). Daily progress and reward (remaining today, win_line, streaks) live inside the Goal Coach wrapper, which appears after Smart Alerts. So “today” and “momentum” are not part of the first impression.
- **One giant Goal Coach card.** Goal Coach is a single outer card containing GoalPlanCard, JourneyCard, DailyCoachCard, WeeklyPlanReviewCard, Progress (weight + photo), trial banner, and paywall. That’s six conceptual blocks in one box. It feels cramped and same-weight; the daily “today” summary and primary CTA don’t stand out as the hero.
- **Flat visual rhythm.** Container uses `gap: 14` and cards use similar padding (16–20px). There’s no clear “hero zone” vs “supporting block” spacing. Everything feels one level.
- **Scans left and goals are another full card.** Scans left, goals, and “protein left today” sit in a separate card with multiple buttons (Refresh, Restore, Edit) and a lot of tiny copy. Important numbers (remaining kcal, protein) don’t read as the hero; they’re mixed with usage and restore copy.
- **Smart Alerts between launcher and Goal Coach.** Smart Alerts appears as its own card between the launcher and Goal Coach. It’s useful but competes for attention and breaks the flow from “actions” to “today/progress.”
- **Launcher copy and helper text.** “Scan Food or Scan Menu → tap Analyse below…” and the coach line add clarity but also add length. For a premium first impression, the hero zone should be minimal: one headline, one primary action, and (if space) today’s number.
- **Hardcoded colors and spacing.** Styles use hex colors (#0b0b0b, #1f2430, #22c55e, #050a13, etc.) and magic numbers (14, 16, 18, 20, 26). designTokens exist but aren’t used on home. That makes it harder to keep a consistent premium dark system.
- **No clear “today” strip.** There is no dedicated “Today” hero (e.g. “X kcal left · Y g protein” or “In range” / win_line) at the very top. That’s the single biggest missed opportunity for a premium dashboard feel.
- **First 5 seconds:** The user sees title, plan, then a big launcher card with five entry points. They do not see “how am I doing today?” or one dominant “do this next” until they scroll or parse the launcher. So the first impression is “menu of features,” not “your day + one action.”

---

## 2. Redesign goals

- **First 5 seconds:** User sees (1) what the app is (AI calorie coach), (2) how they’re doing today (remaining kcal · protein or “In range” / win line), and (3) one primary action (Scan meal or View today’s action). No scrolling required for that.
- **Hero zone:** A dedicated “Today” hero at the top—compact strip or card—with today’s numbers or status and one primary CTA. This is the flagship element.
- **Launcher:** Clean, minimal. One hero action (Scan Food) and a small set of secondary actions (Scan Menu, Best Nearby, etc.) without four equal boxes. Optional: Smart Alerts and Goal Coach as compact rows or links instead of full launcher tiles.
- **Progress and reward visible:** Daily progress (consumed vs target), streak chips, and win_line live in a dedicated “Today’s coach” or daily card that is **separate** from the Goal Coach wrapper and appears **above or right after** the launcher. So “today” and “momentum” are above the fold or one short scroll away.
- **Goal Coach unblocked:** Break the single Goal Coach card. Render GoalPlanCard, JourneyCard, DailyCoachCard, WeeklyPlanReviewCard as **separate cards** with clear section spacing. No outer wrapper card. Optional small section label “Goal Coach” above the first.
- **Scans left and FLI:** Scans left can be a compact row inside the hero or a smaller card; FLI stays a card but with clearer hierarchy (one primary CTA, less nested UI). So the home doesn’t feel like “five equal cards.”
- **Typography and spacing:** Use design tokens. Introduce spacing tiers: tight (8–12px) for related items, medium (16–20px) for same card, large (24–32px) for between sections. One clear “hero” card or zone with slightly larger radius or padding.
- **CTA hierarchy:** One primary CTA on the hero (e.g. “Scan meal” or “View today’s action”). Launcher secondary actions are visually lighter. Edit, Refresh, Restore, Settings are tertiary (text or small outline).
- **Emotional payoff:** Win line and streak chips visible in the daily/today block. User feels “the app sees my progress” without gamification.
- **Conversion:** Hero zone and daily block are screenshot-ready and clearly communicate “premium AI coach” and “your day at a glance.”

---

## 3. New Home screen information hierarchy

**Tier 1 — Hero (above the fold, no scroll)**  
- **Today strip/card:** Remaining kcal · protein (or “In range” / win_line when applicable). One primary CTA: “Scan meal” or “View today’s action” (from Goal Coach). Optional: very short streak or win line (e.g. “3-day protein streak”) in one line.
- **Purpose:** Answer “how am I doing?” and “what do I do next?” in 2 seconds.

**Tier 2 — Primary actions (launcher)**  
- **Scan Food** as the single hero action (large, one tap).  
- **Scan Menu** and **Best Nearby** as secondary actions (one row, two compact tiles or buttons).  
- Optional: one line “Smart Alerts” and “Goal Coach” as text links or small chips that open their flows, so the launcher doesn’t become four equal boxes.

**Tier 3 — Today’s progress and momentum**  
- **Daily progress card** (or reuse DailyCoachCard here): consumed vs target (kcal, protein), streak chips, win_line, best action, one primary CTA. This is the “Today’s coach” content. Place it **immediately after** the launcher (or merge “today” numbers into the hero and keep this card for bars + streaks + action).

**Tier 4 — Goal Coach (plan, journey, weekly)**  
- **Goal plan** (GoalPlanCard) — separate card.  
- **Journey** (JourneyCard) — separate card.  
- **Weekly review** (WeeklyPlanReviewCard) — separate card.  
- Progress (weight, photo) can stay in a small card or at the bottom of Journey.  
- No single “Goal Coach” wrapper card; optional section label above the first card.

**Tier 5 — Smart Alerts**  
- One card: either “Turn on” CTA or preview count + “View all.” Visually lighter than the hero and daily block. Can sit after launcher or after Goal Coach cards depending on product priority.

**Tier 6 — Scans left and FLI**  
- **Scans left:** Compact card or a row in the hero (e.g. “12 left today” with Upgrade only when low). Refresh/Restore as secondary or in settings.  
- **FLI:** One card with clear header, one primary CTA (Refresh or View daily), coach voice or preview. Less nested; tokens for inner spacing.

**Order on the scroll (recommended)**  
1. Header (title, plan, logout)  
2. **Today hero** (remaining kcal · protein or “In range” + one primary CTA [+ optional streak/win line])  
3. **Launcher** (Scan Food hero + Scan Menu | Best Nearby [+ Smart Alerts / Goal Coach as links or compact row])  
4. **Daily progress card** (consumed vs target, streaks, win_line, best action, CTA)  
5. **Smart Alerts** card (if not folded into launcher)  
6. **Goal Coach** section label (optional)  
7. **GoalPlanCard**  
8. **JourneyCard**  
9. **DailyCoachCard** (if not merged with “daily progress” above)  
10. **WeeklyPlanReviewCard**  
11. Progress (weight, photo) — small card or inside Journey  
12. **Scans left** card (compact)  
13. **FLI** card  

**What becomes secondary or lower**  
- “Scans left” details (Refresh, Restore, full goals line) → compact or secondary.  
- Full goals breakdown (C, F, fiber) → behind “Edit” or in a detail view.  
- Smart Alerts preview list → “View all” from one card.  
- UPF processed block → keep only when visible; style as a small status card.  
- Launcher helper lines (“Scan Food or Scan Menu…”) → shorten or move below launcher as one line; don’t dominate the hero.

---

## 4. Card-by-card redesign plan

**Header (topRow)**  
- Keep: CalorieClick.ai, plan, Plans (if free), Logout.  
- Optional: Slightly larger title or use `typography.hero` for the app name; plan in `text.secondary` from tokens. Use tokens for padding and gap.

**Today hero (new)**  
- **Component:** A single View or card (e.g. `HomeTodayHero`).  
- **Content:**  
  - Line 1: “Today” or “Your day” (small label).  
  - Line 2: Remaining kcal and protein (e.g. “1,240 kcal left · 48g protein”) OR “In range” / win_line when applicable. Use `typography.xl` or `hero` for the numbers; success color when in range.  
  - Line 3: One primary CTA button — “Scan meal” or “View today’s action” (from getDailyActions(goalCoachDaily).primaryAction when plan exists).  
  - Optional line 4: win_line or streak (e.g. “3-day protein streak”) in success color, one line.  
- **Style:** Dark surface (`surface.card` or `surface.elevated`), large radius (`radius.xl` or `radius.xxl`), padding from tokens (`spacing.lg`–`spacing.xl`). Subtle border. No nested cards.  
- **Data:** `remainingToday`, `goalCoachDaily?.win_line`, `goalCoachDaily?.protein_streak_days`, `goalCoachDaily?.logging_streak_days`, `getDailyActions(goalCoachDaily).primaryAction`.

**Launcher card**  
- **Simplify:** Keep “What should I eat right now?” (or shorten to “What’s next?”). Drop or shorten the subline.  
- **Primary:** One large “Scan Food” tile (current launcherPrimaryCard style, tokens). Icon + “Scan Food” + one line subtitle.  
- **Secondary row:** Two tiles only — “Scan Menu” and “Best Nearby.” Same width; compact.  
- **Tertiary:** “Smart Alerts” and “Goal Coach” as one row of text links or small chips (e.g. “Smart Alerts” · “Goal Coach”) that open their flows. Or keep as two smaller tiles if product wants them prominent.  
- **Remove or shorten:** The long coach line and “Scan Food or Scan Menu → tap Analyse…” to one short line below the launcher if needed.  
- **Style:** Use tokens (colors, spacing, radius). Slightly less padding than the hero so the hero feels more important.

**Daily progress card (Today’s coach)**  
- This can be **DailyCoachCard** in the new position (right after launcher). Content: consumed vs target bars, streak chips, win_line, best action, primary + secondary CTA.  
- **Or** a new compact “Today’s numbers” card that only shows bars + streak + win_line and links “See full coach” to scroll or modal.  
- **Style:** Same card style as others (tokens); no nested cards inside. Clear title “Today’s coach” or “Your day.”

**Smart Alerts card**  
- When off: One card, one line of benefit, one CTA “Turn on alerts.” Settings (gear) as icon button.  
- When on: Title + count in one line; up to 2–3 preview items; “View all” as text link. No nested cards; use list items with dividers or spacing.  
- **Style:** Tokens; slightly smaller title or muted so it doesn’t compete with hero and daily.

**Goal Coach block → separate cards**  
- **Remove** the single wrapper `<View style={styles.card}>` that contains all of Goal Coach.  
- **Render in order:**  
  - Optional: `<Text style={sectionLabel}>Goal Coach</Text>`  
  - `<GoalPlanCard ... />` with `marginBottom: spacing.section`  
  - `<JourneyCard ... />` with `marginBottom: spacing.section`  
  - `<DailyCoachCard ... />` with `marginBottom: spacing.section` (or skip if daily content is in the “Today” hero + daily progress card above)  
  - `<WeeklyPlanReviewCard ... />` with `marginBottom: spacing.section`  
  - Progress (weight, photo) in a small card or inside Journey  
  - Trial ending banner and paywall card when applicable  
- **Style:** Each card uses the same `card` style from tokens (or a shared `styles.card` that references tokens). Section spacing at least `spacing.section` (28) or `spacing.xl` (20).

**Scans left card**  
- **Compact:** Title “Scans left”; one line “X today · Y this month.” When low: one inline “Upgrade” button. Refresh and Restore as text links or small secondary buttons.  
- **Move:** Goals (kcal, P, C, F) and “Protein left today” can stay in this card as 1–2 lines or move to the Today hero. Avoid a long paragraph; use tokens for typography.  
- **Style:** Same card style; less padding if it should feel supporting.

**FLI card**  
- **Simplify:** One header (title + one primary “Refresh” or “View daily”). One short subline. Coach voice in one block (headline + supporting). Weekly report card as its own block with spacing. No card-inside-card; use dividers and tokens.  
- **Style:** Tokens; one primary CTA; Profile and Weekly as secondary (small buttons or links).

**UPF processed block**  
- Keep only when `upfScanResult || upfScanError || upfScanBusy`. Style as a small status card with minimal padding; don’t let it dominate.

---

## 5. CTA and launcher redesign

**Primary CTA (one per hero)**  
- **Today hero:** One button. Label = “Scan meal” when no plan or no primary action; otherwise “View today’s action” (e.g. “Scan your meal,” “Log breakfast”) from `getDailyActions(goalCoachDaily).primaryAction`.  
- **Style:** Filled background (`colors.success.primary`), inverse text, large tap target, `radius.lg` or `radius.xl`.  
- **Behavior:** Opens camera for meal scan or runs the Goal Coach primary action (e.g. open scan camera).

**Launcher actions**  
- **Scan Food:** Single hero tile. Same as current primary launcher card; use tokens.  
- **Scan Menu + Best Nearby:** Two tiles in one row; equal width; outline or muted fill so they’re clearly secondary to Scan Food.  
- **Smart Alerts + Goal Coach:** Either (a) two smaller tiles in a second row, or (b) one row of text links (“Smart Alerts” · “Goal Coach”) to reduce visual weight. Product choice.

**Secondary CTAs**  
- **Daily progress card:** Primary = same as Goal Coach primary action; secondary = secondary action (e.g. “See weekly”) as outline or text.  
- **Scans left:** “Upgrade” when low (primary); “Refresh” and “Restore” as text or outline.  
- **FLI:** “Refresh” or “View daily” as primary; Profile and Weekly as text or small outline.  
- **Goal Coach cards:** Each card keeps its own primary CTA (e.g. “View today’s action,” “Log weight”). No duplicate “Scan meal” in every card.

**Tertiary**  
- Edit goals, Settings (gear), “See plans,” “View all” — text or small outline only. No green fill.

---

## 6. Reward / momentum / progress redesign

- **In the Today hero (optional):** One short line when `win_line` or streak is present, e.g. “3-day protein streak” or “Protein target met.” Success color; small type so it doesn’t overpower the numbers and CTA.  
- **In the Daily progress card (DailyCoachCard):**  
  - Below the calorie/protein bars: **streak chips** (“Protein 3d” · “Logging 5d”) when ≥ 1. Use small pills with success-tinted text and muted background (tokens).  
  - Below streaks: **win_line** when non-empty. One line, success color.  
  - Then “Best action” and coach summary.  
- **In JourneyCard:** Day X of Y and streak as the visual focus (larger type, success for streak). Optional: protein/logging streak summary.  
- **In WeeklyPlanReviewCard:** win_summary and protein_days_this_week with success tint.  
- **No confetti or badges.** Premium = one line of copy + color + optional number.  
- **Data:** All from existing backend (`goalCoachDaily`, `goalCoachWeekly`, `remainingToday`). No new APIs.

---

## 7. Typography, spacing, and dark-theme polish strategy

**Typography**  
- **Hero numbers (today):** `typography.hero` or `typography.xxl`, `colors.text.primary` or `colors.success.text` when in range.  
- **Card titles:** `typography.lg` or `typography.xl`, `fontWeight: extrabold`, `colors.text.primary`.  
- **Body / sublines:** `typography.sm` or `typography.base`, `colors.text.secondary`.  
- **Tertiary / hints:** `typography.xs` or `typography.sm`, `colors.text.muted`.  
- **Outcomes (win line, “In range”):** One step up (e.g. `typography.md`) and `colors.success.text`.  
- **Import designTokens** in App.js (or a shared home styles file) and use these keys instead of hardcoded fontSize and colors.

**Spacing**  
- **Container:** Padding from tokens (e.g. `spacing.lg` or `spacing.xl`). Bottom padding `spacing.section * 2` for scroll comfort.  
- **Between sections:** `marginBottom: spacing.section` (28) or `spacing.xl` (20) between major cards.  
- **Inside cards:** `spacing.base` (12) or `spacing.lg` (16) for vertical rhythm; `spacing.sm` between related elements.  
- **Avoid:** Uniform 12–14px everywhere. Use at least two tiers: “same section” (12–16) and “new section” (20–28).

**Dark theme**  
- **Background:** `colors.surface.primary` for screen; `colors.surface.card` for cards; `colors.surface.elevated` for hero or inner highlight. Replace #000, #0b0b0b, #050a13 with tokens.  
- **Borders:** `colors.surface.cardBorder` for all card borders. Replace #1f2430, #263d62.  
- **Success:** `colors.success.primary` for primary CTA and “in range”; `colors.success.text` for win line and streak. Use sparingly.  
- **Amber:** For “low scans” and caution only.  
- **Radius:** `radius.xl` or `radius.xxl` for cards; `radius.lg` for buttons. Keep consistent.

**Polish**  
- Add subtle shadow to the Today hero card (`shadows.sm` or `shadows.md`) so it feels elevated.  
- Ensure tap targets are at least 44pt.  
- No `gap` if the codebase avoids it; use marginBottom/marginRight for spacing between launcher tiles.

---

## 8. React Native implementation plan

**New or extracted components**  
- **HomeTodayHero:** Receives `remainingToday`, `goalCoachDaily` (for win_line, streaks, primaryAction), `onScanPress`, `onPrimaryAction`. Renders the today strip/card and one primary CTA. Can live in `mobile/components/HomeTodayHero.js` and use designTokens.  
- **Optional:** Extract the launcher into `HomeLauncher.js` (title, Scan Food, Scan Menu, Best Nearby, Smart Alerts / Goal Coach links) so App.js stays readable.  
- **No change** to GoalPlanCard, JourneyCard, DailyCoachCard, WeeklyPlanReviewCard, WeeklyPlanReviewCard, SmartAlertCard, or FLI block logic; only their **order** and **wrapper** change.

**App.js changes**  
1. **Import** `colors`, `spacing`, `radius`, `typography`, `shadows` from `./designTokens` (or from a home-specific file that re-exports them).  
2. **Insert** the Today hero immediately after the header (when `activeScreen !== "healthy_nearby"`). Render `<HomeTodayHero ... />` with props from `remainingToday`, `goalCoachDaily`, `getDailyActions`, and handlers.  
3. **Simplify** the launcher: keep one primary Scan Food tile and one row of Scan Menu + Best Nearby; optionally replace the second row (Smart Alerts, Goal Coach) with text links or keep as smaller tiles. Shorten or move the helper line.  
4. **Remove** the single Goal Coach wrapper `<View style={styles.card}>`. Replace with a fragment or a wrapper View with no card style. Render in order: optional section label, GoalPlanCard, JourneyCard, DailyCoachCard, WeeklyPlanReviewCard, Progress card, trial banner, paywall card. Add `marginBottom: spacing.section` (or 28) between each.  
5. **Reorder** so that after the launcher comes: (a) Daily progress card (DailyCoachCard) — so “today” content is high — then Smart Alerts, then Goal Coach cards. Or: Today hero → Launcher → Smart Alerts → DailyCoachCard → GoalPlanCard → JourneyCard → WeeklyPlanReviewCard → Progress → Scans left → FLI. Exact order can follow “information hierarchy” above.  
6. **Scans left card:** Reduce content to title + one line usage + Upgrade when low + Refresh/Restore as secondary. Optionally move “Protein left today” and goals into the Today hero so Scans left is only about quota.  
7. **Replace** hardcoded colors and key spacing in the home block with token references. Add a `homeSectionGap` style (e.g. `marginBottom: spacing.section`) and apply between major sections.  
8. **FLI:** When you touch it, use tokens and one primary CTA; reduce nesting.

**Styles**  
- Add or extend StyleSheet in App.js: e.g. `heroCard: { backgroundColor: colors.surface.card, borderRadius: radius.xxl, padding: spacing.xl, borderWidth: 1, borderColor: colors.surface.cardBorder, ...shadows.sm }`, `sectionGap: { marginBottom: spacing.section }`.  
- Use `heroCard` for the Today hero; use `sectionGap` between Goal Coach cards and other major blocks.  
- Launcher card: use tokens for background, border, radius, padding, and text colors.

**Data flow**  
- Today hero and DailyCoachCard both need `goalCoachDaily`, `remainingToday`. No new API. Refetch `goalCoachDaily` after scan/check-in as today so the hero and daily card stay in sync.  
- Primary CTA: when `goalPlan` and `getDailyActions(goalCoachDaily).primaryAction` exist, use that label and `handleGoalCoachAction`; otherwise “Scan meal” and open camera for meal.

---

## 9. Recommended implementation priority

**Phase 1 — Hero and unblock (biggest impact)**  
1. Add **HomeTodayHero** component and render it after the header with `remainingToday`, `goalCoachDaily`, and one primary CTA.  
2. **Break** the Goal Coach wrapper: remove the single card that wraps all Goal Coach content; render GoalPlanCard, JourneyCard, DailyCoachCard, WeeklyPlanReviewCard, Progress, and banners as **separate** cards with `marginBottom: spacing.section`.  
3. **Reorder** so DailyCoachCard (today’s progress) appears **right after** the launcher (or right after Smart Alerts if you keep Smart Alerts above Goal Coach).  
4. **Apply** design tokens to the Today hero and to the new section spacing (e.g. import tokens in App.js and use them for the new/updated styles).  
- **Outcome:** First screen has a clear “today” hero and one primary CTA; Goal Coach no longer feels like one cramped box; daily progress is visible early.

**Phase 2 — Launcher and spacing**  
5. **Simplify** the launcher: keep Scan Food as hero; make Scan Menu and Best Nearby one row; Smart Alerts and Goal Coach as one row of links or compact tiles. Shorten helper text.  
6. **Apply** tokens to the launcher card (background, border, radius, typography).  
7. **Standardize** spacing between all home sections (e.g. `spacing.section` between cards).  
- **Outcome:** Launcher is cleaner and clearly secondary to the hero; rhythm is consistent.

**Phase 3 — Scans left and FLI**  
8. **Compact** Scans left card; move or duplicate “protein left” into Today hero if desired. Use tokens.  
9. **Simplify** FLI card: one primary CTA, tokens, less nesting.  
- **Outcome:** Supporting blocks feel lighter; hero and daily stay the focus.

**Phase 4 — Reward and polish**  
10. **Add** streak chips and win_line to DailyCoachCard (or to Today hero as one line). Use success color and tokens.  
11. **Replace** remaining hardcoded colors and spacing in the home block with tokens.  
12. **Final pass:** Typography hierarchy (hero numbers, card titles, muted tertiary), tap targets, and shadow on the hero card.  
- **Outcome:** Reward and momentum visible; full tokenization and premium polish on home.

Implementing **Phase 1** first will give the largest perceived upgrade (hero + unblocked Goal Coach + daily progress position). Then Phase 2 for launcher and spacing, then 3 and 4 for supporting cards and polish. This can all be built inside the current CalorieClick.ai app with existing data and handlers.

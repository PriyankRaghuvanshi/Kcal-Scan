# Scan Result / Meal Analysis – Premium Redesign

Product goals: make the result screen the **hero** of the app; **2–3 second** comprehension; **luxurious dark** UI; **no feature removal**—only presentation, hierarchy, and premium UX.

---

## 1. Critique of the current Scan Result screen

- **Single dense card:** The entire result lives inside one `View` with `marginTop: 14` and many sibling blocks (`marginTop: 10`). Image, totals, confidence, candidates, clarification, QA, micros, powder, items, coaching, disclaimer—all compete in one scroll. No clear “above the fold” vs “detail.”
- **No hero:** The photo is a flat `preview` (220px, 16px radius) with no treatment (no overlay, no meal label, no quality badge). Totals are two lines (`styles.big` + `styles.p`) immediately below with no card or emphasis. The eye has no single anchor.
- **Weak hierarchy:** “Total: X kcal” and “Protein Xg • Carbs Xg • Fat Xg” have similar weight to “Scan confidence,” “Top candidates,” “Items,” “Coaching insights.” Section titles (`cardTitle`) are consistent but sections are not grouped into visual zones (hero / summary / breakdown / insights / actions).
- **Too many boxes:** Scan confidence (bar + text), Top candidates (3 rows), clarifying_question, clarification_questions, Meal QA, Micronutrients, Powder chips, Items list, then 6+ Meter blocks and messages. Each feels like another “panel” with no rhythm or consolidation.
- **Goal-fit missing:** There is no explicit “good / okay / weak for your goal” or “fits your day” line. `remainingToday` exists in the app but is not surfaced here, so the result feels informative but not **actionably** judged.
- **Coaching buried:** Satiety, Protein BV, Leucine, Glycemic load, UPF are each a full `Meter` (label, value, help text, bar). Valuable but heavy; no single “AI insight” or “best takeaway” that the user sees first.
- **Clarification and actions mixed in:** Clarification questions sit between QA and micros; “Apply and update kcal” is one of many buttons. “Clear current scan” and “Analyze” sit above the result; no clear primary CTA (e.g. “Looks good” / “Save to day”) after the result.
- **Text fatigue:** Many `styles.p` and `styles.tiny` blocks, disclaimer + sources at the bottom. Feels like a report, not a reward.
- **Visual tone:** Dark but not luxurious—flat backgrounds (#111, #0f0f0f), hard borders (#161616, #1c1c1c). No elevation, no soft separation, no “premium” card rhythm.

---

## 2. Redesign goals

1. **Hero in 2–3 seconds:** One clear hero (image + one-line meal label + total kcal + quality badge) so the user immediately knows “what was detected” and “how it fits.”
2. **Strict hierarchy:** Hero → Macro summary (calories + P/C/F in one card) → Goal-fit line → Item breakdown → Advanced/coaching (collapsible or single card) → Clarification (if any) → Actions.
3. **Premium feel:** Near-black base, large rounded cards, generous spacing, one accent (e.g. green for good, amber for caution), no competing boxes.
4. **Single “AI insight”:** One prominent line or card for the best takeaway (e.g. satiety, protein quality, or “one thing to know”) instead of six equal meters first.
5. **Clear CTAs:** One primary (e.g. “Save to day” or “Looks good”) and secondary (Improve / Clarify / Rerun) grouped at the bottom.
6. **Preserve everything:** All data (confidence, candidates, QA, micros, powder, items, all meters, disclaimer) remains available; some move into “Details” or “Advanced” to reduce upfront density.
7. **Emotional reward:** The screen should feel like a “win”—clear result, clear verdict, clear next step—not a form.

---

## 3. New information hierarchy

| Order | Zone | Content | Purpose |
|-------|------|---------|--------|
| 1 | **Hero** | Photo + meal label (e.g. “Oatmeal, eggs”) + total kcal + quality badge (Good / Okay / Weak) | Instant recognition and verdict |
| 2 | **Macro summary** | One card: Calories (large) + P / C / F (row or compact grid) | Core numbers at a glance |
| 3 | **Goal-fit line** | One line: “Fits your day” / “Within protein goal” / “Over calorie target” using `remainingToday` or meal_qa | Connects to user’s goal |
| 4 | **AI insight** | One card: best insight (e.g. “High satiety” or “Strong protein quality” or meal_qa one_tap_fixes headline) | Single takeaway |
| 5 | **Food breakdown** | Card: “What we detected” – list of items (name, grams, kcal) | Transparency without clutter |
| 6 | **Clarification** | If present: one card “Improve accuracy” with questions + Apply | Only when needed |
| 7 | **Advanced** | One card “Details” (expandable or scroll): confidence, top candidates, micronutrients, powder, full coaching meters, QA issues | For users who want depth |
| 8 | **Actions** | Primary CTA + secondary (Improve meal, Clear, etc.) | Clear next step |
| 9 | **Legal** | Disclaimer + sources (small, bottom) | Compliance without prominence |

---

## 4. Card-by-card redesign plan

### 4.1 Food image + meal recognition hero

- **Current:** `Image` (preview) 220px, then buttons; no meal label on image.
- **Redesign:**
  - **Hero block:** Full-width image with fixed aspect ratio (e.g. 4:3 or 16:10), large radius (20–24), soft shadow or subtle border. Overlay at bottom: gradient (transparent → near-black) so text is readable.
  - **On overlay:** One line meal label (e.g. from `top_candidates[0].label` or concatenated item names, max ~40 chars). Below that: **Total kcal** in large type (e.g. 28–32px, bold). No “Total:” prefix on hero—just the number + “kcal.”
  - **Quality badge:** Pill on top-right of image (or below image): “Good” (green) / “Okay” (amber) / “Weak” (red/muted) derived from meal_qa.qa_score or satiety + protein BV + UPF. If no data, hide or show “—”.
  - **Merge:** Image and meal + kcal + badge are one visual “hero card”; no separate card for image then another for totals.

### 4.2 Total calories / protein / carbs / fat summary

- **Current:** Two lines of text under hero (`styles.big` + `styles.p`).
- **Redesign:**
  - **One card** (e.g. “Nutrition” or no title): Calories as the main number (optional repeat if not on hero, or only P/C/F here). Row of four chips or columns: **Cal** (number) | **P** (g) | **C** (g) | **F** (g). Use design tokens (e.g. `colors.surface.card`, `radius.xl`). Typography: one size for value, smaller for unit/label. No extra text (“Protein”, “Carbs” can be abbreviated).
  - **Placement:** Directly below hero with consistent vertical spacing (e.g. 16–20px).

### 4.3 Meal quality / goal-fit summary

- **Current:** Not present as a single line.
- **Redesign:**
  - **One line or mini card:** e.g. “Fits your day” (green) when meal is within remaining kcal/protein; “Over calorie target” (amber) when over; “Great for protein” when high protein and under goal. Use `remainingToday` and meal totals. If no remaining data, use only meal_qa or satiety/UPF as fallback.
  - **Tone:** Short, factual, one sentence. No extra paragraph.

### 4.4 Food item breakdown list

- **Current:** “Items” title then `itemRow` for each (name + grams • kcal). Border between rows.
- **Redesign:**
  - **Card title:** “What we detected” or “Items”.
  - **List:** Same data, but: more padding per row, optional subtle divider (lighter than current #161616), optional leading dot or icon. Consider first item slightly emphasized (e.g. larger name) if it’s the “main” candidate. Keep itemName / itemMeta semantics; increase spacing (e.g. 12px vertical between rows).
  - **No new features:** Same items, same order; only visual cleanup.

### 4.5 Advanced metrics / coaching insights area

- **Current:** Six Meter components + coaching.messages list; locked box when no Pro.
- **Redesign:**
  - **Single “AI insight” card (above the fold):** Pick the single most valuable insight: e.g. “Satiety: 78/100 – filling meal” or “Protein quality: high” or first message from coaching.messages. One or two lines max. This is the only coaching content visible by default if we want to reduce density.
  - **“Details” or “Advanced” card:** Contains: Scan confidence (bar + %), Top candidates (compact), Micronutrients (one line), Powder confirmation (if any), then all Meters (Satiety, Protein BV, Leucine, GL, UPF) and full messages. Can be **collapsible** (e.g. “Show details” tap to expand) so the default view is one insight card + optional expand.
  - **Locked state:** Keep locked box for non-Pro; style it as one card with lock icon and upgrade CTA, not inline with meters.
  - **Meters:** When expanded, keep current Meter component but with consistent card background and spacing (e.g. 8px between meters).

### 4.6 Clarification questions / better-accuracy prompts

- **Current:** “Confirm for better accuracy” (single) and “Confirm details (we'll remember)” (multi) as two blocks with chips and “Apply and update kcal.”
- **Redesign:**
  - **One card** when any clarification exists: title “Improve accuracy” or “Quick confirm”. Single question: same chip row. Multi questions: stack vertically with one chip row per question; single **Apply** button at bottom of card. Style chips with border + fill when selected (already partially there); use design token radius and colors.
  - **Placement:** After “What we detected” and before “Details”; after “AI insight” so flow is: hero → macros → goal-fit → insight → items → clarify → details → actions.

### 4.7 Action buttons / rerun / improve meal flow

- **Current:** “Open Camera”, “Analyze” above result; “Clear current scan” below; “Apply and update kcal” inside clarification; QA one_tap_fixes as chips inside Meal QA block.
- **Redesign:**
  - **Primary CTA:** One clear action after result: e.g. “Save to day” or “Looks good” (if save is automatic, then “Done” or “Scan another”). Full-width, prominent (e.g. `colors.success.primary`), 44–48px height, large radius.
  - **Secondary row:** “Improve meal” (opens edit/rerun or clarification if needed), “Clear scan”. Secondary style (outline or muted). Optional: “Scan another” as text link.
  - **Rerun/Apply:** Keep “Apply and update kcal” inside clarification card; keep QA one_tap_fixes in Details or in a small “Quick fixes” chip row under AI insight when present. No removal of flows—only grouping and one primary CTA at bottom.

### 4.8 “What next” AI recommendation area

- **Current:** coaching.messages and multiple meters; no single “what to do next.”
- **Redesign:**
  - **Option A:** Use the single “AI insight” card to include a “Next” line when available (e.g. from meal_qa.one_tap_fixes or first coaching message). E.g. “Consider adding a portion of vegetables to boost fiber.”
  - **Option B:** Small “Tip” or “Next” card below AI insight: one sentence from backend (if we add a dedicated field) or from first relevant message. Only one line; no list.
  - Implementation: Reuse existing coaching.messages or meal_qa; no new backend contract required. Pick first message or first fix as the “one thing.”

---

## 5. Typography and spacing strategy

- **Use design tokens** from `designTokens.js`: `typography`, `spacing`, `radius`.
- **Hierarchy:**
  - **Hero kcal:** `typography.hero` or 28–32px, `weight.extrabold`, `colors.text.primary`.
  - **Section titles:** `typography.lg` or `xxl`, `weight.extrabold`, letterSpacing 0.2.
  - **Body / labels:** `typography.md` or `base`, `weight.medium` / `semibold`.
  - **Secondary (meta, units):** `typography.sm`, `colors.text.muted`.
- **Spacing:**
  - Between major zones: `spacing.section` or `spacing.xxl` (24–28px).
  - Between cards: `spacing.lg` to `spacing.xl` (16–20px).
  - Inside cards: `spacing.base` to `spacing.lg` (12–16px).
  - Avoid ad-hoc `marginTop: 10`; use a consistent scale (e.g. 8, 12, 16, 24).
- **Cards:** `paddingVertical: spacing.lg`, `paddingHorizontal: spacing.lg`, `borderRadius: radius.xl` (16), `backgroundColor: colors.surface.card`, `borderWidth: 1`, `borderColor: colors.surface.cardBorder`. Optional soft shadow from `shadows.md` for hero only.

---

## 6. Color / accent strategy

- **Background:** `colors.surface.primary` (#0a0f18) or near-black for the screen; cards `colors.surface.card` (#060e1c).
- **Text:** `colors.text.primary` (headings), `colors.text.secondary` (body), `colors.text.muted` (meta, hints).
- **Accent – quality and actions:**
  - **Good / success:** `colors.success.primary` (#22c55e), badge bg `colors.success.bg`.
  - **Okay / caution:** `colors.amber.primary` / `colors.amber.text`.
  - **Weak / warning:** `colors.warning.primary` or muted red; use sparingly.
- **Borders:** `colors.surface.cardBorder` (#1a2642); avoid pure black borders.
- **Primary CTA:** `colors.success.primary` background, `colors.text.inverse` text.
- **Secondary buttons:** Outline with `colors.surface.cardBorder` or muted fill.
- **No new palette:** Stay within existing tokens so the app stays consistent.

---

## 7. React Native implementation plan

1. **Extract a dedicated component** (e.g. `ScanResultScreen.js` or `MealAnalysisResult.js`) that receives `result`, `photoUri`, `coaching`, `remainingToday`, `canCoaching`, and handlers (rerun, applyClarification, clearScan, openPaywall, etc.). The existing `result ? ( ... )` block in `App.js` becomes a single `<ScanResultScreen ... />` so the file stays maintainable.
2. **Structure the component** into subviews matching the hierarchy:
   - `ScanResultHero` (image + overlay meal label + kcal + quality badge)
   - `ScanResultMacroCard` (P/C/F + optional Cal)
   - `ScanResultGoalFit` (one line from remainingToday / meal_qa)
   - `ScanResultInsightCard` (one AI takeaway; optional “Details” expandable)
   - `ScanResultItemsCard` (list of items)
   - `ScanResultClarificationCard` (if clarification_questions or clarifying_question)
   - `ScanResultDetailsCard` (expandable: confidence, candidates, micros, powder, meters, QA)
   - `ScanResultActions` (primary CTA + secondary)
   - Footer: disclaimer + sources (small)
3. **Quality badge logic:** Add a small helper `getMealQualityBadge(result, coaching)` → `{ label: 'Good'|'Okay'|'Weak', color }` from qa_score or satiety + protein_bv + UPF thresholds. No backend change.
4. **Goal-fit line:** Add `getGoalFitLine(result, remainingToday)` → string and optional tone (success/amber/warning). Use existing `remainingToday` and result totals.
5. **Styling:** Import `colors`, `spacing`, `radius`, `typography`, `shadows` from `designTokens.js`. Use StyleSheet; avoid inline magic numbers. Use marginBottom (or a wrapper with marginBottom) between sections instead of marginTop to avoid drift.
6. **No gap in layout:** Use `marginBottom` / `marginTop` on wrapper Views for vertical rhythm (React Native compatibility).
7. **ScrollView:** Wrap the entire result content in one ScrollView so the hero can be at top and actions at bottom; keyboard-aware if clarification has focus.
8. **Preserve all props and handlers:** Pass through rerunBusy, clarificationSelections, applyClarificationAnswers, applyClarifyingAnswer, applyQaFix, applyPowderConfirmation, etc. No change to business logic or API.

---

## 8. Updated component/code direction or example code structure

Suggested file: `mobile/components/ScanResultScreen.js` (or `MealAnalysisResult.js`).

```jsx
// ScanResultScreen.js – structure only; implement with your result/coaching shape.
// Use round1 and num from App.js or a shared util (e.g. utils/numbers.js).
import React, { useState } from "react";
import { View, Text, Image, ScrollView, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function round1(x) {
  const n = num(x);
  return n != null ? Math.round(n * 10) / 10 : "—";
}

function getMealQualityBadge(result, coaching) {
  const qa = result?.meal_qa?.qa_score;
  if (qa != null) {
    if (qa >= 70) return { label: "Good", color: colors.success.primary };
    if (qa >= 45) return { label: "Okay", color: colors.amber.primary };
    return { label: "Weak", color: colors.warning.primary };
  }
  const sat = num(coaching?.satiety_score);
  const upf = num(coaching?.ultra_processed_score);
  if (sat >= 65 && upf < 5) return { label: "Good", color: colors.success.primary };
  if (sat >= 45 || upf < 7) return { label: "Okay", color: colors.amber.primary };
  return { label: "—", color: colors.text.muted };
}

function getGoalFitLine(result, remainingToday) {
  if (!result?.total_kcal || !remainingToday) return null;
  const kcal = num(result.total_kcal);
  const remKcal = num(remainingToday.kcal);
  const remP = num(remainingToday.protein_g);
  const p = num(result?.totals?.protein_g);
  if (remKcal !== null && kcal > remKcal) return { text: "Over calorie target", tone: "amber" };
  if (remP !== null && p !== null && p >= remP * 0.3) return { text: "Good for protein today", tone: "success" };
  if (remKcal !== null && remKcal > 0) return { text: "Fits your day", tone: "success" };
  return null;
}

export function ScanResultHero({ photoUri, result, coaching }) {
  const mealLabel = result?.top_candidates?.[0]?.label || (result?.items || []).map((i) => i?.name).filter(Boolean).slice(0, 2).join(", ") || "Meal";
  const kcal = result?.total_kcal != null ? Math.round(num(result.total_kcal)) : "—";
  const badge = getMealQualityBadge(result, coaching);
  return (
    <View style={styles.heroWrap}>
      <Image source={{ uri: photoUri }} style={styles.heroImage} />
      <View style={styles.heroOverlay}>
        <Text style={styles.heroMealLabel} numberOfLines={1}>{mealLabel}</Text>
        <Text style={styles.heroKcal}>{kcal} kcal</Text>
      </View>
      <View style={[styles.qualityBadge, { borderColor: badge.color }]}>
        <Text style={[styles.qualityBadgeText, { color: badge.color }]}>{badge.label}</Text>
      </View>
    </View>
  );
}

export function ScanResultMacroCard({ result }) {
  const t = result?.totals || {};
  return (
    <View style={styles.card}>
      <View style={styles.macroRow}>
        <View style={styles.macroItem}><Text style={styles.macroValue}>{round1(result?.total_kcal)}</Text><Text style={styles.macroUnit}>kcal</Text></View>
        <View style={styles.macroItem}><Text style={styles.macroValue}>{round1(t.protein_g)}</Text><Text style={styles.macroUnit}>P</Text></View>
        <View style={styles.macroItem}><Text style={styles.macroValue}>{round1(t.carbs_g)}</Text><Text style={styles.macroUnit}>C</Text></View>
        <View style={styles.macroItem}><Text style={styles.macroValue}>{round1(t.fat_g)}</Text><Text style={styles.macroUnit}>F</Text></View>
      </View>
    </View>
  );
}

export function ScanResultScreen({
  result,
  photoUri,
  coaching,
  remainingToday,
  canCoaching,
  rerunBusy,
  clarificationSelections,
  onApplyClarification,
  onClearScan,
  onOpenPaywall,
  postScanUpgradeBannerVisible,
  onDismissUpgradeBanner,
  childrenClarification,
  childrenDetails,
  primaryCtaLabel,
  onPrimaryCta,
}) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const goalFit = getGoalFitLine(result, remainingToday);
  const hasClarification = (result?.clarification_questions?.length > 0) || result?.clarifying_question?.ask;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {postScanUpgradeBannerVisible && (
        <View style={styles.upgradeBanner}>
          <Text style={styles.upgradeBannerText}>Get more scans + daily coaching — Upgrade</Text>
          <TouchableOpacity onPress={() => { onDismissUpgradeBanner(); onOpenPaywall(null); }}><Text style={styles.upgradeBannerBtn}>See plans</Text></TouchableOpacity>
          <TouchableOpacity onPress={onDismissUpgradeBanner}><Text style={styles.upgradeBannerClose}>✕</Text></TouchableOpacity>
        </View>
      )}

      <ScanResultHero photoUri={photoUri} result={result} coaching={coaching} />
      <View style={styles.section}>
        <ScanResultMacroCard result={result} />
      </View>
      {goalFit && (
        <View style={styles.section}>
          <Text style={[styles.goalFitText, goalFit.tone === "success" && styles.goalFitSuccess, goalFit.tone === "amber" && styles.goalFitAmber]}>{goalFit.text}</Text>
        </View>
      )}

      {/* AI insight: one card with best takeaway */}
      {canCoaching && coaching && (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>AI insight</Text>
            <Text style={styles.insightBody}>
              {coaching.messages?.[0] || `Satiety ${round1(coaching.satiety_score)}/100 · Protein quality ${round1(coaching.protein_bv_score)}/100`}
            </Text>
          </View>
        </View>
      )}

      {/* Items */}
      <View style={styles.section}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>What we detected</Text>
          {(result?.items || []).map((it, idx) => (
            <View key={idx} style={styles.itemRow}>
              <Text style={styles.itemName}>{it.name}</Text>
              <Text style={styles.itemMeta}>{round1(it.grams)}g · {round1(it.kcal)} kcal</Text>
            </View>
          ))}
        </View>
      </View>

      {hasClarification && <View style={styles.section}>{childrenClarification}</View>}

      {/* Expandable details */}
      <View style={styles.section}>
        <TouchableOpacity style={styles.detailsToggle} onPress={() => setDetailsExpanded((e) => !e)}>
          <Text style={styles.detailsToggleText}>{detailsExpanded ? "Hide details" : "Show details"}</Text>
        </TouchableOpacity>
        {detailsExpanded && childrenDetails}
      </View>

      <View style={styles.section}>
        <TouchableOpacity style={styles.primaryCta} onPress={onPrimaryCta} disabled={rerunBusy}>
          <Text style={styles.primaryCtaText}>{primaryCtaLabel || "Done"}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.secondaryCta} onPress={onClearScan} disabled={rerunBusy}>
          <Text style={styles.secondaryCtaText}>Clear scan</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.disclaimer}>{/* HEALTH_DISCLAIMER */}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: spacing.section * 2 },
  section: { marginBottom: spacing.xl },
  card: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  heroWrap: { position: "relative", marginBottom: spacing.lg, borderRadius: radius.xl, overflow: "hidden", ...shadows.md },
  heroImage: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius.xl },
  heroOverlay: { position: "absolute", bottom: 0, left: 0, right: 0, padding: spacing.lg, backgroundColor: "rgba(0,0,0,0.6)" },
  heroMealLabel: { fontSize: typography.lg, fontWeight: typography.weight.semibold, color: colors.text.primary },
  heroKcal: { fontSize: 28, fontWeight: typography.weight.extrabold, color: colors.text.primary, marginTop: spacing.xs },
  qualityBadge: { position: "absolute", top: spacing.base, right: spacing.base, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm, borderRadius: radius.pill, borderWidth: 1 },
  qualityBadgeText: { fontSize: typography.sm, fontWeight: typography.weight.bold },
  macroRow: { flexDirection: "row", justifyContent: "space-between" },
  macroItem: { alignItems: "center" },
  macroValue: { fontSize: typography.xl, fontWeight: typography.weight.bold, color: colors.text.primary },
  macroUnit: { fontSize: typography.sm, color: colors.text.muted },
  goalFitText: { fontSize: typography.md, fontWeight: typography.weight.semibold },
  goalFitSuccess: { color: colors.success.text },
  goalFitAmber: { color: colors.amber.text },
  cardTitle: { fontSize: typography.lg, fontWeight: typography.weight.extrabold, color: colors.text.primary, marginBottom: spacing.base },
  insightBody: { fontSize: typography.md, color: colors.text.secondary, lineHeight: 22 },
  itemRow: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.surface.cardBorder },
  itemName: { fontSize: typography.md, fontWeight: typography.weight.semibold, color: colors.text.primary },
  itemMeta: { fontSize: typography.sm, color: colors.text.muted, marginTop: spacing.xs },
  detailsToggle: { paddingVertical: spacing.base },
  detailsToggleText: { fontSize: typography.sm, color: colors.accent.primary },
  primaryCta: { backgroundColor: colors.success.primary, borderRadius: radius.lg, paddingVertical: spacing.lg, alignItems: "center", marginBottom: spacing.base },
  primaryCtaText: { fontSize: typography.md, fontWeight: typography.weight.bold, color: colors.text.inverse },
  secondaryCta: { alignItems: "center", paddingVertical: spacing.base },
  secondaryCtaText: { fontSize: typography.sm, color: colors.text.muted },
  disclaimer: { fontSize: typography.xs, color: colors.text.muted, marginTop: spacing.lg },
  upgradeBanner: { flexDirection: "row", alignItems: "center", marginBottom: spacing.base, padding: spacing.base, backgroundColor: colors.surface.elevated, borderRadius: radius.lg },
  upgradeBannerText: { flex: 1, fontSize: typography.sm, color: colors.text.secondary },
  upgradeBannerBtn: { fontSize: typography.sm, color: colors.accent.primary, fontWeight: "600" },
  upgradeBannerClose: { marginLeft: spacing.sm, color: colors.text.muted },
});
```

**Integration in App.js:** Replace the block `{ result ? ( <View style={{ marginTop: 14 }}> ... </View> ) : null }` with:

```jsx
{result ? (
  <ScanResultScreen
    result={result}
    photoUri={photoUri}
    coaching={coaching}
    remainingToday={remainingToday}
    canCoaching={canCoaching}
    rerunBusy={rerunBusy}
    clarificationSelections={clarificationSelections}
    onApplyClarification={applyClarificationAnswers}
    onClearScan={clearCurrentScan}
    onOpenPaywall={openPaywall}
    postScanUpgradeBannerVisible={postScanUpgradeBannerVisible}
    onDismissUpgradeBanner={dismissPostScanBanner}
    primaryCtaLabel="Done"
    onPrimaryCta={() => {}}
    childrenClarification={/* existing clarification UI as a fragment or component */}
    childrenDetails={/* existing confidence, candidates, micros, powder, Meter list, QA */}
  />
) : null}
```

Implement `childrenClarification` and `childrenDetails` by moving the current JSX for clarification and for the “Details” content (confidence, candidates, micros, powder, meters, QA, disclaimer/sources) into two render props or subcomponents. This keeps all existing behavior while giving a single place to refine layout and styles.

---

**Summary:** The redesign is **presentation-only**: same data, same handlers, new hierarchy (hero → macros → goal-fit → one AI insight → items → clarification → expandable details → actions), new card rhythm and tokens, and one primary CTA. Implementing it as a dedicated `ScanResultScreen` (or `MealAnalysisResult`) component with the structure above will make the scan result feel like the hero of the app and understandable in 2–3 seconds while preserving every current feature.

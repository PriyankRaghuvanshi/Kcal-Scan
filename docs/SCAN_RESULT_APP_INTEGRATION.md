# Scan Result – App.js integration

## 1. Import (already added)

```js
import { ScanResultScreen } from "./components/ScanResultScreen";
```

## 2. Replace the `result ? (...)` block

**Find** the block that starts with:

```js
{result ? (
  <View style={{ marginTop: 14 }}>
```

and ends with:

```js
            </View>
          ) : null}
```

**Replace the entire block** with the snippet below. This keeps all existing business logic (clarification, details, coaching, disclaimer) by passing them as `childrenClarification` and `childrenDetails`.

---

## Exact replacement snippet

```js
{result ? (
  <View style={{ marginTop: 14 }}>
    <ScanResultScreen
      result={result}
      photoUri={photoUri}
      coaching={coaching}
      remainingToday={remainingToday}
      canCoaching={canCoaching}
      rerunBusy={rerunBusy}
      clarificationSelections={clarificationSelections}
      onClearScan={clearCurrentScan}
      onOpenPaywall={openPaywall}
      postScanUpgradeBannerVisible={postScanUpgradeBannerVisible}
      onDismissUpgradeBanner={dismissPostScanBanner}
      primaryCtaLabel="Done"
      onPrimaryCta={() => {}}
      disclaimerText={HEALTH_DISCLAIMER}
      disclaimerSources={HEALTH_SOURCES}
      onOpenSourceLink={openURLSafe}
      childrenClarification={(
        <>
          {result?.clarifying_question?.ask ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Confirm for better accuracy</Text>
              <Text style={styles.p}>{String(result?.clarifying_question?.ask || "")}</Text>
              <View style={styles.rowWrap}>
                {(result?.clarifying_question?.options || []).slice(0, 6).map((opt, idx) => (
                  <TouchableOpacity
                    key={String(opt) + "-" + idx}
                    style={styles.chip}
                    onPress={() => applyClarifyingAnswer(opt)}
                    disabled={rerunBusy}
                  >
                    <Text style={styles.chipText}>{String(opt)}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ) : null}
          {(result?.clarification_questions || []).length > 0 ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Confirm details (we'll remember)</Text>
              {(result.clarification_questions || []).map((q, qIdx) => (
                <View key={q.key || qIdx} style={{ marginTop: 8 }}>
                  <Text style={styles.p}>{q.label}</Text>
                  <View style={styles.rowWrap}>
                    {(q.options || []).map((opt, idx) => (
                      <TouchableOpacity
                        key={(q.key || "") + "-" + idx}
                        style={[styles.chip, clarificationSelections[q.key] === opt ? { borderColor: "#22c55e", borderWidth: 2 } : null]}
                        onPress={() => setClarificationSelections((prev) => ({ ...prev, [q.key]: opt }))}
                        disabled={rerunBusy}
                      >
                        <Text style={styles.chipText}>{String(opt)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ))}
              <TouchableOpacity
                style={[styles.primaryBtn, { marginTop: 10 }]}
                onPress={() => applyClarificationAnswers()}
                disabled={rerunBusy || !Object.keys(clarificationSelections).some((k) => clarificationSelections[k])}
              >
                <Text style={styles.btnText}>Apply and update kcal</Text>
              </TouchableOpacity>
            </View>
          ) : null}
        </>
      )}
      childrenDetails={(
        <>
          {result?.vision_confidence != null ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Scan confidence</Text>
              <Text style={styles.p}>
                {Math.round(Math.max(0, Math.min(1, num(result?.vision_confidence))) * 100)}% •{" "}
                {Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.82
                  ? "High"
                  : Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.72
                  ? "Medium"
                  : "Low"}
              </Text>
              <View style={styles.barOuter}>
                <View
                  style={[
                    styles.barFill,
                    {
                      width: String(Math.round(Math.max(0, Math.min(1, num(result?.vision_confidence))) * 100)) + "%",
                      backgroundColor:
                        Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.82
                          ? "#22c55e"
                          : Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.72
                          ? "#f59e0b"
                          : "#ef4444",
                    },
                  ]}
                />
              </View>
            </View>
          ) : null}
          {(result?.top_candidates || []).length ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Top candidates</Text>
              {(result.top_candidates || []).slice(0, 3).map((c, idx) => (
                <View key={(c?.candidate_id != null ? c.candidate_id : idx)} style={styles.itemRow}>
                  <Text style={styles.itemName}>{String(c?.label || "")}</Text>
                  <Text style={styles.itemMeta}>
                    {Math.round(Math.max(0, Math.min(1, num(c?.confidence))) * 100)}% confidence • portion{" "}
                    {round1(c?.portion_guess_g)}g
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {result?.meal_qa ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Meal QA</Text>
              <Text style={styles.p}>Quality score: {round1(result?.meal_qa?.qa_score)}/100</Text>
              {(result?.meal_qa?.issues || []).slice(0, 3).map((iss, idx) => (
                <Text key={"qa-issue-" + idx} style={styles.tiny}>
                  • {String(iss?.message || "")}
                </Text>
              ))}
              {(result?.meal_qa?.one_tap_fixes || []).length ? (
                <View style={styles.rowWrap}>
                  {(result?.meal_qa?.one_tap_fixes || []).slice(0, 3).map((fix, idx) => (
                    <TouchableOpacity
                      key={"fix-" + idx}
                      style={styles.chip}
                      onPress={() => applyQaFix(fix)}
                      disabled={rerunBusy}
                    >
                      <Text style={styles.chipText}>{String(fix?.label || "Apply fix")}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              ) : null}
            </View>
          ) : null}
          {result?.micros ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.cardTitle}>Micronutrients</Text>
              <Text style={styles.p}>
                Fiber {round1(result.micros.fiber_g ?? result.micros.fiber)}g • Vit D {round1(result.micros.vitamin_d_ug ?? result.micros.vitamin_d_mcg)}µg • B12{" "}
                {round1(result.micros.vitamin_b12_ug ?? result.micros.vitamin_b12_mcg)}µg
              </Text>
              <Text style={styles.p}>
                Iron {round1(result.micros.iron_mg)}mg • Magnesium {round1(result.micros.magnesium_mg)}mg
              </Text>
            </View>
          ) : null}
          {(Array.isArray(result?.items) ? result.items : [])
            .filter((it) => it && typeof it === "object" && it?._powder_meta?.is_powder_like)
            .slice(0, 1)
            .map((it) => {
              const meta = it._powder_meta || {};
              const conf = meta.powder_confirmation || {};
              const needs = Boolean(meta.needs_powder_confirmation);
              const resolved = String(meta.powder_type_resolved || "").trim();
              const itemId = String(it.item_id || "").trim();
              const scoopG = Math.round(num(it.grams));
              return (
                <ScanConfirmationChips
                  key={"powder-confirm-" + itemId}
                  title={needs ? "Confirm powder type + scoop" : "Powder detected (optional confirm)"}
                  powderTypes={conf.powder_types || ["whey", "whey_isolate", "plant_protein", "mass_gainer", "cocoa_powder", "other_powder"]}
                  scoopSizesG={conf.scoop_sizes_g || [25, 30, 40]}
                  selectedPowderType={resolved}
                  selectedScoopG={scoopG || 30}
                  disabled={rerunBusy}
                  onSelectPowderType={(pt) => applyPowderConfirmation(itemId, pt, scoopG || 30)}
                  onSelectScoopG={(g) => applyPowderConfirmation(itemId, resolved || "whey", g)}
                />
              );
            })}
          <Text style={[styles.cardTitle, { marginTop: 12 }]}>Coaching insights</Text>
          {!canCoaching ? (
            <View style={styles.lockedBox}>
              <Text style={styles.lockedTitle}>Locked 🔒</Text>
              <Text style={styles.p}>
                Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.
              </Text>
              <Text style={styles.tiny}>Upgrade to Pro or Infinite to unlock these insights.</Text>
            </View>
          ) : coaching ? (
            <View style={{ marginTop: 8 }}>
              <Meter
                label="Satiety Score"
                value={coaching.satiety_score}
                max={100}
                help={coaching?.layman_terms?.satiety || "How filling this meal is."}
              />
              <Meter
                label="Protein Bioavailability"
                value={coaching.protein_bv_score}
                max={100}
                help={coaching?.layman_terms?.protein_bv || "How well your body can use the protein."}
              />
              <View style={styles.meter}>
                <View style={styles.meterTop}>
                  <Text style={styles.meterLabel}>Leucine estimate</Text>
                  <Text style={styles.meterValue}>{round1(coaching.leucine_estimate_g)}g</Text>
                </View>
                <Text style={styles.meterHelp}>
                  {coaching?.layman_terms?.leucine || "Key amino acid that helps switch on muscle-building."}
                </Text>
                <Text style={styles.tiny}>
                  MPS trigger: {round1(coaching.mps_threshold_g)}g •{" "}
                  {coaching.mps_triggered ? "✅ Triggered" : "❌ Not yet"}
                </Text>
              </View>
              <View style={styles.meter}>
                <View style={styles.meterTop}>
                  <Text style={styles.meterLabel}>Glycemic load</Text>
                  <Text style={styles.meterValue}>
                    {round1(coaching?.glycemic_load?.gl)} ({coaching?.glycemic_load?.level || "-"})
                  </Text>
                </View>
                <Text style={styles.meterHelp}>
                  {coaching?.layman_terms?.glycemic_load || "Sugar-spike risk from carbs."}
                </Text>
              </View>
              <View style={styles.meter}>
                <View style={styles.meterTop}>
                  <Text style={styles.meterLabel}>Ultra-processed score</Text>
                  <Text style={styles.meterValue}>{round1(coaching.ultra_processed_score)}/10</Text>
                </View>
                <Text style={styles.meterHelp}>
                  {coaching?.layman_terms?.ultra_processed || "How processed the food is."}
                </Text>
              </View>
              {(coaching.messages || []).length ? (
                <View style={{ marginTop: 10 }}>
                  {(coaching.messages || []).map((m, i) => (
                    <Text key={i} style={styles.p}>
                      • {m}
                    </Text>
                  ))}
                </View>
              ) : null}
            </View>
          ) : locked ? (
            <View style={styles.lockedBox}>
              <Text style={styles.lockedTitle}>Locked 🔒</Text>
              <Text style={styles.p}>Upgrade to Pro to unlock coaching insights.</Text>
            </View>
          ) : (
            <Text style={styles.tiny}>No coaching data returned.</Text>
          )}
        </>
      )}
    />
  </View>
) : null}
```

---

## 3. Helper functions

All helpers live in `ScanResultScreen.js` and are used internally:

- `num`, `round1` – safe number/rounding
- `getMealQualityBadge(result, coaching)` – Good/Okay/Weak/—
- `getGoalFitLine(result, remainingToday)` – goal-fit line or null

No extra helpers are required in App.js; `num` and `round1` are still used in the `childrenDetails` / `childrenClarification` JSX that stays in App.js.

---

## 4. Safe fallback behavior (missing result fields)

| Area | When data missing | Behavior |
|------|--------------------|----------|
| **Hero** | No `photoUri` | Placeholder view (no image). |
| **Hero** | No `top_candidates` / no `items` | Meal label falls back to `"Meal"`. |
| **Hero** | No `result.total_kcal` | Shows `"—"` for kcal. |
| **Quality badge** | No `meal_qa.qa_score`, no coaching satiety/ultra_processed | Badge shows `"—"` (muted). |
| **Goal-fit line** | No `result.total_kcal` or no `remainingToday` | Line not rendered. |
| **Macro card** | No `result.totals` / `total_kcal` | Uses `round1`/`num`; shows `"—"` where needed. |
| **Insight card** | No `coaching` | Section not rendered (only when `canCoaching \|\| result?.locked`). |
| **Items card** | `items` empty or not array | Returns null; section still has wrapper but no list. |
| **Clarification** | No `clarification_questions` and no `clarifying_question.ask` | Clarification card not rendered. |
| **Details** | `childrenDetails` not passed | "Show details" card not rendered. |
| **Disclaimer** | No `disclaimerText` | Disclaimer block not rendered. |
| **Sources** | No `disclaimerSources` or no `onOpenSourceLink` | Only disclaimer text shown. |

All handlers (`applyClarificationAnswers`, `setClarificationSelections`, `applyClarifyingAnswer`, `clearCurrentScan`, `dismissPostScanBanner`, `openPaywall`, `applyQaFix`, `applyPowderConfirmation`, `openURLSafe`) are unchanged and passed either as props or used inside the `childrenClarification` / `childrenDetails` JSX in App.js.

/**
 * RecommendationCard – Unified premium card for Healthy Nearby, Smart Alerts, map bottom.
 * Token-driven, Figma-friendly. Supports strong / estimated / weak variants.
 */

import React from "react";
import { View, Text, TouchableOpacity, Linking, Image, StyleSheet } from "react-native";
import { PressableScale } from "./PressableScale";
import { colors, spacing, radius, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";
import { ConfidenceBadge, inferConfidenceTier } from "./ConfidenceBadge";
import { shouldShowMenuMayVary } from "../smartAlertTrustLabels";
import { ScoreBadge } from "./ScoreBadge";
import { RecommendationMetaRow } from "./RecommendationMetaRow";
import { RecommendationActionRow } from "./RecommendationActionRow";
import { BestOrderEvidenceBlock } from "./BestOrderEvidence";

function extractSwapSuggestions(...sources) {
  const out = [];
  const seen = new Set();
  for (const src of sources) {
    if (!src || typeof src !== "object") continue;
    const swaps = Array.isArray(src?.swap_suggestions) ? src.swap_suggestions : [];
    swaps.forEach((row) => {
      const text = String(row || "").trim().replace(/\s+/g, " ");
      if (text && !seen.has(text.toLowerCase())) {
        seen.add(text.toLowerCase());
        out.push(text);
      }
    });
    const better = String(src?.swap_suggestion || src?.better_swap || "").trim();
    if (better && !seen.has(better.toLowerCase())) {
      seen.add(better.toLowerCase());
      out.push(better);
    }
  }
  return out.slice(0, 2);
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * Build "Your usual: X" pill content from the place.usual_meal payload.
 * Returns null if no usual yet (e.g. <2 prior visits at this place_id).
 */
function buildUsualMealPill(place, bestItemName) {
  const u = place?.usual_meal;
  if (!u || typeof u !== "object") return null;
  const name = String(u.item_name || "").trim();
  if (!name) return null;
  const kcal = Number.isFinite(Number(u.estimated_calories)) ? Math.round(Number(u.estimated_calories)) : null;
  const protein = Number.isFinite(Number(u.estimated_protein_g)) ? Math.round(Number(u.estimated_protein_g)) : null;
  const times = Number.isFinite(Number(u.times_chosen)) ? Number(u.times_chosen) : 0;
  const isSameAsTopPick = String(bestItemName || "").trim().toLowerCase() === name.toLowerCase();
  return {
    name,
    kcal,
    protein,
    times,
    isSameAsTopPick,
  };
}

/**
 * Detect whether the top item (or the place-level menu) confirms palm-oil
 * contents. Reads multiple possible signal locations; returns true/false/null.
 * null = unknown (do NOT claim either way).
 */
function detectPalmOil(place) {
  if (!place || typeof place !== "object") return null;
  const directCandidates = [
    place.contains_palm_oil,
    place?.top_menu_item?.contains_palm_oil,
  ];
  for (const v of directCandidates) {
    if (v === true) return true;
    if (v === false) return false;
  }
  const flagLists = [
    place.negative_flags,
    place?.top_menu_item?.negative_flags,
  ];
  for (const nf of flagLists) {
    if (!Array.isArray(nf)) continue;
    if (nf.includes("contains_palm_oil")) return true;
    if (nf.includes("palm_oil_free")) return false;
  }
  return null;
}

/**
 * Build two or three goal_variant pills for display: the highest-protein and
 * lowest-calorie (and fat-loss) picks from goal_variants, skipping any that
 * are the same as the primary bestItem or each other.
 */
function buildGoalVariantPills(place, bestItemName) {
  const gv = place?.goal_variants;
  if (!gv || typeof gv !== "object") return [];
  const norm = (s) => String(s || "").trim().toLowerCase();
  const primary = norm(bestItemName);
  const out = [];
  const seen = new Set();
  const add = (label, variant) => {
    if (!variant || typeof variant !== "object") return;
    const name = String(variant.item_name || "").trim();
    if (!name) return;
    const key = norm(name);
    if (key === primary || seen.has(key)) return;
    seen.add(key);
    const rawImg = String(variant.image_url || "").trim();
    out.push({
      label,
      name,
      kcal: Number.isFinite(Number(variant.estimated_calories)) ? Math.round(Number(variant.estimated_calories)) : null,
      protein: Number.isFinite(Number(variant.estimated_protein_g)) ? Math.round(Number(variant.estimated_protein_g)) : null,
      image: rawImg.startsWith("https://") ? rawImg : null,
    });
  };
  // Order: high protein, lowest cal, fat_loss (if distinct from both)
  add("High protein", gv.high_protein);
  add("Lowest cal", gv.lowest_calorie);
  add("Fat-loss", gv.fat_loss);
  return out.slice(0, 2);
}

/**
 * Infer card variant from place/candidate data.
 */
export function inferCardVariant(place) {
  const tier = inferConfidenceTier(place);
  if (tier === "verified" || tier === "chain_backed" || tier === "local_favorite")
    return "strong";
  if (tier === "estimated") return "estimated";
  return "weak";
}

/**
 * RecommendationCard – flexible recommendation display.
 *
 * @param {object} place – Place/candidate with best_item_name, display_rank_score_100, etc.
 * @param {string} heroLabel – e.g. "Best nearby right now", "Best fit for your goal"
 * @param {number} rankPosition – 1, 2, 3 for rank badges
 * @param {string} variant – "strong" | "estimated" | "weak" (or inferred from place)
 * @param {object} actions – { primaryLabel, onPrimary, secondaryLabel, onSecondary, primaryIcon }
 * @param {boolean} dark – Dark theme (default true for map/healthy)
 * @param {boolean} compact – Shorter layout for lists
 * @param {function} onPress – Optional card tap
 */
export function RecommendationCard({
  place,
  heroLabel,
  rankPosition,
  variant,
  actions = {},
  dark = true,
  compact = false,
  onPress,
  style,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
}) {
  if (!place || typeof place !== "object") return null;

  const isScreenshot = Boolean(screenshotMode);
  const name = String(place.place_name ?? place.name ?? "").trim() || "Restaurant";
  const score = num(place.display_rank_score_100) ?? num(place.health_score_100);
  const bestItem = String(place.best_item_name ?? place.best_order ?? "").trim();
  const calories = num(place.best_item_calories ?? place.estimated_calories);
  const protein = num(place.best_item_protein ?? place.estimated_protein_g);
  const reason = String(place.rank_reason_short ?? place.why_this_ranked_here ?? "").trim();
  const memoryLabel = String(place.personal_memory_label || "").trim();
  const hideMemory = !memoryLabel || memoryLabel === "Not enough data yet";

  const topItem = place.top_menu_item && typeof place.top_menu_item === "object" ? place.top_menu_item : null;
  const swaps = extractSwapSuggestions(topItem || place, place);
  const goalVariantPills = buildGoalVariantPills(place, bestItem);
  const palmOil = detectPalmOil(place);
  const usualMeal = buildUsualMealPill(place, bestItem);
  // Top-item thumbnail. Falls back gracefully when the Supabase column is
  // missing or the image URL doesn't resolve.
  const topItemImageRaw = String(
    (topItem && topItem.image_url) || place.best_item_image_url || ""
  ).trim();
  const topItemImage = topItemImageRaw.startsWith("https://") ? topItemImageRaw : null;

  const resolvedVariant = variant || inferCardVariant(place);
  const needsMenuCheck = shouldShowMenuMayVary(place);

  const isWeak = resolvedVariant === "weak";
  const textPrimary = dark ? colors.text.primary : colors.textLight.primary;
  const textMuted = dark ? colors.slate.text : colors.textLight.muted;
  const resolvedActions = isScreenshot
    ? { ...actions, secondaryLabel: undefined, onSecondary: undefined }
    : actions;

  const content = (
    <>
      {/* A. Place name + hero + score */}
      <View style={styles.header}>
        <Text style={[styles.name, { color: textPrimary }]} numberOfLines={2}>
          {name}
        </Text>
        <View style={styles.headerRight}>
          {heroLabel ? (
            <Text
              style={[
                styles.heroBadge,
                isWeak && styles.heroBadgeWeak,
                { color: isWeak ? textMuted : colors.success.text },
              ]}
              numberOfLines={1}
            >
              {heroLabel}
            </Text>
          ) : null}
          {Number.isFinite(score) && (
            <ScoreBadge score={score} isTop={rankPosition === 1} size={compact ? "sm" : "md"} />
          )}
        </View>
      </View>

      {/* B. Confidence badge */}
      <View style={styles.badgeRow}>
        <ConfidenceBadge place={place} />
      </View>

      {/* C. Best item + heuristic suggestion disclaimer for covered chains */}
      {bestItem ? (
        <View>
          <View style={styles.bestItemRow}>
            {topItemImage ? (
              <Image
                source={{ uri: topItemImage }}
                style={styles.bestItemThumb}
                resizeMode="cover"
                accessible
                accessibilityIgnoresInvertColors
              />
            ) : null}
            <View style={{ flex: topItemImage ? 1 : undefined }}>
              <Text
                style={[
                  styles.bestItem,
                  { color: textPrimary },
                ]}
                numberOfLines={2}
              >
                {bestItem}
              </Text>
              {num(place.protein_fill_pct) != null && place.protein_fill_pct > 0 ? (
                <Text style={styles.fitLabel}>
                  Fills {place.protein_fill_pct}% of protein gap
                  {num(place.calorie_use_pct) != null && place.calorie_use_pct <= 50
                    ? ` · ${place.calorie_use_pct}% of cal budget`
                    : num(place.calorie_use_pct) != null && place.calorie_use_pct > 80
                    ? ""
                    : ""}
                </Text>
              ) : null}
              {num(place.calorie_use_pct) != null && place.calorie_use_pct > 90 ? (
                <Text style={styles.overBudgetLabel}>
                  ⚠️ Uses {place.calorie_use_pct}% of remaining calories
                </Text>
              ) : null}
            </View>
          </View>
          {place.item_provenance === "heuristic_suggestion" && place.covered_chain_key ? (
            <View style={{ marginTop: 4 }}>
              <Text style={{ color: textMuted, fontSize: 11, fontStyle: "italic" }} numberOfLines={1}>
                Suggested pick — not from official menu
              </Text>
              {String(place.covered_chain_menu_url || "").trim() ? (
                <TouchableOpacity
                  onPress={() => {
                    const url = String(place.covered_chain_menu_url).trim();
                    if (url.startsWith("http")) Linking.openURL(url).catch(() => {});
                  }}
                  style={{ marginTop: 3 }}
                >
                  <Text style={{ color: colors.success.text, fontSize: 11, fontWeight: "600" }}>
                    View {String(place.covered_chain_display_name || "official").trim()} menu
                  </Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}

      {/* C-pre. "Your usual: X" pill — only shown when user has ≥2 prior visits */}
      {usualMeal && !isScreenshot ? (
        <View style={styles.usualPill}>
          <Text style={styles.usualLabel} numberOfLines={1}>
            👤 Your usual{usualMeal.times >= 3 ? ` (${usualMeal.times}×)` : ""}:
          </Text>
          <Text style={[styles.usualName, { color: textPrimary }]} numberOfLines={1}>
            {usualMeal.name}
          </Text>
          {(usualMeal.kcal != null || usualMeal.protein != null) ? (
            <Text style={[styles.usualMacros, { color: textMuted }]} numberOfLines={1}>
              {usualMeal.kcal != null ? `${usualMeal.kcal} kcal` : ""}
              {(usualMeal.kcal != null && usualMeal.protein != null) ? " · " : ""}
              {usualMeal.protein != null ? `${usualMeal.protein}g p` : ""}
            </Text>
          ) : null}
        </View>
      ) : null}

      {/* C-a. Palm-oil indicator (only when confirmed TRUE; never falsely claim) */}
      {palmOil === true && !isScreenshot ? (
        <View style={styles.palmBadge}>
          <Text style={styles.palmText} numberOfLines={1}>
            🌴 Contains palm oil
          </Text>
        </View>
      ) : null}

      {/* C-b. Alternative picks by goal (high-protein / lowest-cal).
          Only render pills that have a usable item name — bare label text
          without the item is confusing UX. Thumb shown when available. */}
      {goalVariantPills.length > 0 && !isScreenshot ? (
        <View style={styles.variantsRow}>
          {goalVariantPills.map((v, idx) => (
            <View key={`gv-${idx}-${v.label}`} style={styles.variantPill}>
              {v.image ? (
                <Image
                  source={{ uri: v.image }}
                  style={styles.variantThumb}
                  resizeMode="cover"
                  accessible
                  accessibilityIgnoresInvertColors
                />
              ) : (
                <View style={[styles.variantThumb, styles.variantThumbFallback]} />
              )}
              <View style={styles.variantTextCol}>
                <Text style={[styles.variantLabel, { color: textMuted }]} numberOfLines={1}>
                  {v.label}
                </Text>
                <Text style={[styles.variantName, { color: textPrimary }]} numberOfLines={2}>
                  {v.name}
                </Text>
                {(v.kcal != null || v.protein != null) ? (
                  <Text style={[styles.variantMacros, { color: textMuted }]} numberOfLines={1}>
                    {v.kcal != null ? `${v.kcal} kcal` : ""}
                    {(v.kcal != null && v.protein != null) ? " · " : ""}
                    {v.protein != null ? `${v.protein}g p` : ""}
                  </Text>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      ) : null}

      {/* C2. Evidence-backed best order trust (additive) */}
      <BestOrderEvidenceBlock
        payload={place}
        mode="place"
        dark={dark}
        compact={compact}
        screenshotMode={screenshotMode}
      />

      {/* D. Menu may vary (weak only) */}
      {needsMenuCheck && !isScreenshot && (
        <Text style={[styles.menuMayVary, { color: textMuted }]} numberOfLines={1}>
          Menu may vary
        </Text>
      )}

      {/* E. Macros */}
      {(calories != null || protein != null) && (
        <RecommendationMetaRow
          calories={calories}
          protein={protein}
          compact={compact}
        />
      )}

      {/* F. Reason */}
      {reason ? (
        <Text style={[styles.reason, { color: textMuted }]} numberOfLines={2}>
          {reason}
        </Text>
      ) : null}

      {/* Swaps */}
      {swaps.length > 0 && !isScreenshot && (
        <Text style={[styles.swapHint, { color: textMuted }]} numberOfLines={1}>
          Better swap: {swaps[0]}
        </Text>
      )}

      {/* Memory label */}
      {!hideMemory && memoryLabel && !isScreenshot ? (
        <Text style={[styles.memory, { color: colors.accent.primary }]} numberOfLines={1}>
          {memoryLabel}
        </Text>
      ) : null}

      {/* Actions */}
      {(resolvedActions.onPrimary || resolvedActions.onSecondary) && (
        <RecommendationActionRow
          primaryLabel={resolvedActions.primaryLabel}
          onPrimary={resolvedActions.onPrimary}
          secondaryLabel={resolvedActions.secondaryLabel}
          onSecondary={resolvedActions.onSecondary}
          primaryIcon={resolvedActions.primaryIcon}
          variant={dark ? "dark" : "light"}
        />
      )}
    </>
  );

  const cardBase = dark ? premium.cardBase : styles.cardLight;
  const cardHero = dark ? premium.cardHero : styles.cardLightHero;
  const cardStyle = [
    rankPosition === 1 && !compact ? cardHero : cardBase,
    styles.cardLocal,
    compact && styles.cardCompact,
    style,
  ];

  if (onPress) {
    return (
      <PressableScale style={cardStyle} onPress={onPress} scaleDown={0.98} haptic>
        {content}
      </PressableScale>
    );
  }

  return <View style={cardStyle}>{content}</View>;
}

const styles = StyleSheet.create({
  // Local overrides only; surface comes from premium.cardBase/cardHero.
  cardLocal: {},
  cardCompact: {
    padding: spacing.base,
    paddingBottom: spacing.lg,
  },
  // Light theme fallback (rare): keep existing look.
  cardLight: {
    backgroundColor: colors.surfaceLight.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surfaceLight.cardBorder,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  cardLightHero: {
    backgroundColor: colors.surfaceLight.card,
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderColor: colors.surfaceLight.cardBorder,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.xl,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    flexShrink: 0,
  },
  name: {
    fontSize: typography.xxl,
    fontWeight: typography.weight.extrabold,
    flex: 1,
  },
  heroBadge: {
    fontSize: typography.xs,
    fontWeight: typography.weight.bold,
    backgroundColor: colors.success.bg,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    overflow: "hidden",
    marginRight: spacing.md,
  },
  heroBadgeWeak: {
    backgroundColor: "rgba(100,116,139,0.2)",
  },
  badgeRow: {
    marginTop: spacing.sm,
  },
  bestItem: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
    marginTop: spacing.md,
    lineHeight: typography.xl * 1.35,
  },
  fitLabel: {
    fontSize: 11,
    fontWeight: "700",
    color: colors.success.text,
    marginTop: 3,
  },
  overBudgetLabel: {
    fontSize: 11,
    fontWeight: "600",
    color: colors.amber.primary,
    marginTop: 2,
  },
  bestItemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  bestItemThumb: {
    width: 56,
    height: 56,
    borderRadius: radius.sm,
    backgroundColor: "rgba(148, 163, 184, 0.18)",
  },
  usualPill: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    marginTop: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "rgba(99, 102, 241, 0.35)",
    backgroundColor: "rgba(99, 102, 241, 0.10)",
    alignSelf: "flex-start",
    maxWidth: "100%",
  },
  usualLabel: {
    fontSize: 11,
    fontWeight: typography.weight.semibold,
    color: "#a5b4fc",
    marginRight: 6,
  },
  usualName: {
    fontSize: 12,
    fontWeight: typography.weight.semibold,
    flexShrink: 1,
  },
  usualMacros: {
    fontSize: 11,
    marginLeft: 6,
  },
  palmBadge: {
    marginTop: 6,
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.45)",
    backgroundColor: "rgba(245, 158, 11, 0.14)",
  },
  palmText: {
    fontSize: 11,
    fontWeight: typography.weight.semibold,
    color: "#f59e0b",
  },
  variantsRow: {
    marginTop: spacing.sm,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  variantPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "rgba(148, 163, 184, 0.30)",
    backgroundColor: "rgba(15, 23, 42, 0.35)",
    width: "100%",
  },
  variantThumb: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: "rgba(148, 163, 184, 0.18)",
  },
  variantThumbFallback: {
    backgroundColor: "rgba(148, 163, 184, 0.12)",
  },
  variantTextCol: {
    flex: 1,
    flexDirection: "column",
  },
  variantLabel: {
    fontSize: 10,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginBottom: 2,
  },
  variantName: {
    fontSize: 13,
    fontWeight: typography.weight.semibold,
    flexShrink: 1,
  },
  variantMacros: {
    fontSize: 11,
    marginTop: 2,
  },
  menuMayVary: {
    fontSize: typography.xs,
    marginTop: spacing.xs,
    fontStyle: "italic",
  },
  reason: {
    fontSize: typography.sm,
    marginTop: spacing.sm,
    fontStyle: "italic",
  },
  swapHint: {
    fontSize: typography.sm,
    marginTop: spacing.xs,
  },
  memory: {
    fontSize: typography.xs,
    marginTop: spacing.xs,
  },
});

/**
 * RecommendationCard – Unified premium card for Healthy Nearby, Smart Alerts, map bottom.
 * Token-driven, Figma-friendly. Supports strong / estimated / weak variants.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";
import { ConfidenceBadge, inferConfidenceTier } from "./ConfidenceBadge";
import { shouldShowMenuMayVary } from "../smartAlertTrustLabels";
import { ScoreBadge } from "./ScoreBadge";
import { RecommendationMetaRow } from "./RecommendationMetaRow";
import { RecommendationActionRow } from "./RecommendationActionRow";

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
}) {
  if (!place || typeof place !== "object") return null;

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

  const resolvedVariant = variant || inferCardVariant(place);
  const needsMenuCheck = shouldShowMenuMayVary(place);

  const isWeak = resolvedVariant === "weak";
  const bgColor = dark ? colors.surface.card : colors.surfaceLight.card;
  const borderColor = dark ? colors.surface.cardBorder : colors.surfaceLight.cardBorder;
  const textPrimary = dark ? colors.text.primary : colors.textLight.primary;
  const textMuted = dark ? colors.slate.text : colors.textLight.muted;

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

      {/* C. Best item */}
      {bestItem ? (
        <Text style={[styles.bestItem, { color: textPrimary }]} numberOfLines={2}>
          {bestItem}
        </Text>
      ) : null}

      {/* D. Menu may vary (weak only) */}
      {needsMenuCheck && (
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
      {swaps.length > 0 && (
        <Text style={[styles.swapHint, { color: textMuted }]} numberOfLines={1}>
          Better swap: {swaps[0]}
        </Text>
      )}

      {/* Memory label */}
      {!hideMemory && memoryLabel ? (
        <Text style={[styles.memory, { color: colors.accent.primary }]} numberOfLines={1}>
          {memoryLabel}
        </Text>
      ) : null}

      {/* Actions */}
      {(actions.onPrimary || actions.onSecondary) && (
        <RecommendationActionRow
          primaryLabel={actions.primaryLabel}
          onPrimary={actions.onPrimary}
          secondaryLabel={actions.secondaryLabel}
          onSecondary={actions.onSecondary}
          primaryIcon={actions.primaryIcon}
          variant={dark ? "dark" : "light"}
        />
      )}
    </>
  );

  const cardStyle = [
    styles.card,
    { backgroundColor: bgColor, borderColor },
    compact && styles.cardCompact,
  ];

  if (onPress) {
    return (
      <TouchableOpacity style={[cardStyle, style]} onPress={onPress} activeOpacity={0.9}>
        {content}
      </TouchableOpacity>
    );
  }

  return <View style={[cardStyle, style]}>{content}</View>;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.xl,
    borderWidth: 1,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  cardCompact: {
    padding: spacing.base,
    paddingBottom: spacing.lg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.base,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
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

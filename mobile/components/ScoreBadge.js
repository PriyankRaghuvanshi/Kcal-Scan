/**
 * ScoreBadge – Numeric score display (e.g. display_rank_score_100).
 * Premium, calm styling.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function ScoreBadge({ score, isTop = false, size = "md", style }) {
  const s = num(score);
  if (s == null) return null;

  const rounded = Math.round(s);
  const isStrong = rounded >= 75;
  const isGood = rounded >= 65 && rounded < 75;
  const color = isTop ? colors.success.text : isStrong ? colors.success.text : isGood ? colors.amber.text : colors.slate.text;
  const borderColor = isTop ? colors.success.primary : isStrong ? colors.success.border : colors.slate.primary;

  return (
    <View
      style={[
        premium.pill,
        styles.badge,
        size === "sm" && styles.badgeSm,
        { backgroundColor: colors.success.bg, borderColor },
        isTop && styles.badgeTop,
        style,
      ]}
    >
      <Text style={[styles.text, size === "sm" && styles.textSm, { color }]}>{rounded}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    minWidth: 40,
    alignItems: "center",
  },
  badgeSm: {
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    minWidth: 32,
  },
  badgeTop: {
    borderWidth: 1.5,
  },
  text: {
    fontSize: typography.lg,
    fontWeight: typography.weight.extrabold,
  },
  textSm: {
    fontSize: typography.base,
  },
});

/**
 * RecommendationMetaRow – Macros (kcal, protein), distance, secondary info.
 * Consistent layout for cards.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, typography } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function formatDistance(m) {
  if (m == null || !Number.isFinite(m) || m <= 0) return "";
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m)} m`;
}

export function RecommendationMetaRow({
  calories,
  protein,
  distanceM,
  compact = false,
  style,
}) {
  const cal = num(calories);
  const pro = num(protein);
  const dist = distanceM != null ? formatDistance(Number(distanceM)) : null;
  const parts = [];

  if (cal != null) parts.push(`${Math.round(cal)} kcal`);
  if (pro != null) parts.push(`${Math.round(pro)}g protein`);
  if (dist) parts.push(dist);

  if (parts.length === 0) return null;

  return (
    <View style={[styles.row, compact && styles.rowCompact, style]}>
      <Text style={[styles.text, compact && styles.textCompact]} numberOfLines={1}>
        {parts.join(" · ")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.sm,
  },
  rowCompact: {
    marginTop: spacing.xs,
  },
  text: {
    fontSize: typography.sm,
    color: colors.slate.text,
  },
  textCompact: {
    fontSize: typography.xs,
  },
});

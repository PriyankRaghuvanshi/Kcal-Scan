/**
 * Filter chips for Healthy Nearby map – horizontal scroll, store-locator style.
 */

import React from "react";
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";

const CHIPS = [
  { key: "all", label: "All" },
  { key: "high_protein", label: "High Protein" },
  { key: "under_600", label: "Under 600 kcal" },
  { key: "fits_today", label: "Fits Today" },
  { key: "cut_friendly", label: "Cut Friendly" },
  { key: "best_right_now", label: "Best Right Now" },
];

export function HealthyMapFilters({ activeKey, onSelect, style }) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={[styles.row, style]}
    >
      {CHIPS.map((chip) => {
        const active = activeKey === chip.key;
        return (
          <TouchableOpacity
            key={chip.key}
            style={[styles.chip, active && styles.chipActive]}
            onPress={() => onSelect(chip.key)}
            activeOpacity={0.8}
          >
            <Text style={[styles.chipText, active && styles.chipTextActive]}>{chip.label}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.pill,
    backgroundColor: colors.surface.card,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
  },
  chipActive: {
    backgroundColor: colors.success.bg,
    borderColor: colors.success.primary,
  },
  chipText: {
    color: colors.slate.text,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  chipTextActive: {
    color: colors.success.text,
  },
});

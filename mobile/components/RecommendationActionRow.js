/**
 * RecommendationActionRow – Primary + optional secondary CTAs.
 * Directions, Scan Menu, View, Dismiss, etc.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";

export function RecommendationActionRow({
  primaryLabel = "Directions",
  onPrimary,
  secondaryLabel,
  onSecondary,
  primaryIcon = "📍",
  variant = "dark",
  style,
}) {
  const isDark = variant === "dark";

  return (
    <View style={[styles.row, style]}>
      {onPrimary && (
        <TouchableOpacity
          style={[
            styles.primaryBtn,
            isDark ? styles.primaryBtnDark : styles.primaryBtnLight,
          ]}
          onPress={onPrimary}
          activeOpacity={0.8}
        >
          <Text
            style={[
              styles.primaryBtnText,
              isDark ? styles.primaryBtnTextDark : styles.primaryBtnTextLight,
            ]}
            numberOfLines={1}
          >
            {primaryIcon ? `${primaryIcon} ` : ""}{primaryLabel}
          </Text>
        </TouchableOpacity>
      )}
      {onSecondary && secondaryLabel && (
        <TouchableOpacity
          style={[
            styles.secondaryBtn,
            isDark ? styles.secondaryBtnDark : styles.secondaryBtnLight,
          ]}
          onPress={onSecondary}
          activeOpacity={0.8}
        >
          <Text
            style={[
              styles.secondaryBtnText,
              isDark ? styles.secondaryBtnTextDark : styles.secondaryBtnTextLight,
            ]}
            numberOfLines={1}
          >
            {secondaryLabel}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: spacing.base,
    marginTop: spacing.lg,
  },
  primaryBtn: {
    flex: 1,
    paddingVertical: spacing.base,
    borderRadius: radius.lg,
    alignItems: "center",
    borderWidth: 1,
  },
  primaryBtnDark: {
    backgroundColor: colors.success.bg,
    borderColor: colors.success.border,
  },
  primaryBtnLight: {
    backgroundColor: colors.success.primary,
    borderColor: colors.success.primary,
  },
  primaryBtnText: {
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
  },
  primaryBtnTextDark: {
    color: colors.success.text,
  },
  primaryBtnTextLight: {
    color: "#fff",
  },
  secondaryBtn: {
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  secondaryBtnDark: {
    backgroundColor: colors.surface.elevated,
    borderColor: colors.surface.cardBorder,
  },
  secondaryBtnLight: {
    backgroundColor: colors.surfaceLight.elevated,
    borderColor: colors.surfaceLight.cardBorder,
  },
  secondaryBtnText: {
    fontSize: typography.base,
    fontWeight: typography.weight.semibold,
  },
  secondaryBtnTextDark: {
    color: colors.accent.muted,
  },
  secondaryBtnTextLight: {
    color: colors.textLight.secondary,
  },
});

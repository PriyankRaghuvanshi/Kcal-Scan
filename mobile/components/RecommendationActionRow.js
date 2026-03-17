/**
 * RecommendationActionRow – Primary + optional secondary CTAs.
 * Directions, Scan Menu, View, Dismiss, etc.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";

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
            premium.ctaPrimary,
            styles.primaryBtn,
            !isDark && styles.primaryBtnLight,
          ]}
          onPress={onPrimary}
          activeOpacity={0.8}
        >
          <Text
            style={[
              premium.ctaPrimaryText,
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
            premium.ctaSecondary,
            styles.secondaryBtn,
            isDark ? styles.secondaryBtnDark : styles.secondaryBtnLight,
          ]}
          onPress={onSecondary}
          activeOpacity={0.8}
        >
          <Text
            style={[
              premium.ctaSecondaryText,
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
    marginTop: spacing.lg,
  },
  primaryBtn: {
    flex: 1,
    paddingHorizontal: spacing.base,
  },
  primaryBtnLight: {
    backgroundColor: colors.success.primary,
    borderColor: colors.success.primary,
  },
  primaryBtnText: {
    fontSize: typography.md,
  },
  primaryBtnTextDark: {
    color: colors.text.inverse,
  },
  primaryBtnTextLight: {
    color: "#fff",
  },
  secondaryBtn: {
    marginLeft: spacing.base,
  },
  secondaryBtnDark: {
    backgroundColor: "transparent",
  },
  secondaryBtnLight: {
    backgroundColor: colors.surfaceLight.elevated,
    borderColor: colors.surfaceLight.cardBorder,
  },
  secondaryBtnText: {
    fontSize: typography.base,
  },
  secondaryBtnTextDark: {
    color: colors.accent.primary,
  },
  secondaryBtnTextLight: {
    color: colors.textLight.secondary,
  },
});

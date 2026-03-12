/**
 * SectionHeader – Consistent section titles for lists and cards.
 */

import React from "react";
import { Text, StyleSheet } from "react-native";
import { colors, spacing, typography } from "../designTokens";

export function SectionHeader({ title, subtitle, style, light = false }) {
  const textColor = light ? colors.textLight.primary : colors.text.primary;
  const subColor = light ? colors.textLight.muted : colors.slate.text;

  return (
    <>
      <Text style={[styles.title, { color: textColor }, style]} numberOfLines={1}>
        {title}
      </Text>
      {subtitle ? (
        <Text style={[styles.subtitle, { color: subColor }]} numberOfLines={1}>
          {subtitle}
        </Text>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  title: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
  },
  subtitle: {
    fontSize: typography.sm,
    marginTop: spacing.xs,
  },
});

/**
 * Goal Coach – paywall / continuation card after free kickoff.
 * Plan remains visible; this card prompts to unlock ongoing adaptive coach.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

export function PlanPaywallCard({ onUnlock, kickoffDay = 0, kickoffDaysTotal = 21, requiresAdvancedPlan = false }) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>
        {requiresAdvancedPlan ? "Upgrade to Advanced to continue" : "Unlock your ongoing adaptive coach"}
      </Text>
      <Text style={styles.body}>
        You've used your {kickoffDaysTotal}-day free trial. Your plan and progress are still here.
        {requiresAdvancedPlan
          ? " Upgrade to the Advanced plan to keep daily check-ins, weight & photo tracking, and coach actions."
          : " Subscribe to get daily targets, best actions, and weekly reviews every day."}
      </Text>
      <TouchableOpacity onPress={onUnlock} style={styles.btn} activeOpacity={0.8}>
        <Text style={styles.btnText}>{requiresAdvancedPlan ? "Upgrade to Advanced" : "View subscription"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.success.border,
    padding: spacing.lg,
    ...shadows.sm,
  },
  title: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: spacing.sm,
  },
  body: {
    fontSize: typography.sm,
    color: colors.slate.text,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
    marginBottom: spacing.base,
  },
  btn: {
    backgroundColor: colors.success.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.base,
    alignItems: "center",
  },
  btnText: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.inverse,
  },
});

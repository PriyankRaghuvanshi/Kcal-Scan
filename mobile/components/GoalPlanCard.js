/**
 * Goal Coach – plan summary card (targets, timeframe, first actions, optional CTA).
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

const GOAL_LABELS = { fat_loss: "Fat loss", muscle_gain: "Muscle gain", recomp: "Recomp", maintain: "Maintain" };

export function GoalPlanCard({ plan, kickoffDay = 0, kickoffDaysTotal = 21, kickoffActive, hasDailyAction, onViewToday }) {
  if (!plan || typeof plan !== "object") return null;

  const starter = plan.starter_plan || plan;
  const goalType = (plan.goal_type || starter.goal_type || "fat_loss").replace(/\s+/g, "_");
  const targetCal = num(starter.target_calories ?? plan.target_calories) ?? 0;
  const targetProtein = num(starter.target_protein_g ?? plan.target_protein_g) ?? 0;
  const weeks = num(plan.timeframe_weeks ?? starter.timeframe_weeks) || 0;
  const firstActions = starter.first_actions || [];
  const weeklyFocus = starter.weekly_focus || "";
  const showViewToday = hasDailyAction && typeof onViewToday === "function";

  const goalLabel = GOAL_LABELS[goalType] || goalType.replace(/_/g, " ");

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.badge}>Your plan</Text>
        {kickoffActive && (
          <Text style={styles.kickoff}>
            Day {kickoffDay} of {kickoffDaysTotal} free
          </Text>
        )}
      </View>
      <Text style={styles.goal}>{goalLabel}</Text>
      <View style={styles.targets}>
        <Text style={styles.targetLine}>{targetCal} kcal · {targetProtein}g protein</Text>
        {weeks > 0 && <Text style={styles.weeks}>{weeks} weeks</Text>}
      </View>
      {weeklyFocus ? (
        <Text style={styles.focus} numberOfLines={2}>{weeklyFocus}</Text>
      ) : null}
      {firstActions.length > 0 && (
        <View style={styles.actions}>
          <Text style={styles.actionsLabel}>First steps</Text>
          {firstActions.slice(0, 3).map((action, i) => (
            <Text key={i} style={styles.actionItem} numberOfLines={1}>• {action}</Text>
          ))}
        </View>
      )}
      {showViewToday && (
        <TouchableOpacity style={styles.viewTodayCta} onPress={onViewToday} activeOpacity={0.8}>
          <Text style={styles.viewTodayCtaText}>View today's action</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    padding: spacing.lg,
    ...shadows.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  badge: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.success.text,
    textTransform: "uppercase",
  },
  kickoff: {
    fontSize: typography.xs,
    color: colors.slate.muted,
  },
  goal: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  targets: {
    marginBottom: spacing.sm,
  },
  targetLine: {
    fontSize: typography.md,
    color: colors.text.secondary,
  },
  weeks: {
    fontSize: typography.sm,
    color: colors.slate.muted,
    marginTop: 2,
  },
  focus: {
    fontSize: typography.sm,
    color: colors.slate.text,
    lineHeight: typography.md * typography.lineHeight.normal,
    marginBottom: spacing.sm,
  },
  actions: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  actionsLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.slate.muted,
    marginBottom: spacing.xs,
  },
  actionItem: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    marginLeft: spacing.xs,
  },
  viewTodayCta: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  viewTodayCtaText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
    fontWeight: typography.weight.semibold,
  },
});

/**
 * Goal Coach – daily state card: targets, consumed, one best action, coach summary, CTAs.
 */

import React, { useEffect, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";
import { trackGoalCoachActionShown } from "../utils/goalCoachUtils";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function DailyCoachCard({ apiBase, userId, daily, subscriptionRequired, primaryAction, secondaryAction, onPrimaryAction, onSecondaryAction }) {
  const shownTrackedRef = useRef(null);

  useEffect(() => {
    if (!apiBase || !userId || !primaryAction?.action_type || subscriptionRequired) return;
    const key = `${primaryAction.action_type}:${primaryAction.label || ""}`;
    if (shownTrackedRef.current === key) return;
    shownTrackedRef.current = key;
    const ctx = primaryAction.context || {};
    trackGoalCoachActionShown(apiBase, userId, {
      source_surface: "daily_coach",
      action_type: primaryAction.action_type,
      goal_type: ctx.goal,
      reason: primaryAction.reason,
      remaining_protein_g: ctx.remaining_protein_g,
      remaining_calories: ctx.remaining_calories,
    });
  }, [apiBase, userId, primaryAction?.action_type, primaryAction?.label, subscriptionRequired]);

  if (!daily || typeof daily !== "object") return null;

  const targets = daily.today_targets || {};
  const consumed = daily.consumed_so_far || {};
  const calTarget = num(targets.calories) || 0;
  const proteinTarget = num(targets.protein_g) || 0;
  const calConsumed = num(consumed.calories) || 0;
  const proteinConsumed = num(consumed.protein_g) || 0;
  const bestAction = daily.best_action_today || "";
  const coachSummary = daily.coach_summary || "";
  const riskFlags = Array.isArray(daily.risk_flags) ? daily.risk_flags : [];

  const calPct = calTarget > 0 ? Math.min(100, Math.round((calConsumed / calTarget) * 100)) : 0;
  const proteinPct = proteinTarget > 0 ? Math.min(100, Math.round((proteinConsumed / proteinTarget) * 100)) : 0;

  if (subscriptionRequired) {
    return (
      <View style={styles.card}>
        <Text style={styles.gatedTitle}>Today's coach</Text>
        <Text style={styles.gatedText}>Unlock your ongoing adaptive coach to see daily targets and your best action.</Text>
      </View>
    );
  }

  const hasPrimary = primaryAction && primaryAction.label && typeof onPrimaryAction === "function";
  const hasSecondary = secondaryAction && secondaryAction.label && typeof onSecondaryAction === "function";

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Today's coach</Text>
      <View style={styles.row}>
        <View style={styles.block}>
          <Text style={styles.label}>Calories</Text>
          <Text style={styles.value}>{calConsumed} / {calTarget}</Text>
          <View style={styles.barBg}><View style={[styles.barFill, { width: `${calPct}%` }]} /></View>
        </View>
        <View style={styles.block}>
          <Text style={styles.label}>Protein</Text>
          <Text style={styles.value}>{proteinConsumed}g / {proteinTarget}g</Text>
          <View style={styles.barBg}><View style={[styles.barFill, { width: `${proteinPct}%` }]} /></View>
        </View>
      </View>
      {bestAction ? (
        <View style={styles.actionBlock}>
          <Text style={styles.actionLabel}>Best action</Text>
          <Text style={styles.actionText}>{bestAction}</Text>
        </View>
      ) : null}
      {coachSummary ? (
        <Text style={styles.summary} numberOfLines={2}>{coachSummary}</Text>
      ) : null}
      {riskFlags.length > 0 && (
        <View style={styles.riskRow}>
          {riskFlags.slice(0, 2).map((r, i) => (
            <Text key={i} style={styles.riskChip}>{r.replace(/_/g, " ")}</Text>
          ))}
        </View>
      )}
      {hasPrimary && (
        <View style={styles.ctaRow}>
          <TouchableOpacity style={styles.primaryCta} onPress={() => onPrimaryAction(primaryAction)} activeOpacity={0.8}>
            <Text style={styles.primaryCtaText}>{primaryAction.label}</Text>
          </TouchableOpacity>
          {hasSecondary && (
            <TouchableOpacity style={styles.secondaryCta} onPress={() => onSecondaryAction(secondaryAction)} activeOpacity={0.8}>
              <Text style={styles.secondaryCtaText}>{secondaryAction.label}</Text>
            </TouchableOpacity>
          )}
        </View>
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
  title: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: spacing.base,
  },
  gatedTitle: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  gatedText: {
    fontSize: typography.sm,
    color: colors.slate.text,
  },
  row: {
    flexDirection: "row",
    gap: spacing.lg,
    marginBottom: spacing.base,
  },
  block: {
    flex: 1,
  },
  label: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    marginBottom: 2,
  },
  value: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    marginBottom: spacing.xs,
  },
  barBg: {
    height: 4,
    backgroundColor: "rgba(26,38,66,0.8)",
    borderRadius: 2,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    backgroundColor: colors.success.primary,
    borderRadius: 2,
  },
  actionBlock: {
    marginBottom: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  actionLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.slate.muted,
    marginBottom: 2,
  },
  actionText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
  },
  summary: {
    fontSize: typography.sm,
    color: colors.slate.text,
    lineHeight: typography.sm * typography.lineHeight.normal,
  },
  riskRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  riskChip: {
    fontSize: typography.xs,
    color: colors.amber.text,
    backgroundColor: colors.amber.bg,
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.xs,
  },
  ctaRow: {
    marginTop: spacing.base,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
    gap: spacing.sm,
  },
  primaryCta: {
    backgroundColor: colors.success.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    alignItems: "center",
  },
  primaryCtaText: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.inverse,
  },
  secondaryCta: {
    backgroundColor: "transparent",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    alignItems: "center",
  },
  secondaryCtaText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
  },
});

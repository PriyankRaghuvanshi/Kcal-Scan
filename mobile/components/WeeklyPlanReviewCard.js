/**
 * Goal Coach – weekly review card: adherence, win, bottleneck, next focus, CTA.
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

export function WeeklyPlanReviewCard({ apiBase, userId, review, weekStart, weekEnd, subscriptionRequired, nextStepAction, onNextStepAction }) {
  const shownTrackedRef = useRef(null);

  useEffect(() => {
    if (!apiBase || !userId || !nextStepAction?.action_type || subscriptionRequired) return;
    const key = `${nextStepAction.action_type}:${nextStepAction.label || ""}`;
    if (shownTrackedRef.current === key) return;
    shownTrackedRef.current = key;
    const ctx = nextStepAction.context || {};
    trackGoalCoachActionShown(apiBase, userId, {
      source_surface: "weekly_review",
      action_type: nextStepAction.action_type,
      goal_type: ctx.goal,
      reason: nextStepAction.reason,
      remaining_protein_g: ctx.remaining_protein_g,
      remaining_calories: ctx.remaining_calories,
    });
  }, [apiBase, userId, nextStepAction?.action_type, nextStepAction?.label, subscriptionRequired]);

  if (!review || typeof review !== "object") return null;

  if (subscriptionRequired) {
    return (
      <View style={styles.card}>
        <Text style={styles.gatedTitle}>Weekly review</Text>
        <Text style={styles.gatedText}>Unlock your ongoing coach to see adherence and next week's focus.</Text>
      </View>
    );
  }

  const headline = review.headline || "";
  const supporting = review.supporting_text || "";
  const adherence = num(review.adherence_score) ?? 0;
  const mainWin = review.main_win || "";
  const mainBottleneck = review.main_bottleneck || "";
  const nextFocus = review.next_week_focus || {};
  const headlineNext = nextFocus.headline || "";
  const supportingNext = nextFocus.supporting_text || "";
  const hasNextStep = nextStepAction && nextStepAction.label && typeof onNextStepAction === "function";

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Weekly review</Text>
      {(weekStart || weekEnd) && (
        <Text style={styles.weekRange}>
          {weekStart && weekEnd ? `${weekStart} – ${weekEnd}` : weekStart || weekEnd}
        </Text>
      )}
      {headline ? <Text style={styles.headline}>{headline}</Text> : null}
      {supporting ? <Text style={styles.supporting} numberOfLines={2}>{supporting}</Text> : null}
      <View style={styles.scoreRow}>
        <View style={styles.scoreBlock}>
          <Text style={styles.scoreValue}>{adherence}</Text>
          <Text style={styles.scoreLabel}>Adherence %</Text>
        </View>
      </View>
      {mainWin ? (
        <View style={styles.winBlock}>
          <Text style={styles.winLabel}>Main win</Text>
          <Text style={styles.winText} numberOfLines={2}>{mainWin}</Text>
        </View>
      ) : null}
      {mainBottleneck ? (
        <View style={styles.bottleneckBlock}>
          <Text style={styles.bottleneckLabel}>Bottleneck</Text>
          <Text style={styles.bottleneckText} numberOfLines={2}>{mainBottleneck}</Text>
        </View>
      ) : null}
      {(headlineNext || supportingNext) ? (
        <View style={styles.nextBlock}>
          <Text style={styles.nextLabel}>Next week</Text>
          {headlineNext ? <Text style={styles.nextHeadline}>{headlineNext}</Text> : null}
          {supportingNext ? <Text style={styles.nextSupporting} numberOfLines={2}>{supportingNext}</Text> : null}
        </View>
      ) : null}
      {hasNextStep && (
        <TouchableOpacity style={styles.nextStepCta} onPress={() => onNextStepAction(nextStepAction)} activeOpacity={0.8}>
          <Text style={styles.nextStepCtaText}>{nextStepAction.label}</Text>
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
  title: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: spacing.xs,
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
  weekRange: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    marginBottom: spacing.sm,
  },
  headline: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.secondary,
    marginBottom: spacing.xs,
  },
  supporting: {
    fontSize: typography.sm,
    color: colors.slate.text,
    marginBottom: spacing.base,
    lineHeight: typography.sm * typography.lineHeight.normal,
  },
  scoreRow: {
    flexDirection: "row",
    marginBottom: spacing.base,
  },
  scoreBlock: {
    marginRight: spacing.xl,
  },
  scoreValue: {
    fontSize: typography.xxl,
    fontWeight: typography.weight.bold,
    color: colors.success.text,
  },
  scoreLabel: {
    fontSize: typography.xs,
    color: colors.slate.muted,
  },
  winBlock: {
    marginBottom: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  winLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.slate.muted,
    marginBottom: 2,
  },
  winText: {
    fontSize: typography.sm,
    color: colors.success.text,
  },
  bottleneckBlock: {
    marginBottom: spacing.sm,
  },
  bottleneckLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.slate.muted,
    marginBottom: 2,
  },
  bottleneckText: {
    fontSize: typography.sm,
    color: colors.amber.text,
  },
  nextBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  nextLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.slate.muted,
    marginBottom: 2,
  },
  nextHeadline: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.secondary,
  },
  nextSupporting: {
    fontSize: typography.sm,
    color: colors.slate.text,
    marginTop: 2,
    lineHeight: typography.sm * typography.lineHeight.normal,
  },
  nextStepCta: {
    marginTop: spacing.base,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
    backgroundColor: colors.success.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    alignItems: "center",
  },
  nextStepCtaText: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.inverse,
  },
});

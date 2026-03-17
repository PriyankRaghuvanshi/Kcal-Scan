/**
 * Goal Coach – weekly review card: adherence, win, bottleneck, next focus, CTA.
 */

import React, { useEffect, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";
import { trackGoalCoachActionShown } from "../utils/goalCoachUtils";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function WeeklyPlanReviewCard({
  apiBase,
  userId,
  review,
  weekStart,
  weekEnd,
  subscriptionRequired,
  nextStepAction,
  onNextStepAction,
  // Optional: allow passing weekly reward signals even if not nested under review.
  winSummary: winSummaryProp,
  proteinDaysThisWeek: proteinDaysThisWeekProp,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
}) {
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
  const winSummary = String(winSummaryProp || review.win_summary || review?.report_card_facts?.win_summary || "").trim();
  const proteinDaysThisWeek = proteinDaysThisWeekProp != null ? num(proteinDaysThisWeekProp) : num(review?.report_card_facts?.protein_days_this_week);
  const nextFocus = review.next_week_focus || {};
  const headlineNext = nextFocus.headline || "";
  const supportingNext = nextFocus.supporting_text || "";
  const hasNextStep = nextStepAction && nextStepAction.label && typeof onNextStepAction === "function";
  const isScreenshot = Boolean(screenshotMode);

  return (
    <View style={[premium.cardBase, styles.card]}>
      <Text style={premium.title}>Weekly review</Text>
      {(weekStart || weekEnd) && (
        <Text style={styles.weekRange}>
          {weekStart && weekEnd ? `${weekStart} – ${weekEnd}` : weekStart || weekEnd}
        </Text>
      )}
      {headline ? <Text style={styles.headline}>{headline}</Text> : null}
      {supporting ? <Text style={premium.muted} numberOfLines={2}>{supporting}</Text> : null}
      <View style={styles.scoreRow}>
        <View style={styles.scoreBlock}>
          <Text style={styles.scoreValue}>{adherence}</Text>
          <Text style={styles.scoreLabel}>Adherence %</Text>
        </View>
      </View>

      {(winSummary || proteinDaysThisWeek != null) ? (
        <View style={styles.summaryBlock}>
          <Text style={premium.kicker}>This week</Text>
          {winSummary ? <Text style={[premium.body, { marginTop: 6 }]} numberOfLines={3}>{winSummary}</Text> : null}
          {proteinDaysThisWeek != null ? (
            <Text style={[premium.muted, { marginTop: 6 }]}>
              Protein target hit {Math.round(proteinDaysThisWeek)}/7 days
            </Text>
          ) : null}
        </View>
      ) : null}
      {mainWin ? (
        <View style={styles.winBlock}>
          <Text style={styles.winLabel}>Main win</Text>
          <Text style={styles.winText} numberOfLines={2}>{mainWin}</Text>
        </View>
      ) : null}
      {mainBottleneck && !isScreenshot ? (
        <View style={styles.bottleneckBlock}>
          <Text style={styles.bottleneckLabel}>Bottleneck</Text>
          <Text style={styles.bottleneckText} numberOfLines={2}>{mainBottleneck}</Text>
        </View>
      ) : null}
      {(headlineNext || supportingNext) && !isScreenshot ? (
        <View style={styles.nextBlock}>
          <Text style={styles.nextLabel}>Next week</Text>
          {headlineNext ? <Text style={styles.nextHeadline}>{headlineNext}</Text> : null}
          {supportingNext ? <Text style={premium.muted} numberOfLines={2}>{supportingNext}</Text> : null}
        </View>
      ) : null}
      {hasNextStep && (
        <TouchableOpacity style={premium.ctaPrimary} onPress={() => onNextStepAction(nextStepAction)} activeOpacity={0.85}>
          <Text style={premium.ctaPrimaryText}>{nextStepAction.label}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // Local overrides only; base card comes from premium.cardBase.
  card: {},
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
  summaryBlock: {
    marginBottom: spacing.base,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
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
});

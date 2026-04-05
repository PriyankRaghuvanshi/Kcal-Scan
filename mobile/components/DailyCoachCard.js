/**
 * Goal Coach – daily state card: targets, consumed, one best action, coach summary, CTAs.
 */

import React, { useEffect, useMemo, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";
import { trackGoalCoachActionShown } from "../utils/goalCoachUtils";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function clamp01(v) {
  const n = num(v);
  if (n == null) return 0;
  return Math.max(0, Math.min(1, n));
}

function formatInt(v) {
  const n = num(v);
  if (n == null) return "—";
  return String(Math.round(n));
}

export function DailyCoachCard({
  apiBase,
  userId,
  daily,
  subscriptionRequired,
  primaryAction,
  secondaryAction,
  onPrimaryAction,
  onSecondaryAction,
  /** Scroll home to Progress (weight / photos) when user taps progress nudge. */
  onProgressReminderPress,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
}) {
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

  // Hooks must run before any conditional return (Rules of Hooks).
  const proteinStreakDays = daily && typeof daily === "object" ? num(daily.protein_streak_days) : null;
  const loggingStreakDays = daily && typeof daily === "object" ? num(daily.logging_streak_days) : null;
  const streakChips = useMemo(() => {
    const chips = [];
    if (proteinStreakDays != null && proteinStreakDays >= 2) {
      chips.push({ kind: "success", text: `${Math.round(proteinStreakDays)}‑day protein streak` });
    }
    if (loggingStreakDays != null && loggingStreakDays >= 2) {
      chips.push({ kind: "neutral", text: `${Math.round(loggingStreakDays)}‑day logging streak` });
    }
    return chips.slice(0, 2);
  }, [proteinStreakDays, loggingStreakDays]);

  if (!daily || typeof daily !== "object") return null;

  const targets = daily.today_targets || {};
  const consumed = daily.consumed_so_far || {};
  const calTarget = num(targets.calories) || 0;
  const proteinTarget = num(targets.protein_g) || 0;
  const calConsumed = num(consumed.calories) || 0;
  const proteinConsumed = num(consumed.protein_g) || 0;
  const bestAction = String(daily.best_action_today || "").trim();
  const coachSummary = String(daily.coach_summary || "").trim();
  const coachConnection = String(daily.coach_connection || "").trim();
  const progressReminder =
    daily.progress_reminder && typeof daily.progress_reminder === "object" ? daily.progress_reminder : null;
  const progressMsg = String(progressReminder?.message || "").trim();
  const progressCta = String(progressReminder?.cta_label || "Update progress").trim();
  const winLine = String(daily.win_line || "").trim();
  const riskFlags = Array.isArray(daily.risk_flags) ? daily.risk_flags : [];

  const calPct = calTarget > 0 ? Math.min(100, Math.round((calConsumed / calTarget) * 100)) : 0;
  const proteinPct = proteinTarget > 0 ? Math.min(100, Math.round((proteinConsumed / proteinTarget) * 100)) : 0;
  const calTrackPct = Math.round(clamp01(calTarget > 0 ? calConsumed / calTarget : 0) * 100);
  const proteinTrackPct = Math.round(clamp01(proteinTarget > 0 ? proteinConsumed / proteinTarget : 0) * 100);

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
  const isScreenshot = Boolean(screenshotMode);

  return (
    <View style={[premium.cardBase, styles.card]}>
      <View style={styles.headerRow}>
        <View style={styles.coachIdRow}>
          <View style={premium.aiOrb}>
            <Text style={premium.aiOrbText}>AI</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={premium.kickerOnLight}>Goal Coach</Text>
            <Text style={[premium.title, styles.onLightTitle]}>Today</Text>
          </View>
        </View>
        {streakChips.length ? (
          <View style={styles.chipsRow}>
            {streakChips.map((c, idx) => (
              <View
                key={c.text}
                style={[
                  premium.chipBaseSm,
                  styles.streakChip,
                  idx > 0 ? { marginLeft: spacing.sm } : null,
                  c.kind === "success" ? premium.chipSuccess : premium.chipNeutral,
                ]}
              >
                <Text
                  style={[
                    c.kind === "success" ? premium.chipTextSuccess : premium.chipTextNeutral,
                  ]}
                  numberOfLines={1}
                >
                  {c.text}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
      </View>

      {coachConnection ? (
        <View style={styles.connectionBox}>
          <Text style={premium.kickerOnLight}>Checking in</Text>
          <Text style={[premium.body, styles.onLightBody, { marginTop: 6 }]} numberOfLines={4}>
            {coachConnection}
          </Text>
        </View>
      ) : null}

      {winLine ? (
        <View style={styles.winLineBox}>
          <Text style={styles.winLineText} numberOfLines={2}>
            {winLine}
          </Text>
        </View>
      ) : null}

      <View style={styles.row}>
        <View style={styles.block}>
          <Text style={styles.label}>Calories</Text>
          <Text style={styles.value}>
            {formatInt(calConsumed)} / {formatInt(calTarget)}
            {calTarget > 0 ? ` · ${calTrackPct}%` : ""}
          </Text>
          <View style={styles.barBg}><View style={[styles.barFill, { width: `${calPct}%` }]} /></View>
        </View>
        <View style={styles.block}>
          <Text style={styles.label}>Protein</Text>
          <Text style={styles.value}>
            {formatInt(proteinConsumed)}g / {formatInt(proteinTarget)}g
            {proteinTarget > 0 ? ` · ${proteinTrackPct}%` : ""}
          </Text>
          <View style={styles.barBg}><View style={[styles.barFill, { width: `${proteinPct}%` }]} /></View>
        </View>
      </View>
      {bestAction ? (
        <View style={styles.actionBlock}>
          <View style={styles.oneThingHeader}>
            <Text style={styles.actionLabel}>If you do one thing</Text>
            <View style={styles.oneThingPill}>
              <Text style={styles.oneThingPillText}>High impact</Text>
            </View>
          </View>
          <Text style={styles.actionText} numberOfLines={3}>{bestAction}</Text>
        </View>
      ) : null}
      {coachSummary ? (
        <View style={styles.coachBubble}>
          <Text style={premium.kickerOnLight}>Today at a glance</Text>
          <Text style={[premium.body, styles.onLightBody, { marginTop: 6 }]} numberOfLines={3}>{coachSummary}</Text>
        </View>
      ) : null}

      {!isScreenshot && progressMsg && typeof onProgressReminderPress === "function" ? (
        <View style={styles.progressNudge}>
          <Text style={styles.progressNudgeText} numberOfLines={4}>
            {progressMsg}
          </Text>
          <TouchableOpacity style={premium.ctaGhost} onPress={() => onProgressReminderPress(progressReminder)} activeOpacity={0.85}>
            <Text style={premium.ctaGhostText}>{progressCta}</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      {!isScreenshot && riskFlags.length > 0 && (
        <View style={styles.riskRow}>
          {riskFlags.slice(0, 2).map((r, i) => (
            <Text key={i} style={styles.riskChip}>{r.replace(/_/g, " ")}</Text>
          ))}
        </View>
      )}
      {hasPrimary && (
        <View style={styles.ctaRow}>
          <TouchableOpacity style={premium.ctaPrimary} onPress={() => onPrimaryAction(primaryAction)} activeOpacity={0.85}>
            <Text style={premium.ctaPrimaryText}>{primaryAction.label}</Text>
          </TouchableOpacity>
          {hasSecondary && !isScreenshot && (
            <TouchableOpacity style={[premium.ctaSecondary, { marginTop: spacing.sm }]} onPress={() => onSecondaryAction(secondaryAction)} activeOpacity={0.85}>
              <Text style={premium.ctaSecondaryText}>{secondaryAction.label}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // Local overrides only; base card comes from premium.cardBase.
  card: {
    backgroundColor: "#ffffff",
    borderColor: "#e7b008",
    borderWidth: 1.5,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 6,
  },
  onLightTitle: {
    color: colors.textLight.primary,
  },
  onLightBody: {
    color: colors.textLight.secondary,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.base,
  },
  coachIdRow: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
  },
  kicker: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: 2,
  },
  chipsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    flex: 1,
    marginLeft: spacing.base,
  },
  streakChip: {
    maxWidth: "56%",
  },
  winLineBox: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    backgroundColor: "rgba(255, 188, 13, 0.14)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.40)",
    marginBottom: spacing.base,
  },
  winLineText: {
    fontSize: typography.sm,
    color: "#92400e",
    fontWeight: typography.weight.semibold,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
  },
  connectionBox: {
    marginBottom: spacing.base,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    backgroundColor: "rgba(34, 197, 94, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(34, 197, 94, 0.22)",
  },
  progressNudge: {
    marginBottom: spacing.base,
    padding: spacing.base,
    borderRadius: radius.md,
    backgroundColor: "rgba(59, 130, 246, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(59, 130, 246, 0.22)",
  },
  progressNudgeText: {
    fontSize: typography.sm,
    color: colors.textLight.secondary,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
    marginBottom: spacing.sm,
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
    marginBottom: spacing.base,
  },
  block: {
    flex: 1,
  },
  label: {
    fontSize: typography.xs,
    color: "#6b7280",
    marginBottom: 2,
  },
  value: {
    fontSize: typography.sm,
    color: "#111827",
    marginBottom: spacing.xs,
  },
  barBg: {
    height: 4,
    backgroundColor: "rgba(245, 158, 11, 0.20)",
    borderRadius: 2,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    backgroundColor: "#f59e0b",
    borderRadius: 2,
  },
  actionBlock: {
    marginBottom: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: "#f7b500",
  },
  oneThingHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  oneThingPill: {
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(34, 197, 94, 0.22)",
    backgroundColor: "rgba(255, 188, 13, 0.14)",
    marginLeft: spacing.base,
  },
  oneThingPillText: {
    fontSize: typography.xs,
    color: "#92400e",
    fontWeight: typography.weight.semibold,
  },
  actionLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.extrabold,
    color: "#92400e",
    marginBottom: 2,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  actionText: {
    fontSize: typography.md,
    color: "#1f2937",
    lineHeight: typography.md * typography.lineHeight.relaxed,
    marginTop: 2,
  },
  coachBubble: {
    marginTop: spacing.sm,
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    backgroundColor: "#fff7e0",
    borderWidth: 1,
    borderColor: "#f7b500",
  },
  riskRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginTop: spacing.sm,
  },
  riskChip: {
    fontSize: typography.xs,
    color: "#7c2d12",
    backgroundColor: "#fff3cd",
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.xs,
    marginRight: spacing.xs,
    marginBottom: spacing.xs,
  },
  ctaRow: {
    marginTop: spacing.base,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: "#f7b500",
  },
  // CTA styles now sourced from premium system.
});

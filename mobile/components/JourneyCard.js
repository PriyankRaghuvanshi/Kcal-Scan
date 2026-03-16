/**
 * Let's Go Journey – premium summary card: day number, streak, weight change,
 * this week's photo status, next check-in milestone.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function JourneyCard({
  dayNumber = 0,
  kickoffDaysTotal = 21,
  summary = null,
  photoEntries = [],
  weekStartISO = "",
}) {
  const streak = num(summary?.streak_days) ?? 0;
  const latestWeight = summary?.latest_weight?.value_kg != null ? num(summary.latest_weight.value_kg) : null;
  const previousWeight = summary?.previous_weight?.value_kg != null ? num(summary.previous_weight.value_kg) : null;
  const weightChange =
    latestWeight != null && previousWeight != null ? latestWeight - previousWeight : null;
  const hasPhotoThisWeek =
    weekStartISO &&
    Array.isArray(photoEntries) &&
    photoEntries.some((p) => (p?.week_start || "").slice(0, 10) === weekStartISO.slice(0, 10));
  const nextMilestone = summary?.next_check_in_milestone || "Log your next meal to check in";

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Your journey</Text>

      <View style={styles.row}>
        <View style={styles.stat}>
          <Text style={styles.statValue}>Day {dayNumber}</Text>
          <Text style={styles.statLabel}>of {kickoffDaysTotal}</Text>
        </View>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{streak} day{streak !== 1 ? "s" : ""}</Text>
          <Text style={styles.statLabel}>streak</Text>
        </View>
      </View>

      {weightChange != null && (
        <View style={styles.row}>
          <Text style={styles.label}>Latest weight change</Text>
          <Text
            style={[
              styles.weightChange,
              weightChange > 0 && styles.weightUp,
              weightChange < 0 && styles.weightDown,
            ]}
          >
            {weightChange > 0 ? "+" : ""}
            {weightChange.toFixed(1)} kg
          </Text>
        </View>
      )}

      <View style={styles.row}>
        <Text style={styles.label}>This week's photo</Text>
        <Text style={[styles.photoStatus, hasPhotoThisWeek && styles.photoDone]}>
          {hasPhotoThisWeek ? "Done" : "Not yet"}
        </Text>
      </View>

      <View style={styles.milestone}>
        <Text style={styles.milestoneLabel}>Next</Text>
        <Text style={styles.milestoneText} numberOfLines={2}>
          {nextMilestone}
        </Text>
      </View>
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
    marginBottom: spacing.base,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  stat: {
    alignItems: "flex-start",
  },
  statValue: {
    fontSize: typography.lg,
    fontWeight: typography.weight.bold,
    color: colors.success.text,
  },
  statLabel: {
    fontSize: typography.xs,
    color: colors.slate.text,
    marginTop: 2,
  },
  label: {
    fontSize: typography.sm,
    color: colors.slate.text,
  },
  weightChange: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.secondary,
  },
  weightUp: {
    color: colors.amber.text,
  },
  weightDown: {
    color: colors.success.text,
  },
  photoStatus: {
    fontSize: typography.sm,
    color: colors.slate.muted,
  },
  photoDone: {
    color: colors.success.text,
    fontWeight: typography.weight.semibold,
  },
  milestone: {
    marginTop: spacing.base,
    paddingTop: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  milestoneLabel: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  milestoneText: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
  },
});

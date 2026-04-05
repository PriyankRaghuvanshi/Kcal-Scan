/**
 * Let's Go Journey – premium summary card: day number, streak, weight change,
 * this week's photo status, next check-in milestone.
 */

import React, { useMemo } from "react";
import { View, Text, StyleSheet, Image } from "react-native";
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

  const comparePhotos = useMemo(() => {
    if (!Array.isArray(photoEntries) || photoEntries.length < 2) return null;
    const sorted = [...photoEntries].sort((a, b) =>
      String(b?.week_start || "").localeCompare(String(a?.week_start || "")),
    );
    const a = sorted[0];
    const b = sorted[1];
    const ua = String(a?.uri_or_ref || "").trim();
    const ub = String(b?.uri_or_ref || "").trim();
    if (!ua || !ub) return null;
    return {
      newerUri: ua,
      olderUri: ub,
      newerWeek: String(a?.week_start || "").slice(0, 10),
      olderWeek: String(b?.week_start || "").slice(0, 10),
    };
  }, [photoEntries]);

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

      {comparePhotos ? (
        <View style={styles.compareBlock}>
          <Text style={styles.compareTitle}>Last two progress photos</Text>
          <Text style={styles.compareHint} numberOfLines={2}>
            Same lighting and clothes each week makes this easier to read—not a verdict, just a visual check-in.
          </Text>
          <View style={styles.compareRow}>
            <View style={styles.compareCell}>
              <Text style={styles.compareWeek}>{comparePhotos.olderWeek}</Text>
              <Image source={{ uri: comparePhotos.olderUri }} style={styles.compareImg} resizeMode="cover" />
            </View>
            <View style={styles.compareCell}>
              <Text style={styles.compareWeek}>{comparePhotos.newerWeek}</Text>
              <Image source={{ uri: comparePhotos.newerUri }} style={styles.compareImg} resizeMode="cover" />
            </View>
          </View>
        </View>
      ) : null}

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
  compareBlock: {
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    paddingTop: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  compareTitle: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: 4,
  },
  compareHint: {
    fontSize: typography.xs,
    color: colors.slate.text,
    marginBottom: spacing.sm,
    lineHeight: typography.xs * typography.lineHeight.relaxed,
  },
  compareRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  compareCell: {
    flex: 1,
    minWidth: 0,
  },
  compareWeek: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    marginBottom: 4,
  },
  compareImg: {
    width: "100%",
    aspectRatio: 3 / 4,
    borderRadius: radius.md,
    backgroundColor: colors.surface.elevated,
  },
});

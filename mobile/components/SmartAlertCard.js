/**
 * SmartAlertCard – Single alert candidate. Uses design tokens + shared components.
 * Visually aligned with RecommendationCard for coherent product language.
 * Trust labels and hero language reflect recommendation quality.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { ScoreBadge } from "./ScoreBadge";
import { RecommendationActionRow } from "./RecommendationActionRow";
import {
  getEffectiveAlertTitle,
  getAlertTrustTone,
  shouldShowMenuMayVary,
  TRUST_TONES,
} from "../smartAlertTrustLabels";

const ALERT_TYPE_LABELS = {
  protein_rescue: "Protein rescue",
  post_workout_recovery: "Post-workout recovery",
  late_night_damage_control: "Late-night option",
  worked_before_repeat: "Worked well before",
  habit_rescue: "Habit rescue",
};

function formatDistance(m) {
  if (m == null || !Number.isFinite(m)) return "";
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m)} m`;
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function SmartAlertCard({
  candidate,
  onOpen,
  onDismiss,
  compact = false,
}) {
  if (!candidate || typeof candidate !== "object") return null;

  const effectiveTitle = getEffectiveAlertTitle(candidate);
  const body = candidate.body || "";
  const placeName = candidate.place_name || "Nearby spot";
  const bestItem = candidate.best_item_name || "";
  const score = candidate.display_rank_score_100;
  const alertType = candidate.alert_type || "";
  const distanceM = candidate.distance_m;
  const protein = candidate.estimated_protein_g;
  const personalLabel = candidate.personal_memory_label || "";
  const trustTone = getAlertTrustTone(candidate);
  const showMenuMayVary = shouldShowMenuMayVary(candidate);

  const typeLabel = ALERT_TYPE_LABELS[alertType] || alertType.replace(/_/g, " ");
  const whyLine = personalLabel
    ? personalLabel
    : protein != null
    ? `${typeLabel} • ${protein}g protein • ${formatDistance(distanceM) || "nearby"}`
    : `${typeLabel} • ${formatDistance(distanceM) || "nearby"}`;

  // Pass full candidate so ConfidenceBadge uses canonical trust mapping
  const isWeak = trustTone === TRUST_TONES.weak;
  const cardStyle = [styles.card, compact && styles.cardCompact, isWeak && styles.cardWeak];

  return (
    <View style={cardStyle}>
      <View style={styles.header}>
        <Text style={[styles.typeBadge, isWeak && styles.typeBadgeWeak]} numberOfLines={1}>
          {typeLabel}
        </Text>
        {Number.isFinite(num(score)) && (
          <ScoreBadge score={score} size="sm" />
        )}
      </View>

      <Text style={[styles.title, isWeak && styles.titleWeak]} numberOfLines={2}>
        {effectiveTitle}
      </Text>
      {body ? (
        <Text style={[styles.body, isWeak && styles.bodyWeak]} numberOfLines={2}>
          {body}
        </Text>
      ) : null}

      {!compact && (
        <>
          {bestItem ? (
            <Text style={styles.meta} numberOfLines={1}>
              {placeName} — {bestItem}
            </Text>
          ) : (
            <Text style={styles.meta} numberOfLines={1}>
              {placeName}
            </Text>
          )}
          <Text style={styles.why} numberOfLines={2}>{whyLine}</Text>
          <View style={styles.confRow}>
            <ConfidenceBadge place={candidate} />
          </View>
          {showMenuMayVary && (
            <Text style={styles.menuMayVary} numberOfLines={1}>
              Menu may vary
            </Text>
          )}
        </>
      )}

      <RecommendationActionRow
        primaryLabel="View nearby option"
        onPrimary={() => onOpen && onOpen(candidate)}
        secondaryLabel="Dismiss"
        onSecondary={() => onDismiss && onDismiss(candidate)}
        primaryIcon=""
        variant="light"
        style={styles.actions}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceLight.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.base,
    borderWidth: 1,
    borderColor: colors.surfaceLight.cardBorder,
    ...shadows.sm,
  },
  cardCompact: {
    padding: spacing.base,
    marginBottom: spacing.sm,
  },
  cardWeak: {
    borderColor: colors.slate.primary,
    opacity: 0.95,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  typeBadge: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.textLight.muted,
  },
  typeBadgeWeak: {
    color: colors.slate.text,
  },
  title: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.textLight.primary,
  },
  titleWeak: {
    color: colors.textLight.secondary,
  },
  body: {
    fontSize: typography.md,
    color: colors.textLight.secondary,
    marginTop: spacing.xs,
  },
  bodyWeak: {
    color: colors.slate.text,
  },
  meta: {
    fontSize: typography.sm,
    color: colors.textLight.muted,
    marginTop: spacing.sm,
  },
  why: {
    fontSize: typography.xs,
    color: colors.slate.text,
    marginTop: spacing.xs,
  },
  confRow: {
    marginTop: spacing.sm,
  },
  menuMayVary: {
    fontSize: typography.xs,
    color: colors.slate.text,
    fontStyle: "italic",
    marginTop: spacing.xs,
  },
  actions: {
    marginTop: spacing.base,
  },
});

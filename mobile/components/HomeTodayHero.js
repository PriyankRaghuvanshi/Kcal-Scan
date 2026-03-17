import React, { useMemo } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography } from "../designTokens";
import { premium } from "../ui/premiumSystem";

const num = (v) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : null;
};

function formatKcal(v) {
  const n = num(v);
  if (n == null) return "—";
  return `${Math.max(0, Math.round(n))}`;
}

function formatGrams(v) {
  const n = num(v);
  if (n == null) return "—";
  return `${Math.max(0, Math.round(n))}g`;
}

function bestStatusLine({ daily, remainingToday }) {
  const winLine = String(daily?.win_line || "").trim();
  if (winLine) return winLine;

  const remainingKcal = num(remainingToday?.kcal);
  if (remainingKcal != null && remainingKcal <= 0) return "Nice — you’re in range for today.";

  return "Your day, at a glance.";
}

function buildChips(daily) {
  const chips = [];
  const proteinStreak = num(daily?.protein_streak_days);
  const loggingStreak = num(daily?.logging_streak_days);

  if (proteinStreak != null && proteinStreak >= 2) chips.push({ kind: "success", text: `${Math.round(proteinStreak)}‑day protein streak` });
  if (loggingStreak != null && loggingStreak >= 2) chips.push({ kind: "neutral", text: `${Math.round(loggingStreak)}‑day logging streak` });

  return chips.slice(0, 2);
}

export function HomeTodayHero({
  plan,
  goalPlan,
  goalCoachDaily,
  remainingToday,
  primaryAction,
  onPrimaryActionPress,
  onScanPress,
  onLetsGoPress,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
}) {
  const remainingKcal = useMemo(() => formatKcal(remainingToday?.kcal), [remainingToday?.kcal]);
  const remainingProtein = useMemo(() => formatGrams(remainingToday?.protein_g), [remainingToday?.protein_g]);
  const statusLine = useMemo(() => bestStatusLine({ daily: goalCoachDaily, remainingToday }), [goalCoachDaily, remainingToday]);
  const chips = useMemo(() => buildChips(goalCoachDaily), [goalCoachDaily]);

  const hasGoalCoach = !!goalPlan;
  const isScreenshot = Boolean(screenshotMode);
  const primaryLabel =
    (hasGoalCoach && String(primaryAction?.label || "").trim()) ||
    (hasGoalCoach ? "View today" : "Scan meal");

  const onPressPrimary = () => {
    if (hasGoalCoach) {
      if (primaryAction && onPrimaryActionPress) return onPrimaryActionPress(primaryAction);
      if (onPrimaryActionPress) return onPrimaryActionPress(null);
      return;
    }
    if (onScanPress) return onScanPress();
  };

  return (
    <View style={[premium.cardHero, styles.wrap]}>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>Today</Text>
          <Text style={styles.title}>
            <Text style={styles.titleStrong}>{remainingKcal}</Text>
            <Text style={styles.titleMuted}> kcal left</Text>
            <Text style={styles.titleMuted}> · </Text>
            <Text style={styles.titleStrong}>{remainingProtein}</Text>
            <Text style={styles.titleMuted}> protein</Text>
          </Text>
          <Text style={styles.subline} numberOfLines={2}>
            {statusLine}
          </Text>
        </View>
      </View>

      {chips.length ? (
        <View style={styles.chipsRow}>
          {chips.map((c) => (
            <View
              key={c.text}
              style={[
                premium.chipBaseSm,
                styles.chip,
                c.kind === "success" ? premium.chipSuccess : premium.chipNeutral,
              ]}
            >
              <Text style={c.kind === "success" ? premium.chipTextSuccess : premium.chipTextNeutral} numberOfLines={1}>
                {c.text}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.ctaRow}>
        <TouchableOpacity style={[premium.ctaPrimary, styles.primaryCta]} onPress={onPressPrimary} activeOpacity={0.9}>
          <Text style={[premium.ctaPrimaryText, styles.primaryCtaText]}>{primaryLabel}</Text>
        </TouchableOpacity>

        {!hasGoalCoach && !isScreenshot ? (
          <TouchableOpacity
            style={[premium.ctaSecondary, styles.secondaryCta]}
            onPress={onLetsGoPress}
            activeOpacity={0.9}
            disabled={String(plan || "").toLowerCase() === "loading"}
          >
            <Text style={premium.ctaSecondaryText}>Goal Coach</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Local layout only; surface/padding/radius comes from premium.cardHero.
  wrap: {},
  headerRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  kicker: {
    color: colors.slate.text,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    letterSpacing: 0.2,
    marginBottom: spacing.xs,
  },
  title: {
    color: colors.text.primary,
    fontSize: typography.hero,
    fontWeight: typography.weight.extrabold,
    lineHeight: Math.round(typography.hero * typography.lineHeight.tight),
  },
  titleStrong: {
    color: colors.text.primary,
    fontWeight: typography.weight.extrabold,
  },
  titleMuted: {
    color: colors.text.muted,
    fontWeight: typography.weight.semibold,
  },
  subline: {
    marginTop: spacing.sm,
    color: colors.text.secondary,
    fontSize: typography.md,
    lineHeight: Math.round(typography.md * typography.lineHeight.relaxed),
  },
  chipsRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.lg,
  },
  chip: {
    marginRight: spacing.sm,
    maxWidth: "62%",
  },
  ctaRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.xl,
  },
  primaryCta: {
    flex: 1,
  },
  primaryCtaText: {
    fontSize: typography.lg,
  },
  secondaryCta: {
    marginLeft: spacing.md,
  },
});

